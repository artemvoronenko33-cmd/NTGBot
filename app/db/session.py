# app/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings   # или откуда импортируется конфиг

# Если у тебя используется SQLAlchemy 2.0 + asyncpg
engine = create_async_engine(
    settings.DB_URL,          # ← если этой строки нет — замени на правильное название
    # или если у тебя postgresql+asyncpg:
    # "postgresql+asyncpg://botuser:password@localhost/botdb"
    echo=False,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)