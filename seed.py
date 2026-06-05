# seed.py
import asyncio
from app.db.engine import async_session
from app.db.models import Category, Product


async def seed():
    async with async_session() as session:
        # Проверяем, есть ли уже данные
        from sqlalchemy import select
        if (await session.execute(select(Category))).scalar_one_or_none():
            print("️ Данные уже есть, пропускаем.")
            return

        print("🌱 Заполняем БД...")

        # Категории
        cat1 = Category(name=" Фастфуд")
        cat2 = Category(name="🥤 Напитки")
        session.add_all([cat1, cat2])
        await session.flush()  # Чтобы получить ID категорий

        # Товары
        session.add_all([
            Product(category_id=cat1.id, name="Чизбургер", description="Сочный бургер с сыром", price=1),  # 350.00
            Product(category_id=cat1.id, name="Картошка Фри", description="Хрустящая", price=2),  # 120.00
            Product(category_id=cat2.id, name="Кола 0.5", description="Классика", price=3),  # 90.00
            Product(category_id=cat2.id, name="Сок Апельсин", description="Натуральный", price=4)  # 150.00
        ])

        await session.commit()
        print("✅ Готово!")


if __name__ == "__main__":
    asyncio.run(seed())