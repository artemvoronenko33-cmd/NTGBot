import logging
from datetime import datetime

from app.bot.bot_instance import bot
from config import settings

logger = logging.getLogger(__name__)


async def notify_payment_success(
    user_id: int,
    order_id: int,
    amount_usd: float | None = None,
    payment_method: str = "external",
) -> None:
    """Уведомление пользователю об успешной оплате заказа"""
    try:
        method_text = {
            "balance": "💳 Списано с баланса",
            "crypto_qr": "🪙 Оплата криптовалютой получена",
            "external": "💰 Оплата получена",
        }.get(payment_method, "💰 Оплата получена")

        amount_line = f"\n💵 Сумма: <b>${amount_usd:.2f}</b>" if amount_usd is not None else ""

        await bot.send_message(
            user_id,
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"📋 Заказ <b>#{order_id}</b>\n"
            f"{method_text}{amount_line}\n\n"
            f"📦 Товары уже в обработке. Выдача начнётся автоматически.",
            parse_mode="HTML",
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
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Не удалось уведомить пользователя %s о пополнении", user_id)


async def notify_admin_large_payment(
    user_id: int,
    order_id: int,
    amount_usd: float,
    username: str | None = None,
    payment_method: str = "balance",
) -> None:
    """Уведомление админам о крупной оплате"""
    if not settings.ADMIN_CHAT_ID:
        return

    method_label = {
        "balance": "с баланса",
        "crypto_qr": "криптой (QR)",
        "external": "внешняя",
    }.get(payment_method, payment_method)

    try:
        await bot.send_message(
            chat_id=settings.ADMIN_CHAT_ID,
            text=(
                f"💰 <b>Крупная оплата ({method_label})</b>\n\n"
                f"👤 Пользователь: @{username or '—'} (`{user_id}`)\n"
                f"📋 Заказ: #{order_id}\n"
                f"💵 Сумма: <b>${amount_usd:.2f}</b>\n"
                f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            ),
            parse_mode="HTML",
        )
        logger.info("Admin notified: order=%s amount=$%.2f method=%s", order_id, amount_usd, payment_method)
    except Exception:
        logger.exception("Failed to send admin notification for order %s", order_id)