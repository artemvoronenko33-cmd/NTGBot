# app/db/repositories/__init__.py
"""
Repository слой для работы с БД.
Централизует SQL-запросы и переиспользуемую логику.
"""

from .category_repository import CategoryRepository

__all__ = ["CategoryRepository"]