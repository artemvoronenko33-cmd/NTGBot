# app/services/__init__.py
"""
Services слой приложения.
Бизнес-логика, интеграции, логирование.
"""

from .storage import StorageService

# Инициализируем storage_service как singleton
storage_service = StorageService()

__all__ = [
    "storage_service",
]