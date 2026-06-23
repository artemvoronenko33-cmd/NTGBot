from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(String, default="")
    price = Column(BigInteger, nullable=False)  # Цена в копейках (напр. 100000 = 1000.00)
    is_active = Column(Boolean, default=True)

    # Связь с категорией
    category = relationship("Category", back_populates="products")
    account_items = relationship("AccountItem", back_populates="product", cascade="all, delete-orphan")