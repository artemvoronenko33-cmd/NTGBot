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
        """
        Поставить заказ в очередь только если его там ещё нет.
        Используем LPOS (если доступно) для быстрого поиска; при отсутствии support — fallback на LRANGE.
        """
        oid = str(order_id)
        try:
            # LPOS возвращает позицию или None
            pos = await redis_client.lpos(self.queue_key, oid)
            if pos is not None:
                logger.debug(f"Order #{order_id} already present in queue at position {pos}, skipping enqueue")
                return
        except Exception:
            # fallback: читаем список (costly), но безопасно
            try:
                existing = await redis_client.lrange(self.queue_key, 0, -1)
                if oid in existing:
                    logger.debug(f"Order #{order_id} already present in queue (fallback), skipping enqueue")
                    return
            except Exception as ex:
                logger.warning(f"Failed to check existing queue entries for dedupe: {ex}")
                # продолжим попытку поставить в очередь

        try:
            await redis_client.rpush(self.queue_key, oid)
            logger.info(f"Заказ #{order_id} добавлен в очередь")
        except Exception as ex:
            logger.error(f"Failed to enqueue order #{order_id} to Redis: {ex}")

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
            logger.debug(f"Popped order_id_str from Redis queue '{self.queue_key}': {order_id_str}")
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

            if not order:
                logger.info(f"Заказ #{order_id} не найден, пропускаем")
                return

            # Разрешаем обрабатывать заказы со статусами PAID, PARTIAL и PROCESSING
            if order.status not in [OrderStatus.PAID.value, OrderStatus.PARTIAL.value, OrderStatus.PROCESSING.value]:
                logger.info(f"Заказ #{order_id} пропущен (неподдерживаемый статус: {order.status})")
                return

            # ==================== РЕЗЕРВИРОВАНИЕ (только если ещё не в PROCESSING) ====================
            if order.status in [OrderStatus.PAID.value, OrderStatus.PARTIAL.value]:
                logger.info(f"Заказ #{order_id} в статусе {order.status} — запускаем резервирование")
                reserved = await self.delivery_service.reserve_accounts_for_order(session, order_id)
            else:
                # order.status == PROCESSING — предполагаем, что резервирование уже выполнено ранее
                logger.info(f"Заказ #{order_id} уже в PROCESSING — пропускаем шаг резервирования")
                reserved = True

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