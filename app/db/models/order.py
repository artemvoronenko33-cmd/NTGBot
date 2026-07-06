# app/db/models/order.py

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum
from app.db.base import Base
from datetime import datetime


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Order(Base):
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    status = Column(String(50), default=OrderStatus.PENDING.value)
    total_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Прогресс выдачи аккаунтов
    delivery_info = Column(JSON, nullable=True)   # {"overall": 45, "items": {...}}

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(BigInteger, primary_key=True, index=True)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    price_at_purchase = Column(Float, nullable=False)
    product_name = Column(String(150))

    # Поля для процесса выдачи
    delivered_quantity = Column(Integer, default=0)
    reserved_accounts = Column(JSON, default=list)  # список s3_prefix

    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    old_status = Column(String(50))
    new_status = Column(String(50))
    changed_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="status_history")