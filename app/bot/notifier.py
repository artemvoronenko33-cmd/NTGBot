import logging
from datetime import datetime

from app.bot.bot_instance import bot
from config import settings

logger = logging.getLogger(__name__)


async def notify_payment_success(user_id: int, order_id: int) -> None:
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"Заказ <b>#{order_id}</b> успешно оплачен.\nСпасибо за покупку!",
        )
    except Exception:
        logger.exception("Не удалось отправить уведомление пользователю %s", user_id)


async def notify_topup_success(user_id: int, amount_usd: float, topup_id: int) -> None:
    request_num = 1_000_000_000 + topup_id
    logger.info("notify_topup_success: user=%s amount=$%.2f topup_id=%s", user_id, amount_usd, topup_id)
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Баланс пополнен!</b>\n\n"
            f"💲 Зачислено: <b>${amount_usd:.2f}</b>\n"
            f"🔹 Заявка №{request_num}",
        )
        logger.info("✅ Уведомление отправлено пользователю %s", user_id)
    except Exception:
        logger.exception("❌ Не удалось уведомить пользователя %s о пополнении", user_id)


# app/bot/notifier.py

async def notify_order_paid(user_id: int, order_id: int) -> None:
    """Уведомление об успешной оплате заказа с баланса"""
    logger.info("notify_order_paid: user=%s order=%s", user_id, order_id)
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Заказ #{order_id} оплачен!</b>\n\n"
            f"💳 Списано с баланса.\n"
            f"📦 Товары уже в обработке.",
        )
    except Exception:
        logger.exception("Не удалось отправить уведомление о заказе %s пользователю %s", order_id, user_id)

        # app/bot/notifier.py

async def notify_admin_large_payment(
        user_id: int,
        order_id: int,
        amount_usd: float,
        username: str | None = None,
) -> None:
    """Отправляет уведомление в админ-чат о крупной оплате"""
    if not settings.ADMIN_CHAT_ID:
        return

    try:
        await bot.send_message(
            chat_id=settings.ADMIN_CHAT_ID,
            text=(
                f"💰 <b>Крупная оплата с баланса</b>\n\n"
                f"👤 Пользователь: @{username} (`{user_id}`)\n"
                f"📋 Заказ: #{order_id}\n"
                f"💵 Сумма: <b>${amount_usd:.2f}</b>\n"
                f"⏰ Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            parse_mode="HTML",
        )
        logger.info("Admin notified about large payment: order=%s amount=$%.2f", order_id, amount_usd)
    except Exception:
        logger.exception("Failed to send admin notification for order %s", order_id)