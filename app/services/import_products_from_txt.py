import asyncio
import re
from sqlalchemy import select
from app.db.engine import async_session
from app.db.models import Product, Category


async def import_products(txt_path: str, category_name: str):
    async with async_session() as session:
        # Получаем или создаём категорию
        result = await session.execute(select(Category).where(Category.name == category_name))
        category = result.scalar_one_or_none()

        if not category:
            category = Category(name=category_name)
            session.add(category)
            await session.commit()
            await session.refresh(category)
            print(f"✅ Создана категория: {category_name}")

        count = 0
        with open(txt_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                match = re.match(r"(.+?)\s*\((\d+)\$\)", line)
                if not match:
                    print(f"⚠️ Пропущена: {line}")
                    continue

                name = match.group(1).strip()
                price = int(match.group(2)) * 100  # в копейки

                # Проверяем дубликат
                exists = await session.execute(
                    select(Product).where(Product.name == name, Product.category_id == category.id)
                )
                if exists.scalar_one_or_none():
                    print(f"⏭️ Уже есть: {name}")
                    continue

                prod = Product(
                    name=name,
                    price=price,
                    category_id=category.id,
                    is_active=True,
                    description="Импортировано из TXT"
                )
                session.add(prod)
                count += 1

        await session.commit()
        print(f"✅ Успешно добавлено {count} товаров в категорию '{category_name}'")


if __name__ == "__main__":
    asyncio.run(import_products("products.txt", "НазваниеВашейКатегории"))