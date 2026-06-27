# app/services/worker_logger.py
"""
Специализированный логгер для worker-операций (загрузка аккаунтов).
Логирует все транзакции в отдельный файл с детальной информацией.
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Убедиться, что директория для логов существует
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Создаём отдельный логгер для worker-операций
worker_logger = logging.getLogger("worker")
worker_logger.setLevel(logging.INFO)

# Формат с детальной информацией
worker_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# RotatingFileHandler для ротации логов (макс 5МБ на файл, хранить 10 файлов)
worker_file_handler = RotatingFileHandler(
    filename=LOGS_DIR / "worker.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=10,
    encoding="utf-8"
)
worker_file_handler.setFormatter(worker_formatter)
worker_logger.addHandler(worker_file_handler)

# Также выводим в консоль (на уровне WARNING и выше для консоли)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(worker_formatter)
worker_logger.addHandler(console_handler)


# ==================== Логирование операций ====================

def log_upload_initiated(
        worker_id: int,
        product_id: int,
        product_name: str,
        category_name: str,
        file_size: int
) -> None:
    """
    Логирует инициирование процесса загрузки аккаунтов.

    Args:
        worker_id: Telegram ID работника
        product_id: ID продукта
        product_name: Название продукта
        category_name: Название категории
        file_size: Размер ZIP-файла в байтах
    """
    file_size_mb = file_size / (1024 * 1024)
    worker_logger.info(
        f"[UPLOAD_INITIATED] 📤 worker_id={worker_id} | "
        f"product_id={product_id} | product={product_name} | "
        f"category={category_name} | file_size={file_size_mb:.2f}MB"
    )


def log_upload_completed(
        worker_id: int,
        product_id: int,
        accounts_count: int,
        total_size: int
) -> None:
    """
    Логирует успешное завершение загрузки.

    Args:
        worker_id: Telegram ID работника
        product_id: ID продукта
        accounts_count: Количество загруженных аккаунтов
        total_size: Общий размер всех файлов в байтах
    """
    total_size_mb = total_size / (1024 * 1024)
    worker_logger.info(
        f"[UPLOAD_SUCCESS] ✅ worker_id={worker_id} | "
        f"product_id={product_id} | accounts_count={accounts_count} | "
        f"total_size={total_size_mb:.2f}MB"
    )


def log_upload_failed(
        worker_id: int,
        product_id: int,
        error_reason: str
) -> None:
    """
    Логирует ошибку при загрузке.

    Args:
        worker_id: Telegram ID работника
        product_id: ID продукта
        error_reason: Описание ошибки
    """
    worker_logger.warning(
        f"[UPLOAD_FAILED] ❌ worker_id={worker_id} | "
        f"product_id={product_id} | reason={error_reason}"
    )


def log_category_selected(
        worker_id: int,
        category_id: int,
        category_name: str
) -> None:
    """
    Логирует выбор категории работником.

    Args:
        worker_id: Telegram ID работника
        category_id: ID категории
        category_name: Название категории
    """
    worker_logger.info(
        f"[CATEGORY_SELECTED] 📂 worker_id={worker_id} | "
        f"category_id={category_id} | category_name={category_name}"
    )


def log_product_selected(
        worker_id: int,
        product_id: int,
        product_name: str,
        category_name: str
) -> None:
    """
    Логирует выбор продукта работником.

    Args:
        worker_id: Telegram ID работника
        product_id: ID продукта
        product_name: Название продукта
        category_name: Название категории
    """
    worker_logger.info(
        f"[PRODUCT_SELECTED] 📦 worker_id={worker_id} | "
        f"product_id={product_id} | product_name={product_name} | "
        f"category={category_name}"
    )


def log_upload_cancelled(worker_id: int, stage: str) -> None:
    """
    Логирует отмену процесса загрузки.

    Args:
        worker_id: Telegram ID работника
        stage: На каком этапе была отмена (категория, продукт, zip)
    """
    worker_logger.info(
        f"[UPLOAD_CANCELLED] ⏹️ worker_id={worker_id} | stage={stage}"
    )


def log_session_expired(worker_id: int) -> None:
    """
    Логирует истечение сессии (например, при потере данных state).

    Args:
        worker_id: Telegram ID работника
    """
    worker_logger.warning(
        f"[SESSION_EXPIRED] ⚠️ worker_id={worker_id} | session data was lost"
    )


def log_validation_error(
        worker_id: int,
        product_id: int,
        error_message: str
) -> None:
    """
    Логирует ошибку валидации при загрузке.

    Args:
        worker_id: Telegram ID работника
        product_id: ID продукта
        error_message: Текст ошибки валидации
    """
    worker_logger.warning(
        f"[VALIDATION_ERROR] ⚠️ worker_id={worker_id} | "
        f"product_id={product_id} | error={error_message}"
    )


def log_storage_error(
        worker_id: int,
        product_id: int,
        error_message: str,
        error_type: str = "storage"
) -> None:
    """
    Логирует ошибку при работе со storage (S3/Local).

    Args:
        worker_id: Telegram ID работника
        product_id: ID продукта
        error_message: Описание ошибки
        error_type: Тип ошибки (storage, archive, permission, etc.)
    """
    worker_logger.error(
        f"[STORAGE_ERROR] 🔴 worker_id={worker_id} | "
        f"product_id={product_id} | type={error_type} | error={error_message}"
    )