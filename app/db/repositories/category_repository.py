# app/db/repositories/category_repository.py
"""
Repository для работы с категориями и продуктами.
Центральное место для всех SQL-запросов, связанных с категориями/продуктами.
"""

import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Category, Product

logger = logging.getLogger(__name__)


class CategoryRepository:
    """Repository для работы с категориями и продуктами"""

    @staticmethod
    async def get_all_active_categories(session: AsyncSession) -> List[Category]:
        """
        Получить все активные категории, отсортированные по названию.

        Returns:
            List[Category]: Список категорий

        Raises:
            Exception: При ошибке БД
        """
        try:
            stmt = select(Category).order_by(Category.name)
            result = await session.execute(stmt)
            categories = result.scalars().all()
            logger.debug(f"Fetched {len(categories)} categories")
            return categories
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            raise

    @staticmethod
    async def get_category_by_id(session: AsyncSession, category_id: int) -> Optional[Category]:
        """
        Получить категорию по ID.

        Args:
            session: AsyncSession
            category_id: ID категории

        Returns:
            Category или None если не найдена
        """
        try:
            category = await session.get(Category, category_id)
            if not category:
                logger.debug(f"Category {category_id} not found")
            return category
        except Exception as e:
            logger.error(f"Error fetching category {category_id}: {e}")
            raise

    @staticmethod
    async def get_active_products_by_category(
            session: AsyncSession,
            category_id: int
    ) -> List[Product]:
        """
        Получить все активные продукты категории, отсортированные по названию.

        Args:
            session: AsyncSession
            category_id: ID категории

        Returns:
            List[Product]: Список продуктов

        Raises:
            Exception: При ошибке БД
        """
        try:
            stmt = select(Product).where(
                (Product.category_id == category_id) & (Product.is_active == True)
            ).order_by(Product.name)
            result = await session.execute(stmt)
            products = result.scalars().all()
            logger.debug(f"Fetched {len(products)} products for category {category_id}")
            return products
        except Exception as e:
            logger.error(f"Error fetching products for category {category_id}: {e}")
            raise

    @staticmethod
    async def get_product_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
        """
        Получить продукт по ID.

        Args:
            session: AsyncSession
            product_id: ID продукта

        Returns:
            Product или None если не найден
        """
        try:
            product = await session.get(Product, product_id)
            if not product:
                logger.debug(f"Product {product_id} not found")
            return product
        except Exception as e:
            logger.error(f"Error fetching product {product_id}: {e}")
            raise

    @staticmethod
    async def get_product_with_category(
            session: AsyncSession,
            product_id: int
    ) -> Optional[tuple[Product, Optional[Category]]]:
        """
        Получить продукт с информацией о его категории.

        Args:
            session: AsyncSession
            product_id: ID продукта

        Returns:
            Кортеж (Product, Category) или (Product, None) если категория не найдена
        """
        try:
            product = await session.get(Product, product_id)
            if not product:
                logger.debug(f"Product {product_id} not found")
                return None

            # Category автоматически загружается через relationship
            category = product.category
            return (product, category)
        except Exception as e:
            logger.error(f"Error fetching product with category {product_id}: {e}")
            raise