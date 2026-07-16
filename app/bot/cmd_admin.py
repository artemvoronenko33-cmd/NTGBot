import logging
from datetime import datetime

import httpx
from aiogram.types import Message
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.engine import async_session
from app.db.models import User, OrderItem, Order, OrderStatus, AccountItem, Product
from app.services import storage_service
from app.services.maintenance import MaintenanceService
from app.services.payment import generate_address
from app.services.redis_cart import redis_client
from config import settings

logger = logging.getLogger(__name__)


async def cmd_workers(message: Message, session: AsyncSession):
    """Список всех работников"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    from sqlalchemy import text

    result = await session.execute(
        text("SELECT id, username, balance FROM users WHERE is_worker = true ORDER BY id")
    )
    workers = result.fetchall()

    if not workers:
        await message.answer("👷 Пока нет работников.")
        return

    lines = ["👷 **Список работников:**\n"]
    for w in workers:
        username = w.username or "—"
        balance = w.balance or 0
        # Используем безопасный формат без MarkdownV2 проблем
        lines.append(f"• {w.id} | {username} | Баланс: {balance}₽")

    text_msg = "\n".join(lines)

    await message.answer(text_msg, parse_mode=None)


async def cmd_deficit(message: Message):
    """Дефицит аккаунтов с категориями"""
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("⛔ Нет доступа.")
        return

    try:
        text = "📉 <b>Дефицит аккаунтов:</b>\n\n"

        async with async_session() as session:
            # Основной запрос с join категории
            needed_stmt = select(
                OrderItem.product_id,
                func.sum(OrderItem.quantity - func.coalesce(OrderItem.delivered_quantity, 0)).label("needed"),
                Product.name.label("product_name"),
                Product.category  # для eager loading
            ).join(Order).join(Product, OrderItem.product_id == Product.id).where(
                Order.status.in_([OrderStatus.PAID.value, OrderStatus.PARTIAL.value])
            ).group_by(OrderItem.product_id, Product.name, Product.category)

            needed_result = await session.execute(needed_stmt)

            for row in needed_result:
                needed = int(row.needed or 0)
                if needed <= 0:
                    continue

                product_name = row.product_name or f"Product {row.product_id}"
                category_name = row.category.name if row.category else "Без категории"

                text += f"📦 <b>{product_name}</b> ({category_name})\n"
                text += f"Нужно: <b>{needed}</b>\n\n"

        if text == "📉 <b>Дефицит аккаунтов:</b>\n\n":
            text += "Дефицита нет."

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Ошибка в /deficit")
        await message.answer("❌ Ошибка при расчёте дефицита.")
def progress_bar(percent: int, length: int = 5) -> str:
    """Простой прогресс-бар из квадратиков"""
    filled = int(percent / 100 * length)
    bar = "🟩" * filled + "⬜" * (length - filled)
    return bar


async def cmd_queue_status(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("⛔ Нет доступа.")
        return

    try:
        text = "📋 <b>Очередь заказов:</b>\n\n"

        async with async_session() as session:
            stmt = select(Order).options(
                selectinload(Order.items)
            ).where(
                Order.status.in_([OrderStatus.PAID.value, OrderStatus.PARTIAL.value])
            ).order_by(Order.created_at.asc()).limit(30)

            result = await session.execute(stmt)
            orders = result.scalars().all()

            if not orders:
                text += "Очередь пуста."
            else:
                for order in orders:
                    total_needed = sum(item.quantity for item in order.items)
                    total_delivered = sum(getattr(item, 'delivered_quantity', 0) or 0 for item in order.items)
                    progress = int((total_delivered / total_needed * 100)) if total_needed > 0 else 0

                    bar = progress_bar(progress)

                    items_text = ""
                    for item in order.items:
                        name = getattr(item, 'product_name', f"ID{item.product_id}")
                        delivered = getattr(item, 'delivered_quantity', 0) or 0
                        items_text += f"• {name}: <b>{delivered}/{item.quantity}</b>\n"

                    text += (
                        f"Заказ <b>#{order.id}</b> | {order.status.upper()}\n"
                        f"👤 {order.user_id}\n"
                        f"{bar} <b>{progress}%</b>\n"
                        f"{items_text}\n"
                    )

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Ошибка в /queue_status")
        await message.answer("❌ Ошибка при получении статуса.")


async def cmd_maintenance_on(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("Нет доступа.")
        return

    await MaintenanceService.enable_maintenance(
        message="Ведутся технические работы. Сервер перезагружается.",
        updated_by=message.from_user.id
    )
    await message.answer("✅ Сервисный режим ВКЛЮЧЁН")


async def cmd_maintenance_off(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("Нет доступа.")
        return

    await MaintenanceService.disable_maintenance()
    await message.answer("✅ Сервисный режим ВЫКЛЮЧЕН")


async def cmd_full_health(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("Нет доступа.")
        return

    await message.answer("🔍 Полная диагностика системы...")

    status = {
        "bot": "✅ Работает",
        "database": "❌",
        "redis": "❌",
        "westwallet": "❌",
        "storage": "❌",
        "webapi": "❌",
    }

    details = []

    # 1. База данных
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            users = (await session.execute(select(func.count(User.id)))).scalar()
        status["database"] = "✅ OK"
        details.append(f"• БД: {users} пользователей")
    except Exception as e:
        status["database"] = f"❌ {str(e)[:80]}"

    # 2. Redis
    try:
        await redis_client.ping()
        status["redis"] = "✅ OK"
        details.append("• Redis: подключён")
    except Exception:
        status["redis"] = "❌ Нет связи"

    # 3. WestWallet
    try:
        await generate_address("health_test", currency="USDTTRC")
        status["westwallet"] = "✅ OK"
    except Exception:
        status["westwallet"] = "⚠️ Проблемы с API"

    # 4. Storage
    try:
        if hasattr(storage_service, 's3_client'):
            storage_service.s3_client.list_objects_v2(Bucket=storage_service.bucket, MaxKeys=1)
            status["storage"] = "✅ OK"
    except Exception:
        status["storage"] = "⚠️ Проблемы с S3"

    # 5. Web API (более надёжная проверка)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"http://127.0.0.1:{settings.WEB_API_PORT}/health", follow_redirects=True)
            if resp.status_code == 200:
                status["webapi"] = "✅ OK"
                details.append("• WebAPI: отвечает")
            else:
                status["webapi"] = f"⚠️ HTTP {resp.status_code}"
    except httpx.ConnectError:
        status["webapi"] = "❌ Процесс не запущен (порт 8001)"
    except Exception as e:
        status["webapi"] = f"❌ Ошибка соединения: {str(e)[:60]}"
    except Exception:
        status["webapi"] = "❌ Не отвечает (порт 8001)"

    # Итоговый отчёт
    report = "📊 **Состояние системы**\n\n"
    for k, v in status.items():
        report += f"{v} **{k.upper()}**\n"

    if details:
        report += "\n" + "\n".join(details)

    report += f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"

    await message.answer(report, parse_mode="Markdown")