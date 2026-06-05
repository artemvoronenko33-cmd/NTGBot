from sqlalchemy import Column, BigInteger, Integer, String, Float, DateTime, ForeignKey, func
from app.db.base import Base


# app/db/models/payment.py
class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    invoice_token = Column(String(64), unique=True, nullable=True)  # nullable для баланса
    invoice_url = Column(String(512), nullable=True)                # nullable для баланса
    amount_usd = Column(Float, nullable=False)
    status = Column(String(20), default="pending")  # pending, completed, expired, refunded
    payment_method = Column(String(20), default="external")  # external, balance, telegram
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())