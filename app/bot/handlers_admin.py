# app/bot/handlers_admin.py
import asyncio
import logging
from datetime import datetime

import httpx
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.filters import Command, StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session
from app.db.models import User, OrderStatus, Order, OrderItem, Payment
from app.db.models.order import OrderStatusHistory
from app.services import storage_service
from app.services.payment import generate_address
from app.services.redis_cart import redis_client
from config import settings  # или откуда импортируется settings
from sqlalchemy import text, select, delete, func
from app.bot.keyboards import get_admin_menu, get_cancel_kb

from app.services.maintenance import MaintenanceService

logger = logging.getLogger(__name__)
router = Router(name="admin_router")

@router.message(Command("admin"))
async def cmd_worker(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user or not getattr(user, 'is_worker', False):
        await message.answer("⛔ У вас нет доступа к панели работника.")
        return

    await message.answer(
        "👷 Добро пожаловать в панель работника!\n\n"
        "Выберите действие:",
        reply_markup=get_admin_menu()
    )

@router.message(Command("addworker"))
async def cmd_addworker(message: Message, session: AsyncSession):
    """Назначить пользователя работником"""
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("⛔ У вас нет прав администратора.")
        return

    try:
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "❌ Использование:\n"
                "`/addworker <user_id>`\n\n"
                "Пример: `/addworker 726313576`",
                parse_mode="Markdown"
            )
            return

        target_id = int(parts[1])

        user = await session.get(User, target_id)

        if not user:
            user = User(
                id=target_id,
                is_worker=True
            )
            session.add(user)
            action = "создан и назначен"
        else:
            if user.is_worker:
                await message.answer(f"✅ Пользователь `{target_id}` уже является работником.")
                return
            user.is_worker = True
            action = "назначен"

        await session.commit()

        await message.answer(
            f"✅ Пользователь `{target_id}` успешно **{action}** работником.\n"
            f"Теперь он может использовать команду /worker",
            parse_mode="Markdown"
        )

    except ValueError:
        await message.answer("❌ User ID должен быть числом.")
    except Exception as e:
        await session.rollback()
        await message.answer(f"❌ Произошла ошибка: {str(e)}")


@router.message(Command("delworker"))
async def cmd_delworker(message: Message, session: AsyncSession):
    """Снять статус работника"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    try:
        target_id = int(message.text.split()[1])
        user = await session.get(User, target_id)

        if user and user.is_worker:
            user.is_worker = False
            await session.commit()
            await message.answer(f"✅ У пользователя `{target_id}` снят статус работника.")
        else:
            await message.answer("❌ Пользователь не найден или не является работником.")
    except Exception:
        await message.answer("❌ Использование: `/delworker <user_id>`")


@router.message(Command("workers"))
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

@router.message(Command("deficit"))
async def show_deficit(message: Message, session: AsyncSession):
    """Сводка дефицита по товарам"""
    try:
        sql = """
            SELECT 
                p.name as product_name,
                c.name as category_name,
                COUNT(ai.id) as available,
                COALESCE(SUM(oi.quantity - oi.delivered_quantity), 0) as needed
            FROM products p
            JOIN categories c ON p.category_id = c.id
            LEFT JOIN account_items ai 
                ON ai.product_id = p.id AND ai.is_reserved = false
            LEFT JOIN order_items oi ON oi.product_id = p.id
            GROUP BY p.id, p.name, c.name
            HAVING COALESCE(SUM(oi.quantity - oi.delivered_quantity), 0) > 0
        """

        result = await session.execute(text(sql))
        rows = result.all()

        if not rows:
            await message.answer("✅ Дефицита нет. Все заказы могут быть выполнены.")
            return

        response_text = "📉 <b>Дефицит аккаунтов:</b>\n\n"
        for row in rows:
            response_text += f"📦 {row.product_name} ({row.category_name})\n"
            response_text += f"   Нужно: {row.needed} | В наличии: {row.available or 0}\n\n"

        await message.answer(response_text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Error in deficit command")
        await message.answer("❌ Ошибка при получении сводки.")

@router.message(Command("queue_status"))
async def queue_status(message: Message, session: AsyncSession):
    """Статус очереди заказов (для админа)"""
    try:
        # Заказы в обработке
        stmt = select(Order).where(
            Order.status.in_([OrderStatus.PAID.value, OrderStatus.PROCESSING.value, OrderStatus.PARTIAL.value])
        ).order_by(Order.created_at)

        result = await session.execute(stmt)
        orders = result.scalars().all()

        if not orders:
            await message.answer("📭 Очередь пуста.")
            return

        text = "📋 <b>Очередь заказов:</b>\n\n"
        for order in orders:
            progress = order.delivery_info.get("overall", 0) if order.delivery_info else 0
            text += f"Заказ #{order.id} | {order.status.upper()}\n"
            text += f"   Пользователь: {order.user_id}\n"
            text += f"   Прогресс: {progress}%\n"
            if order.delivery_info and "items" in order.delivery_info:
                for pid, info in order.delivery_info["items"].items():
                    text += f"   • {info.get('product_name', pid)}: {info.get('delivered', 0)}/{info.get('needed', 0)}\n"
            text += "\n"

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Error in queue_status")
        await message.answer("❌ Ошибка при получении очереди.")


@router.message(Command("delete_orders"))
async def delete_orders(message: Message, session: AsyncSession, state: FSMContext):
    """Начать процесс удаления заказов"""
    await message.answer("Отправь ID заказов через запятую (например: 24,25,30)")
    await state.set_state("waiting_for_order_ids_to_delete")


@router.message(StateFilter("waiting_for_order_ids_to_delete"))
async def process_order_ids(message: Message, session: AsyncSession, state: FSMContext):
    try:
        order_ids = [int(x.strip()) for x in message.text.split(',') if x.strip().isdigit()]

        if not order_ids:
            await message.answer("Не найдено корректных ID.")
            await state.clear()
            return

        # Удаляем всё связанное
        await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
        await session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))  # ← Добавлено
        await session.execute(delete(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(order_ids)))

        # Удаляем заказы
        result = await session.execute(delete(Order).where(Order.id.in_(order_ids)))

        await session.commit()

        await message.answer(f"✅ Успешно удалено {result.rowcount} заказов (включая все связанные записи).")

    except Exception as e:
        await session.rollback()
        error_msg = str(e)[:200].replace('<', '&lt;').replace('>', '&gt;')  # экранируем
        await message.answer(f"Ошибка: {error_msg}")
    finally:
        await state.clear()


@router.message(Command("maintenance_on"))
async def cmd_maintenance_on(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("Нет доступа.")
        return

    await MaintenanceService.enable_maintenance(
        message="Ведутся технические работы. Сервер перезагружается.",
        updated_by=message.from_user.id
    )
    await message.answer("✅ Сервисный режим ВКЛЮЧЁН")


@router.message(Command("maintenance_off"))
async def cmd_maintenance_off(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("Нет доступа.")
        return

    await MaintenanceService.disable_maintenance()
    await message.answer("✅ Сервисный режим ВЫКЛЮЧЕН")


@router.message(Command("health"))
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