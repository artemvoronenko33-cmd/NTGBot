# app/services/order_delivery.py
import logging
import zipfile
import tempfile
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Order, OrderItem, AccountItem, OrderStatus, Product
from app.services.redis_cart import redis_client
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


class OrderDeliveryService:
    def __init__(self):
        self.storage = StorageService()

    async def _get_file_count(self, s3_prefix: str) -> int:
        """Считает только файлы размером > 0 байт"""
        try:
            prefix = s3_prefix.rstrip('/') + '/'
            count = 0
            continuation_token = None

            while True:
                kwargs = {
                    'Bucket': self.storage.bucket,
                    'Prefix': prefix,
                    'MaxKeys': 1000
                }
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token

                response = self.storage.s3_client.list_objects_v2(**kwargs)

                for obj in response.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('/') or key == prefix:
                        continue
                    # Проверяем размер
                    if obj.get('Size', 0) > 0:
                        count += 1

                if not response.get('IsTruncated', False):
                    break
                continuation_token = response.get('NextContinuationToken')

            logger.info(f"Аккаунт {s3_prefix} содержит {count} непустых файлов")
            return count
        except Exception as e:
            logger.error(f"File count error {s3_prefix}: {e}")
            return 0

    async def _move_to_lost_empty(self, s3_prefix: str):
        """Перенос пустой папки"""
        try:
            old_prefix = s3_prefix.rstrip('/') + '/'
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_name = old_prefix.strip('/').split('/')[-1]
            new_prefix = f"lost_empty/{timestamp}_{folder_name}/"

            response = self.storage.s3_client.list_objects_v2(
                Bucket=self.storage.bucket, Prefix=old_prefix
            )
            contents = response.get('Contents', [])

            for obj in contents:
                old_key = obj['Key']
                new_key = new_prefix + old_key[len(old_prefix):]

                self.storage.s3_client.copy_object(
                    Bucket=self.storage.bucket,
                    CopySource={'Bucket': self.storage.bucket, 'Key': old_key},
                    Key=new_key
                )
                self.storage.s3_client.delete_object(Bucket=self.storage.bucket, Key=old_key)

            logger.info(f"✅ Перемещено в lost_empty: {new_prefix}")
            return True
        except Exception as e:
            logger.error(f"Move to lost_empty failed {s3_prefix}: {e}")
            return False

    async def _delete_prefix_completely(self, s3_prefix: str) -> bool:
        """
        Полностью удаляет все объекты по префиксу в S3 (с учетом пагинации)
        и пытается удалить возможный маркер-папку (ключ, оканчивающийся на '/').
        """
        try:
            prefix = s3_prefix.rstrip('/') + '/'
            continuation_token = None

            while True:
                kwargs = {
                    'Bucket': self.storage.bucket,
                    'Prefix': prefix,
                    'MaxKeys': 1000
                }
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token

                response = self.storage.s3_client.list_objects_v2(**kwargs)
                contents = response.get('Contents', [])

                if not contents:
                    break

                # Удаляем найденные объекты батчами (delete_objects поддерживает до 1000)
                objects_to_delete = [{'Key': obj['Key']} for obj in contents]
                try:
                    self.storage.s3_client.delete_objects(
                        Bucket=self.storage.bucket,
                        Delete={'Objects': objects_to_delete}
                    )
                except Exception as ex:
                    logger.warning(f"Failed to delete some objects for prefix {prefix}: {ex}")

                if not response.get('IsTruncated', False):
                    break

                continuation_token = response.get('NextContinuationToken')

            # Попытка удалить маркер-папку (например 'prefix/')
            try:
                folder_key = prefix
                self.storage.s3_client.delete_object(Bucket=self.storage.bucket, Key=folder_key)
            except Exception:
                # Не критично, просто логируем на debug
                logger.debug(f"No explicit folder object to delete for {prefix}")

            logger.info(f"Deleted all objects under prefix {prefix}")
            return True
        except Exception as e:
            logger.warning(f"Error deleting prefix {s3_prefix}: {e}")
            return False

    async def reserve_accounts_for_order(self, session: AsyncSession, order_id: int) -> bool:
        order = await session.get(Order, order_id)
        if not order:
            return False

        success = True
        delivery_info = order.delivery_info or {"overall": 0, "items": {}}

        for item in order.items:
            needed = item.quantity - (item.delivered_quantity or 0)
            if needed <= 0:
                continue

            stmt = select(AccountItem).where(
                AccountItem.product_id == item.product_id,
                AccountItem.is_reserved == False,
                AccountItem.status == "free"
            ).with_for_update(skip_locked=True).limit(needed * 6)

            result = await session.execute(stmt)
            candidates = result.scalars().all()

            logger.info(f"Order {order_id} | Product {item.product_id}: найдено кандидатов {len(candidates)}")

            really_available = []
            for acc in candidates:
                file_count = await self._get_file_count(acc.s3_prefix)
                if file_count > 0:
                    really_available.append(acc)
                else:
                    await self._move_to_lost_empty(acc.s3_prefix)
                    try:
                        await session.delete(acc)
                    except Exception as ex:
                        logger.warning(f"Failed to delete empty AccountItem {acc.s3_prefix}: {ex}")
                    logger.warning(f"Пустой аккаунт (0 файлов) → lost_empty и удалён: {acc.s3_prefix}")

            reserved_count = len(really_available)

            if reserved_count > 0:
                item.reserved_accounts = item.reserved_accounts or []
                reserved_assigned = 0
                for acc in really_available[:needed]:
                    logger.info(f"Резервируем: {acc.s3_prefix}")

                    item.reserved_accounts.append(acc.s3_prefix)

                    acc.is_reserved = True
                    acc.reserved_for_order_id = order_id
                    acc.reserved_at = datetime.utcnow()
                    acc.status = "reserved"

                    # Немедленно flush — чтобы изменения видны другим транзакциям/селекторам
                    try:
                        await session.flush()
                    except Exception as ex:
                        logger.warning(f"Flush failed after reserving {acc.s3_prefix}: {ex}")

                    logger.debug(f"Reserved AccountItem {acc.s3_prefix} for order {order_id}")
                    reserved_assigned += 1

                # увеличиваем delivered_quantity на реально назначенное количество
                item.delivered_quantity = (item.delivered_quantity or 0) + reserved_assigned

            delivery_info["items"][str(item.product_id)] = {
                "needed": item.quantity,
                "delivered": item.delivered_quantity,
                "product_name": item.product_name,
                "reserved_count": reserved_count
            }

            if reserved_count < needed:
                success = False

        # Пересчёт общего прогресса
        total_needed = sum(i.quantity for i in order.items)
        total_delivered = sum((i.delivered_quantity or 0) for i in order.items)
        delivery_info["overall"] = int((total_delivered / total_needed) * 100) if total_needed > 0 else 100
        order.delivery_info = delivery_info

        # Устанавливаем статус и при необходимости ставим заказ в Redis-очередь
        if success and total_delivered >= total_needed:
            order.status = OrderStatus.PROCESSING.value
            # Сначала сохраняем изменения статуса в БД
            await session.commit()
            # Попытка поместить заказ в Redis-очередь для обработки архива
            queue_key = "order:processing:queue"
            try:
                await redis_client.rpush(queue_key, str(order.id))
                logger.info(f"Order {order.id} enqueued to Redis queue {queue_key}")
            except Exception as ex:
                # Не фатально — логируем и продолжаем. Заказ уже в состоянии PROCESSING в БД.
                logger.warning(f"Failed to enqueue order {order.id} to Redis: {ex}")
        else:
            order.status = OrderStatus.PARTIAL.value
            await session.commit()

        return success



    async def build_order_archive(self, session: AsyncSession, order_id: int) -> Tuple[Optional[bytes], str]:
        """Собирает архив с чёткой категорией из БД"""
        # Правильная предзагрузка всех связей
        stmt = select(Order).where(Order.id == order_id).options(
            selectinload(Order.items)
            .selectinload(OrderItem.product)
            .selectinload(Product.category)
        )
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            return None, ""

        password = os.urandom(12).hex()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                archive_path = os.path.join(tmp_dir, f"order_{order_id}.zip")

                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
                    zipf.setpassword(password.encode('utf-8'))

                    total_files = 0

                    for item in order.items:
                        # 1) Получаем категорию (как раньше)
                        category_name = "Без_категории"
                        try:
                            if item.product and item.product.category:
                                category_name = item.product.category.name
                            elif item.product and item.product.name:
                                category_name = item.product.name.split()[0]
                            elif getattr(item, 'product_name', None):
                                category_name = item.product_name.split()[0]
                        except Exception as e:
                            logger.warning(f"Проблема с категорией для item {item.id}: {e}")

                        # 2) Получаем имя продукта (для второго уровня)
                        product_name_raw = "product"
                        try:
                            if item.product and getattr(item.product, "name", None):
                                product_name_raw = item.product.name
                            elif getattr(item, "product_name", None):
                                product_name_raw = item.product_name
                        except Exception:
                            product_name_raw = "product"

                        # 3) Создаём безопасные имена для папок
                        safe_category = "".join(
                            c if c.isalnum() or c in " _-()" else "_"
                            for c in category_name
                        ).strip() or "uncategorized"

                        safe_product = "".join(
                            c if c.isalnum() or c in " _-()" else "_"
                            for c in product_name_raw
                        ).strip() or "product"

                        # 4) Обрабатываем каждый зарезервированный префикс (аккаунт)
                        # Обрабатываем каждый зарезервированный префикс (аккаунт)
                        prefixes = list(getattr(item, 'reserved_accounts', []) or [])
                        for idx, s3_prefix in enumerate(prefixes):
                            logger.info(
                                f"Order {order_id} → Category '{category_name}' | Product '{product_name_raw}' → {s3_prefix}")

                            local_files = await self._download_account_from_s3(s3_prefix)
                            if not local_files:
                                logger.error(f"Аккаунт пуст или не удалось скачать: {s3_prefix}")
                                continue

                            # Определяем оригинальное имя папки аккаунта (возвращается в ключах local_files)
                            first_key = next(iter(local_files.keys()), None)
                            if first_key and '/' in first_key:
                                original_account_folder = first_key.split('/', 1)[0]
                            else:
                                # fallback на кусок из s3_prefix
                                original_account_folder = s3_prefix.rstrip('/').split('/')[-1] or f"acct_{idx}"

                            # Делаем уникальный маркер для папки аккаунта, чтобы избежать перезаписи файлов
                            uniq_suffix = s3_prefix.rstrip('/').split('/')[-1]
                            unique_account_folder = f"{original_account_folder}_{uniq_suffix}_{idx}"

                            logger.debug(
                                f"Using unique account folder '{unique_account_folder}' for prefix {s3_prefix}")

                            files_added = 0
                            for rel_path, data in local_files.items():
                                # rel_path обычно "account_folder_name/..." — убираем оригинальную папку и подставляем уникальную
                                parts = rel_path.split('/', 1)
                                tail = parts[1] if len(parts) > 1 else parts[0]
                                full_rel_path = f"{safe_category}/{safe_product}/{unique_account_folder}/{tail}"
                                logger.debug(f"Adding to zip: {full_rel_path} (from {s3_prefix})")
                                zipf.writestr(full_rel_path, data)
                                total_files += 1
                                files_added += 1

                            logger.info(
                                f"Added {files_added} files from {s3_prefix} into zip as {unique_account_folder}")

                    if total_files == 0:
                        logger.error(f"Не удалось собрать файлы для заказа {order_id}")
                        return None, ""

                with open(archive_path, 'rb') as f:
                    archive_bytes = f.read()

            if not order.delivery_info:
                order.delivery_info = {}
            order.delivery_info["password"] = password
            order.status = OrderStatus.COMPLETED.value

            await session.commit()

        except Exception as e:
            logger.error(f"Failed to build archive for order {order_id}: {e}", exc_info=True)
            await session.rollback()
            return None, ""

        # Очистка S3 и обновление записей AccountItem в БД
        try:
            for item in order.items:
                prefixes = list(getattr(item, 'reserved_accounts', []) or [])
                for s3_prefix in prefixes:
                    # Удаляем объекты по префиксу (с пагинацией)
                    deleted = await self._delete_prefix_completely(s3_prefix)
                    if not deleted:
                        logger.warning(f"Не удалось полностью удалить префикс {s3_prefix} для заказа {order_id}")

                    # Обновляем запись AccountItem — помечаем как delivered и снимаем резерв
                    try:
                        stmt = select(AccountItem).where(AccountItem.s3_prefix == s3_prefix)
                        res = await session.execute(stmt)
                        acc = res.scalar_one_or_none()
                        if acc:
                            acc.status = "delivered"
                            acc.is_reserved = False
                            acc.reserved_for_order_id = None
                            acc.reserved_at = None
                            # Не удаляем запись, чтобы сохранить метаданные; при желании можно вместо этого удалить
                            await session.flush()
                    except Exception as ex:
                        logger.warning(f"DB update failed for AccountItem {s3_prefix}: {ex}")

                # Очистим список зарезервированных префиксов и установим delivered_quantity
                item.reserved_accounts = []
                item.delivered_quantity = item.quantity
            # Сохраняем все изменения в БД
            await session.commit()
        except Exception as e:
            logger.warning(f"Ошибка очистки S3 / обновления DB для заказа {order_id}: {e}")
            try:
                await session.rollback()
            except Exception:
                pass

        return archive_bytes, password

    async def _download_account_from_s3(self, s3_prefix: str) -> Dict[str, bytes]:
        files = {}
        try:
            prefix = s3_prefix.rstrip('/') + '/'
            account_folder_name = prefix.strip('/').split('/')[-1]
            continuation_token = None

            while True:
                kwargs = {'Bucket': self.storage.bucket, 'Prefix': prefix, 'MaxKeys': 1000}
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token

                response = self.storage.s3_client.list_objects_v2(**kwargs)

                for obj in response.get('Contents', []):
                    key = obj['Key']
                    rel_path = key[len(prefix):]
                    if not rel_path or key.endswith('/'):
                        continue

                    # Пропускаем пустые файлы
                    if obj.get('Size', 0) == 0:
                        logger.warning(f"Пропущен пустой файл: {key}")
                        continue

                    full_rel_path = f"{account_folder_name}/{rel_path}"

                    file_obj = self.storage.s3_client.get_object(Bucket=self.storage.bucket, Key=key)
                    data = file_obj['Body'].read()
                    if len(data) > 0:
                        files[full_rel_path] = data

                if not response.get('IsTruncated', False):
                    break
                continuation_token = response.get('NextContinuationToken')

            logger.info(f"Downloaded {len(files)} files from {prefix}")

        except Exception as e:
            logger.error(f"Download error {s3_prefix}: {e}", exc_info=True)

        return files