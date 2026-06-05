# app/db/models/order.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_price = Column(Float, default=0.0)
    status = Column(String(50), default="created")
    created_at = Column(DateTime, default=datetime.utcnow)

    # ✅ ОДНОСТОРОННИЕ СВЯЗИ (без back_populates — надёжно и просто)
    user = relationship("User")  # ← просто связь, без обратной
    items = relationship("OrderItem", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    # ✅ НОВОЕ ПОЛЕ: название товара на момент покупки
    product_name = Column(String(150), nullable=True)  # Можно nullable, если старые записи без имени

    quantity = Column(Integer, default=1)
    price_at_purchase = Column(Float, nullable=False)

    product = relationship("Product")

    # ✅ Теперь это безопасно работает!
    def __repr__(self):
        name = self.product_name or f"Товар #{self.product_id}"
        return f"{name} × {self.quantity} = ${self.price_at_purchase * self.quantity:.2f}"


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    old_status = Column(String(50))
    new_status = Column(String(50))
    changed_at = Column(DateTime, default=datetime.utcnow)

    # ✅ БЕЗОПАСНЫЙ __repr__
    def __repr__(self):
        return f"{self.old_status or '—'} → {self.new_status}"
