# app/db/engine.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import settings

engine = create_async_engine(settings.DB_URL, echo=False)
async_session = async_sessionmaker(bind=engine, expire_on_commit=False)