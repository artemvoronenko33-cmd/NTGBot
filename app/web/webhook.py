import logging
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select, update

from app.db.engine import async_session
from app.db.models.payment import Payment
from app.db.models.order import Order
from app.db.models.topup import TopUp
from app.db.models.user import User
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

_IPN_IP = "5.188.51.47"


@router.post("/webhook/ipn")
async def ipn_handler(request: Request):
    client_ip = request.client.host
    if not settings.WW_DEV_MODE and client_ip != _IPN_IP:
        logger.warning("IPN rejected from IP: %s", client_ip)
        raise HTTPException(status_code=403, detail="Forbidden")

    form = await request.form()
    data = dict(form)
    logger.info("IPN received: %s", data)

    label = data.get("label", "")
    status = data.get("status", "")

    if not label or not status:
        return {"ok": True}

    if label.startswith("topup_"):
        received_amount = _parse_float(data.get("amount"))
        await _handle_topup_ipn(label, status, received_amount)
    else:
        await _handle_order_ipn(label, status)

    return {"ok": True}


def _parse_float(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


async def _handle_order_ipn(label: str, status: str) -> None:
    try:
        order_id = int(label)
    except ValueError:
        return

    if status != "completed":
        return

    if not settings.WW_DEV_MODE:
        try:
            from app.services.payment import verify_transaction
            tx = await verify_transaction(label)
            if tx.get("status") != "completed":
                logger.warning("IPN spoofing attempt for order %s", order_id)
                return
        except Exception:
            logger.exception("Не удалось верифицировать транзакцию для заказа %s", order_id)
            return

    async with async_session() as session:
        stmt = select(Payment).where(Payment.order_id == order_id)
        payment = (await session.execute(stmt)).scalar_one_or_none()

        if not payment or payment.status == "completed":
            return

        payment.status = "completed"
        await session.execute(
            update(Order).where(Order.id == order_id).values(status="paid")
        )
        await session.commit()
        user_id = payment.user_id

    from app.bot.notifier import notify_payment_success
    await notify_payment_success(user_id, order_id)


async def _handle_topup_ipn(label: str, status: str, received_amount: float) -> None:
    if status != "completed":
        return

    if not settings.WW_DEV_MODE:
        try:
            from app.services.payment import verify_transaction
            tx = await verify_transaction(label)
            if tx.get("status") != "completed":
                logger.warning("IPN spoofing for topup %s", label)
                return
        except Exception:
            logger.exception("Не удалось верифицировать топап %s", label)
            return

    async with async_session() as session:
        stmt = select(TopUp).where(TopUp.label == label)
        topup = (await session.execute(stmt)).scalar_one_or_none()

        if not topup or topup.status == "completed":
            return

        # Защита от недоплаты: принимаем только если получено ≥ ожидаемой суммы
        expected = float(topup.amount_usdt)
        if received_amount + 1e-9 < expected:
            logger.warning(
                "Недоплата по топапу %s: получено %.8f, ожидалось %.8f",
                label, received_amount, expected,
            )
            topup.status = "underpaid"
            await session.commit()
            return

        # Зачисляем по факту полученного crypto × курс (на момент создания)
        # fallback: если rate_usd не сохранён (старые записи) — берём amount_usd/amount_usdt
        rate = topup.rate_usd
        if rate is None or rate <= 0:
            rate = topup.amount_usd / topup.amount_usdt if topup.amount_usdt else 0
        credit_usd = received_amount * float(rate)
        balance_delta = int(round(credit_usd * 100))  # в центах

        topup.status = "completed"
        topup.amount_usd = credit_usd  # фактическое зачисление
        await session.execute(
            update(User)
            .where(User.id == topup.user_id)
            .values(balance=User.balance + balance_delta)
        )
        await session.commit()
        user_id = topup.user_id
        amount_usd = credit_usd
        topup_db_id = topup.id

    from app.bot.notifier import notify_topup_success
    await notify_topup_success(user_id, amount_usd, topup_db_id)
