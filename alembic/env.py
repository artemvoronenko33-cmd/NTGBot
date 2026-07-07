# alembic/env.py (замените только верхнюю часть до def run_migrations_offline())
import asyncio
import sys
import os
from logging.config import fileConfig
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.models import User, Category, Product, Order, OrderItem, Payment, TopUp, SystemSettings  # добавьте сюда  # noqa: F401

# 1. Явно указываем путь к .env относительно корня проекта
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 2. Получаем URL и валидируем
db_url = os.getenv("DB_URL")
if not db_url or db_url.strip() == "":
    raise RuntimeError("❌ DB_URL не найден в .env или пуст. Проверьте файл в корне проекта.")

# 3. Принудительно перезаписываем URL для Alembic
config.set_main_option("sqlalchemy.url", db_url)

# Импортируем метаданные моделей
from app.db.base import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise ValueError("DB_URL not configured")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()