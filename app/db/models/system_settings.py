from sqlalchemy import Column, Integer, Boolean, Text, DateTime, BigInteger
from sqlalchemy.sql import func

# Измените импорт на то, что используется в вашем проекте
# Посмотрите, как импортируется Base в других моделях (например stats.py)

from app.db.base import Base  # попробуйте этот вариант


# или
# from app.db.models.base import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)

    maintenance_mode = Column(Boolean, default=False, nullable=False)
    maintenance_message = Column(Text, default="Ведутся технические работы. Попробуйте позже.")
    maintenance_until = Column(DateTime(timezone=False), nullable=True)

    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now())
    updated_by = Column(BigInteger, nullable=True)