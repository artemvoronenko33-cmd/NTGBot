# app/db/models/account_item.py
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.db.base import Base


class AccountStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"


class AccountItem(Base):
    __tablename__ = "account_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)

    # Связь с типом товара (Product)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)

    # === Основное хранение в DigitalOcean Spaces ===
    s3_prefix = Column(Text, nullable=False, unique=True, index=True)
    # Пример: accounts/premium/20250623_154512_Premium_LVL120_#3421/

    account_name = Column(String(255), nullable=False)      # Читаемое название аккаунта
    file_count = Column(Integer, default=0)                 # Количество файлов внутри папки аккаунта
    total_size = Column(BigInteger, nullable=True)          # Общий размер в байтах

    # Статус и резервирование
    status = Column(SQLEnum(AccountStatus), default=AccountStatus.AVAILABLE, nullable=False)
    reserved_for_order_id = Column(BigInteger, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)

    # Информация о создании
    added_by_worker_id = Column(BigInteger, nullable=True)   # Telegram ID работника
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sold_at = Column(DateTime, nullable=True)

    # Характеристики аккаунта
    metadata_json = Column(Text, nullable=True)  # JSON с уровнем, скинами и т.д.

    # Связи
    product = relationship("Product", back_populates="account_items")
    

    def __repr__(self):
        return f"<AccountItem {self.id} | {self.account_name} | {self.status.value}>"