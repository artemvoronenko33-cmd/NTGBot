# app/services/balance.py
import json
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, BalanceTransaction, TransactionType
from config import settings

logger = logging.getLogger(__name__)

# Rate-limit: храним в памяти для простоты (в продакшене — Redis)
_payment_attempts: dict[int, list[datetime]] = {}


async def check_rate_limit(user_id: int, max_attempts: int = 3, window_seconds: int = 60) -> bool:
    """Проверяет, не превысил ли пользователь лимит попыток оплаты"""
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=window_seconds)

    # Очищаем старые записи
    _payment_attempts[user_id] = [
        ts for ts in _payment_attempts.get(user_id, [])
        if ts > window_start
    ]

    if len(_payment_attempts[user_id]) >= max_attempts:
        return False  # лимит превышен

    _payment_attempts[user_id].append(now)
    return True


async def record_transaction(
    session: AsyncSession,
    user_id: int,
    amount_cents: int,
    transaction_type: TransactionType,
    description: str | None = None,
    order_id: int | None = None,
    topup_id: int | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    commit: bool = False,   # новый параметр
) -> int:
    """
    Записывает транзакцию и возвращает новый баланс пользователя.
    amount_cents: положительное = зачисление, отрицательное = списание
    """
    # Получаем текущего пользователя с блокировкой (FOR UPDATE)
    stmt = select(User).where(User.id == user_id).with_for_update()
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user:
        raise ValueError(f"User {user_id} not found")

    # Проверка на недостаточность средств при списании
    if amount_cents < 0 and user.balance + amount_cents < 0:
        raise ValueError("Insufficient balance")

    # Обновляем баланс
    user.balance += amount_cents
    balance_after = user.balance

    # Создаём запись транзакции
    tx = BalanceTransaction(
        user_id=user_id,
        amount_cents=amount_cents,
        transaction_type=transaction_type.value,
        order_id=order_id,
        topup_id=topup_id,
        description=description,
        metadata_json=json.dumps(metadata) if metadata else None,
        balance_after=balance_after,
        ip_address=ip_address,
    )
    session.add(tx)

    # Логирование
    logger.info(
        "BalanceTransaction: user=%s type=%s amount_cents=%d balance_after=%d order_id=%s",
        user_id, transaction_type.value, amount_cents, balance_after, order_id
    )


    return balance_after


async def get_user_balance_history(
        session: AsyncSession,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
) -> list[BalanceTransaction]:
    """Получает историю транзакций пользователя"""
    stmt = (
        select(BalanceTransaction)
        .where(BalanceTransaction.user_id == user_id)
        .order_by(BalanceTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return result.scalars().all()