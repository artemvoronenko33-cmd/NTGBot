import os
from typing import List
from pydantic import field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


class Settings(BaseSettings):
    BOT_TOKEN: str
    DB_URL: str
    DB_URL_SYNC: str | None = None
    REDIS_URL: str = "redis://localhost:6379/0"
    ADMIN_IDS: List[int] = []

    # WestWallet
    WW_PUBLIC_KEY: str = ""
    WW_PRIVATE_KEY: str = ""
    WW_CURRENCIES: List[str] = ["USDTTRC", "BTC"]
    WEBHOOK_BASE_URL: str = ""
    WW_DEV_MODE: bool = False  # True — отключает проверку IP и верификацию транзакций

    # Пополнение баланса
    TOPUP_CURRENCY: str = "USDTTRC"         # USDT TRC-20
    TOPUP_FEE_PERCENT: float = 0.0         # комиссия поверх суммы зачисления
    TOPUP_MIN_USD: float = 10.0              # минимальная сумма пополнения

    # === Платежи и баланс ===
    PAYMENT_RATE_LIMIT_ATTEMPTS: int = 3  # макс. попыток оплаты
    PAYMENT_RATE_LIMIT_WINDOW: int = 60  # в секундах
    LARGE_PAYMENT_THRESHOLD_USD: float = 100  # порог для админ-уведомления
    ADMIN_CHAT_ID: int | None = None  # ID чата для уведомлений (из .env)

    # Webhook server
    WEBHOOK_HOST: str = "0.0.0.0"
    WEBHOOK_PORT: int = 8000

    USE_WEBHOOK: bool = False
    WEBHOOK_URL: str = ""

    # ВАЛЮТА
    CURRENCY_SYMBOL: str = "$"  # Символ для отображения (₽, $, €, ₸)
    CURRENCY_ISO: str = "USD"  # Код для платёжных систем (RUB, USD, EUR, KZT)

    ADMIN_LOGIN: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    ADMIN_SECRET_KEY: str = "change_me"

    ADMIN_API_TOKEN: str = "change_me_123"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return v if isinstance(v, list) else []
    @computed_field  # ← Вычисляемое поле для SQLAdmin
    @property
    def DB_URL_SYNC_FINAL(self) -> str:
        """Возвращает DB_URL_SYNC из .env или авто-конвертирует DB_URL"""
        if self.DB_URL_SYNC:
            return self.DB_URL_SYNC
        # Fallback: авто-конвертация (если DB_URL_SYNC не задан)
        return self.DB_URL.replace("+asyncpg", "", 1)


settings = Settings()
