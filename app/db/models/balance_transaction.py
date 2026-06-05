# app/db/models/balance_transaction.py
from sqlalchemy import Column, BigInteger, Integer, String, Float, DateTime, func, ForeignKey, Enum
from app.db.base import Base
import enum


class TransactionType(enum.Enum):
    DEPOSIT = "deposit"  # пополнение (топап, реферал)
    ORDER_PAYMENT = "order_payment"  # оплата заказа
    REFUND = "refund"  # возврат
    ADMIN_ADJUSTMENT = "admin_adjustment"  # ручная коррекция админом


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)

    # Сумма в центах (положительная = зачисление, отрицательная = списание)
    amount_cents = Column(Integer, nullable=False)

    # Тип операции
    transaction_type = Column(String(20), nullable=False)  # храним как строку из enum.name

    # Связь с сущностью (опционально)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=True)
    topup_id = Column(BigInteger, ForeignKey("topups.id"), nullable=True)

    # Метаданные
    description = Column(String(255), nullable=True)  # краткое описание
    metadata_json = Column(String, nullable=True)  # доп. данные в JSON

    # Баланс после операции (для быстрого аудита)
    balance_after = Column(Integer, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    ip_address = Column(String(45), nullable=True)  # для безопасности