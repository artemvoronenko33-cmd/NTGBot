# app/db/models/stats.py
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime


class StatsCache(Base):
    """Кэш текущих метрик"""
    __tablename__ = "stats_cache"

    id = Column(Integer, primary_key=True)
    metric_name = Column(String(100), unique=True, nullable=False, index=True)
    metric_value = Column(Numeric(20, 2), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    description = Column(String(255), default="")
    def __repr__(self):
        return f"<StatsCache {self.metric_name}={self.metric_value}>"

class StatsDaily(Base):
    """Ежедневная история метрик"""
    __tablename__ = "stats_daily"
    __table_args__ = (UniqueConstraint('stat_date', 'metric_name', name='uq_daily_metric'),)

    id = Column(Integer, primary_key=True)
    stat_date = Column(Date, nullable=False, index=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Numeric(20, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StatsProduct(Base):
    """Статистика по товарам"""
    __tablename__ = "stats_products"
    __table_args__ = (UniqueConstraint('product_id', 'period_start', 'period_end', name='uq_product_period'),)

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(150), nullable=False)
    revenue = Column(Numeric(20, 2), nullable=False)
    qty_sold = Column(Integer, default=0)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

