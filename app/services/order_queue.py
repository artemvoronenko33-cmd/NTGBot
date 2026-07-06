# app/services/order_queue.py
import logging
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import BufferedInputFile

from app.db.models import Order, OrderStatus, OrderItem
from app.services.order_delivery import OrderDeliveryService
from app.services.redis_cart import redis_client

logger = logging.getLogger(__name__)


class OrderQueueService:
    def __init__(self):
        self.delivery_service = OrderDeliveryService()
        self.queue_key = "order:processing:queue"

    async def enqueue_order(self, order_id: int):
        await redis_client.rpush(self.queue_key, str(order_id))
        logger.info(f"Заказ #{order_id} добавлен в очередь")

    async def enqueue_all_pending(self, session: AsyncSession):
        """Добавляет все PAID и PARTIAL заказы в очередь"""
        stmt = select(Order.id).where(
            Order.status.in_([OrderStatus.PAID.value, OrderStatus.PARTIAL.value])
        ).order_by(Order.created_at.asc())
        result = await session.execute(stmt)
        order_ids = [row[0] for row in result.all()]

        for oid in order_ids:
            await self.enqueue_order(oid)

        logger.info(f"В очередь добавлено {len(order_ids)} заказов")

    async def process_single_order(self, session: AsyncSession):
        """Обрабатывает один заказ из очереди"""
        order_id_str = await redis_client.lpop(self.queue_key)
        if not order_id_str:
            return

        order_id = int(order_id_str)

        logger.info(f"Начинаем обработку заказа #{order_id}")

        try:
            # Eager loading
            stmt = select(Order).options(
                selectinload(Order.items).joinedload(OrderItem.product)
            ).where(Order.id == order_id)

            result = await session.execute(stmt)
            order = result.scalar_one_or_none()

            if not order or order.status not in [OrderStatus.PAID.value, OrderStatus.PARTIAL.value]:
                return

            reserved = await self.delivery_service.reserve_accounts_for_order(session, order_id)

            if reserved:
                archive_bytes, password = await self.delivery_service.build_order_archive(session, order_id)
                if archive_bytes:
                    await self._send_order_to_user(order.user_id, order_id, archive_bytes, password)
                    order.status = OrderStatus.COMPLETED.value
                else:
                    order.status = OrderStatus.PARTIAL.value
            else:
                order.status = OrderStatus.PARTIAL.value

            await session.commit()

        except Exception as e:
            logger.exception(f"Ошибка обработки заказа #{order_id}")
            await asyncio.sleep(2)

    async def _send_order_to_user(self, user_id: int, order_id: int, archive_bytes: bytes, password: str):
        from app.bot.bot_instance import bot
        try:
            await bot.send_document(
                chat_id=user_id,
                document=BufferedInputFile(archive_bytes, filename=f"order_{order_id}.zip"),
                caption=f"✅ Заказ #{order_id} готов!"
            )
            await asyncio.sleep(1.5)
            await bot.send_message(user_id, f"🔑 Пароль: `{password}`", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Не удалось отправить заказ {order_id}: {e}")