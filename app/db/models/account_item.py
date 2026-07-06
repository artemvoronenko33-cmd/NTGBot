# app/db/models/account_item.py
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class AccountStatus(str, enum.Enum):
    FREE = "free"
    RESERVED = "reserved"
    DELIVERED = "delivered"


class AccountItem(Base):
    __tablename__ = "account_items"

    id = Column(BigInteger, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    s3_prefix = Column(String(255), unique=True, nullable=False)
    account_name = Column(String(150))
    file_count = Column(Integer)
    total_size = Column(BigInteger)
    added_by_worker_id = Column(BigInteger)

    # Новые поля
    status = Column(String(20), default=AccountStatus.FREE.value)
    is_reserved = Column(Boolean, default=False)
    reserved_for_order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=True)
    reserved_at = Column(DateTime, nullable=True)

    product = relationship("Product")
    # relationship на Order делаем lazy, чтобы избежать циклической загрузки
    order = relationship("Order", foreign_keys=[reserved_for_order_id], lazy="selectin")


def __repr__(self):
    return f"<AccountItem {self.account_name} ({self.status})>"