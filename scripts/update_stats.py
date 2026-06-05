# scripts/update_stats.py
"""
Скрипт для ручного обновления статистики
Запуск: python scripts/update_stats.py
"""

import asyncio
import sys
import os

# Добавляем корень проекта в PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.engine import async_session
from app.services.stats_updater import refresh_stats


async def main():
    print("🔄 Обновление статистики...")
    try:
        async with async_session() as db:
            result = await refresh_stats(db, notify_admin=False)
            print(f"✅ Успешно: {result}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())