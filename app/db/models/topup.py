from sqlalchemy import Column, BigInteger, Integer, String, Float, DateTime, func
from app.db.base import Base


class TopUp(Base):
    __tablename__ = "topups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    amount_usd = Column(Float, nullable=False)    # ожидаемая сумма зачисления
    amount_usdt = Column(Float, nullable=False)   # ожидаемая сумма к оплате
    rate_usd = Column(Float, nullable=True)       # курс 1 crypto = USD на момент создания
    address = Column(String(128), nullable=False)
    label = Column(String(64), unique=True, nullable=False)
    status = Column(String(20), default="pending")  # pending, completed, underpaid
    created_at = Column(DateTime, server_default=func.now())

