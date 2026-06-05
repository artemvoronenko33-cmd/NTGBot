# scripts/create_history_table.py
"""
Скрипт для создания таблицы истории статусов заказов.
Запуск: python scripts/create_history_table.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.db.engine import async_session

async def main():
    sql = """
    CREATE TABLE IF NOT EXISTS order_status_history (
        id SERIAL PRIMARY KEY,
        order_id INTEGER REFERENCES orders(id),
        old_status VARCHAR(50),
        new_status VARCHAR(50),
        changed_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    async with async_session() as session:
        await session.execute(text(sql))
        await session.commit()
    print("✅ Таблица order_status_history создана или уже существует.")

if __name__ == "__main__":
    asyncio.run(main())
