# app/services/stats_updater.py
"""
Обновление всей статистики: кэш, ежедневная, по товарам + уведомления об аномалиях
"""

from sqlalchemy import select, func, update, insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User, Product, Order, OrderItem, StatsCache, StatsDaily, StatsProduct
from datetime import datetime, timedelta, date
from config import settings
import logging

logger = logging.getLogger(__name__)


async def refresh_stats(db: AsyncSession, notify_admin: bool = True):
    """Полное обновление статистики"""

    today = date.today()
    yesterday = today - timedelta(days=1)
    month_ago = today - timedelta(days=30)

    anomalies = []  # Список аномалий для уведомления

    # === 1. СВОДНЫЕ МЕТРИКИ (stats_cache) ===

    # Пользователи
    users_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    await _update_cache(db, "total_users", users_count, "Всего пользователей")

    # Активные товары
    products_count = (await db.execute(
        select(func.count(Product.id)).where(Product.is_active == True)
    )).scalar() or 0
    await _update_cache(db, "active_products", products_count, "Активных товаров")

    # Заказы и выручка
    orders_result = (await db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0)
        ).where(Order.status.in_(["paid", "completed", "shipped"]))
    )).first()

    orders_count = orders_result[0] or 0 if orders_result else 0
    total_revenue = float(orders_result[1]) if orders_result and orders_result[1] else 0.0

    await _update_cache(db, "total_orders", orders_count, "Оплаченных заказов")
    await _update_cache(db, "total_revenue", total_revenue, "Выручка ($)")

    # 🔔 Проверка аномалий: резкий скачок заказов
    if orders_count > 0:
        prev_day = (await db.execute(
            select(StatsDaily.metric_value)
            .where(StatsDaily.stat_date == yesterday, StatsDaily.metric_name == "total_orders")
        )).scalar_one_or_none()

        if prev_day and orders_count > prev_day * 3:  # Рост в 3+ раза
            anomalies.append(f"⚠️ Скачок заказов: {prev_day} → {orders_count} (+{orders_count - prev_day})")

    # === 2. ЕЖЕДНЕВНАЯ СТАТИСТИКА (за вчерашний день) ===

    daily_metrics = [
        ("total_users", users_count),
        ("total_orders", orders_count),
        ("total_revenue", total_revenue),
        ("active_products", products_count),
    ]

    for name, value in daily_metrics:
        await _save_daily(db, yesterday, name, value)

    # === 3. СТАТИСТИКА ПО ТОВАРАМ (за 30 дней) ===

    # Очищаем старый кэш за период
    await db.execute(
        (StatsProduct.__table__.delete()
         .where(StatsProduct.period_start == month_ago, StatsProduct.period_end == today))
    )

    # Считаем выручку по товарам
    products_stats = (await db.execute(
        select(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity * OrderItem.price_at_purchase).label("revenue"),
            func.sum(OrderItem.quantity).label("qty")
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.created_at >= datetime.combine(month_ago, datetime.min.time()),
            Order.status.in_(["paid", "completed", "shipped"])
        )
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity * OrderItem.price_at_purchase).desc())
        .limit(20)
    )).all()

    for prod_id, prod_name, revenue, qty in products_stats:
        if revenue and revenue > 0:
            await db.execute(
                insert(StatsProduct).values(
                    product_id=prod_id,
                    product_name=prod_name,
                    revenue=float(revenue),
                    qty_sold=qty or 0,
                    period_start=month_ago,
                    period_end=today
                )
            )

    await db.commit()

    # === 4. УВЕДОМЛЕНИЯ ОБ АНОМАЛИЯХ ===

    if anomalies and notify_admin and settings.ADMIN_CHAT_ID:
        await _send_admin_notification(anomalies)

    logger.info(f"✅ Статистика обновлена. Аномалий: {len(anomalies)}")
    return {"status": "ok", "anomalies": anomalies}


async def _update_cache(db: AsyncSession, name: str, value: float, desc: str = ""):
    """Обновляет запись в stats_cache"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(StatsCache).values(
        metric_name=name,
        metric_value=value,
        description=desc,
        updated_at=datetime.utcnow()
    ).on_conflict_do_update(
        index_elements=["metric_name"],
        set_={"metric_value": value, "updated_at": datetime.utcnow(), "description": desc}
    )
    await db.execute(stmt)


async def _save_daily(db: AsyncSession, stat_date: date, name: str, value: float):
    """Сохраняет ежедневный снимок метрики"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(StatsDaily).values(
        stat_date=stat_date,
        metric_name=name,
        metric_value=value
    ).on_conflict_do_update(
        index_elements=["stat_date", "metric_name"],
        set_={"metric_value": value}
    )
    await db.execute(stmt)


async def _send_admin_notification(anomalies: list):
    """Отправляет уведомление в чат админа (через aiogram)"""
    try:
        from aiogram import Bot
        from config import settings

        if not settings.ADMIN_CHAT_ID or not settings.BOT_TOKEN:
            return

        bot = Bot(token=settings.BOT_TOKEN)
        message = "🚨 <b>Аномалии в статистике</b>\n\n" + "\n".join(anomalies)
        await bot.send_message(chat_id=settings.ADMIN_CHAT_ID, text=message, parse_mode="HTML")
        await bot.session.close()
    except Exception as e:
        logger.error(f"❌ Не удалось отправить уведомление: {e}")