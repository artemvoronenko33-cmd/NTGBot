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
from config import settings

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
        """Обрабатывает один заказ с Redis Lock и корректным управлением очередью"""
        # ==================== REDIS LOCK ====================
        lock_key = "order:queue:global_lock"
        locked = await redis_client.set(lock_key, "1", nx=True, ex=60)  # 60 секунд таймаут
        if not locked:
            logger.debug("Другой обработчик уже работает с очередью")
            return

        try:
            # ==================== БЕРЁМ ЗАКАЗ ИЗ ОЧЕРЕДИ ====================
            order_id_str = await redis_client.lpop(self.queue_key)
            if not order_id_str:
                return

            order_id = int(order_id_str)
            logger.info(f"Начинаем обработку заказа #{order_id}")

            # ==================== ЗАГРУЗКА ЗАКАЗА ====================
            stmt = select(Order).options(
                selectinload(Order.items).joinedload(OrderItem.product)
            ).where(Order.id == order_id)

            result = await session.execute(stmt)
            order = result.scalar_one_or_none()

            if not order or order.status not in [OrderStatus.PAID.value, OrderStatus.PARTIAL.value]:
                logger.info(f"Заказ #{order_id} пропущен (статус: {order.status if order else 'None'})")
                return

            # ==================== РЕЗЕРВИРОВАНИЕ ====================
            reserved = await self.delivery_service.reserve_accounts_for_order(session, order_id)

            if not reserved:
                order.status = OrderStatus.PARTIAL.value
                await session.commit()
                return

            # ==================== СБОРКА АРХИВА ====================
            archive_bytes, password = await self.delivery_service.build_order_archive(session, order_id)

            if not archive_bytes:
                order.status = OrderStatus.PARTIAL.value
                await session.commit()
                return

            # ==================== ОТПРАВКА ПОЛЬЗОВАТЕЛЮ ====================
            sent = await self._send_order_to_user(order.user_id, order_id, archive_bytes, password)

            # ==================== ФИНАЛЬНЫЙ СТАТУС ====================
            order.status = OrderStatus.COMPLETED.value if sent else OrderStatus.PARTIAL.value
            await session.commit()

            logger.info(f"✅ Заказ #{order_id} успешно обработан и завершён")

        except Exception as e:
            logger.exception(f"Критическая ошибка обработки заказа #{order_id}")
            # Возвращаем заказ в конец очереди
            await redis_client.rpush(self.queue_key, str(order_id))
            await asyncio.sleep(5)

        finally:
            # ==================== СНЯТИЕ БЛОКИРОВКИ ====================
            await redis_client.delete(lock_key)

    async def _send_order_to_user(self, user_id: int, order_id: int, archive_bytes: bytes, password: str):
        """Надёжная отправка заказа пользователю"""
        from app.bot.bot_instance import bot

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Отправка архива
                await bot.send_document(
                    chat_id=user_id,
                    document=BufferedInputFile(archive_bytes, filename=f"order_{order_id}.zip"),
                    caption=f"✅ Заказ #{order_id} готов!\n\n"
                            f"📦 Архив с аккаунтами",
                    disable_notification=False
                )

                await asyncio.sleep(1.5)

                # Отправка пароля
                await bot.send_message(
                    user_id,
                    f"🔑 Пароль архива: `{password}`\n\n"
                    f"⚠️ Сохраните пароль! Без него открыть архив невозможно.",
                    parse_mode="Markdown"
                )

                logger.info(f"Заказ #{order_id} успешно отправлен пользователю {user_id}")
                return True

            except Exception as e:
                logger.error(f"Попытка {attempt + 1}/{max_retries} отправки заказа {order_id} не удалась: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3 * (attempt + 1))  # экспоненциальная задержка
                else:
                    logger.critical(f"Не удалось отправить заказ {order_id} после {max_retries} попыток")
                    # Здесь можно добавить уведомление админу
                    try:
                        await bot.send_message(
                            settings.ADMIN_IDS[0],
                            f"❌ Не удалось доставить заказ #{order_id} пользователю {user_id}"
                        )
                    except:
                        pass
                    return False