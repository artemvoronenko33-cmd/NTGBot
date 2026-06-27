# app/services/payment_logger.py
"""
Специализированный логгер для платежей и финансовых операций.
Логирует все транзакции в отдельный файл с детальной информацией.
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Убедиться, что директория для логов существует
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Создаём отдельный логгер для платежей
payment_logger = logging.getLogger("payments")
payment_logger.setLevel(logging.INFO)

# Формат с более подробной информацией
payment_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# RotatingFileHandler для ротации логов (макс 5МБ на файл, хранить 10 файлов)
payment_file_handler = RotatingFileHandler(
    filename=LOGS_DIR / "payments.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=10,
    encoding="utf-8"
)
payment_file_handler.setFormatter(payment_formatter)
payment_logger.addHandler(payment_file_handler)

# Также выводим в консоль (на уровне WARNING и выше для консоли)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(payment_formatter)
payment_logger.addHandler(console_handler)


def log_payment_start(user_id: int, order_id: int, amount_usd: float, payment_method: str) -> None:
    """Логирует начало обработки платежа"""
    payment_logger.info(
        f"[PAYMENT_START] user_id={user_id} | order_id={order_id} | "
        f"amount_usd={amount_usd:.2f} | method={payment_method}"
    )


def log_payment_success(user_id: int, order_id: int, amount_usd: float, payment_method: str,
                       new_balance_cents: int) -> None:
    """Логирует успешный платёж"""
    payment_logger.info(
        f"[PAYMENT_SUCCESS] ✅ user_id={user_id} | order_id={order_id} | "
        f"amount_usd={amount_usd:.2f} | method={payment_method} | "
        f"new_balance_usd={new_balance_cents / 100:.2f}"
    )


def log_payment_failed(user_id: int, order_id: int, amount_usd: float, payment_method: str,
                      error_reason: str) -> None:
    """Логирует неудачный платёж"""
    payment_logger.warning(
        f"[PAYMENT_FAILED] ❌ user_id={user_id} | order_id={order_id} | "
        f"amount_usd={amount_usd:.2f} | method={payment_method} | "
        f"reason={error_reason}"
    )


def log_topup_initiated(user_id: int, topup_id: int, amount_usd: float,
                       currency: str, address: str) -> None:
    """Логирует инициирование пополнения баланса"""
    payment_logger.info(
        f"[TOPUP_INITIATED] user_id={user_id} | topup_id={topup_id} | "
        f"amount_usd={amount_usd:.2f} | currency={currency} | "
        f"address={address[:20]}..."
    )


def log_topup_completed(user_id: int, topup_id: int, amount_usd: float,
                       amount_received: float, currency: str) -> None:
    """Логирует завершение пополнения"""
    payment_logger.info(
        f"[TOPUP_COMPLETED] ✅ user_id={user_id} | topup_id={topup_id} | "
        f"requested_usd={amount_usd:.2f} | received_usd={amount_received:.2f} | "
        f"currency={currency}"
    )


def log_refund(user_id: int, order_id: int, amount_usd: float) -> None:
    """Логирует возврат средств"""
    payment_logger.info(
        f"[REFUND] ♻️ user_id={user_id} | order_id={order_id} | "
        f"refund_amount_usd={amount_usd:.2f}"
    )


def log_rate_limit_hit(user_id: int, max_attempts: int, window_seconds: int) -> None:
    """Логирует превышение лимита попыток платежа"""
    payment_logger.warning(
        f"[RATE_LIMIT_HIT] ⚠️ user_id={user_id} | "
        f"max_attempts={max_attempts} | window_seconds={window_seconds}"
    )


def log_large_payment_admin_notified(user_id: int, order_id: int, amount_usd: float,
                                     username: str) -> None:
    """Логирует уведомление администратора о крупном платеже"""
    payment_logger.info(
        f"[ADMIN_NOTIFIED] 🔔 user_id={user_id} | order_id={order_id} | "
        f"amount_usd={amount_usd:.2f} | username={username}"
    )