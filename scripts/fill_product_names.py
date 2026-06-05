# scripts/fill_product_names.py
"""
Заполняет поле product_name в order_items на основе связанных товаров.
Запуск: python scripts/fill_product_names.py
"""

import asyncio
import sys
import os

# Добавляем корень проекта в PATH, чтобы работали импорты
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select, update
from app.db.engine import async_session
from app.db.models import OrderItem, Product


async def main():
    print("🔍 Поиск записей без product_name...")

    async with async_session() as db:
        # Находим все OrderItem, где product_name пустой
        items = (await db.execute(
            select(OrderItem).where(
                (OrderItem.product_name == None) | (OrderItem.product_name == '')
            )
        )).scalars().all()

        print(f"📦 Найдено {len(items)} записей для обновления")

        if not items:
            print("✅ Все записи уже заполнены!")
            return

        updated = 0
        for item in items:
            if item.product_id:
                # Ищем товар по ID
                product = (await db.execute(
                    select(Product).where(Product.id == item.product_id)
                )).scalar_one_or_none()

                if product and product.name:
                    # Обновляем product_name
                    await db.execute(
                        update(OrderItem)
                        .where(OrderItem.id == item.id)
                        .values(product_name=product.name)
                    )
                    updated += 1

        # Сохраняем изменения
        await db.commit()
        print(f"✅ Обновлено {updated} из {len(items)} записей")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
