# app/db/models/user.py
from sqlalchemy import Column, BigInteger, String, DateTime, func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=False)  # Telegram ID
    username = Column(String(32), nullable=True)
    language_code = Column(String(10), default="ru")
    balance = Column(BigInteger, default=0)  # В минимальных единицах (копейки/сатоши)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())   
    def __repr__(self):
        return f"{self.username or 'Без имени'} (ID: {self.id})" 
 
    