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
            ).with_for_update().limit(needed * 6)

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
                    await session.delete(acc)
                    logger.warning(f"Пустой аккаунт (0 файлов) → lost_empty и удалён: {acc.s3_prefix}")

            reserved_count = len(really_available)

            if reserved_count > 0:
                item.reserved_accounts = item.reserved_accounts or []
                for acc in really_available[:needed]:
                    logger.info(f"Резервируем: {acc.s3_prefix}")
                    item.reserved_accounts.append(acc.s3_prefix)

                    acc.is_reserved = True
                    acc.reserved_for_order_id = order_id
                    acc.reserved_at = datetime.utcnow()
                    acc.status = "reserved"

                item.delivered_quantity = (item.delivered_quantity or 0) + min(reserved_count, needed)

            delivery_info["items"][str(item.product_id)] = {
                "needed": item.quantity,
                "delivered": item.delivered_quantity,
                "product_name": item.product_name,
                "reserved_count": reserved_count
            }

            if reserved_count < needed:
                success = False

        total_needed = sum(i.quantity for i in order.items)
        total_delivered = sum((i.delivered_quantity or 0) for i in order.items)
        delivery_info["overall"] = int((total_delivered / total_needed) * 100) if total_needed > 0 else 100
        order.delivery_info = delivery_info

        if success and total_delivered >= total_needed:
            order.status = OrderStatus.PROCESSING.value
        else:
            order.status = OrderStatus.PARTIAL.value

        # Пересчёт общего прогресса
        total_needed = sum(i.quantity for i in order.items)
        total_delivered = sum((i.delivered_quantity or 0) for i in order.items)
        delivery_info["overall"] = int((total_delivered / total_needed) * 100) if total_needed > 0 else 100

        order.delivery_info = delivery_info

        await session.commit()  # <--- добавить
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
                        category_name = "Без_категории"
                        try:
                            # Теперь категория должна быть загружена
                            if item.product and item.product.category:
                                category_name = item.product.category.name
                            elif item.product and item.product.name:
                                category_name = item.product.name.split()[0]
                            elif getattr(item, 'product_name', None):
                                category_name = item.product_name.split()[0]
                        except Exception as e:
                            logger.warning(f"Проблема с категорией для item {item.id}: {e}")

                        safe_category = "".join(
                            c if c.isalnum() or c in " _-()" else "_"
                            for c in category_name
                        ).strip() or "uncategorized"

                        for s3_prefix in (getattr(item, 'reserved_accounts', []) or []):
                            logger.info(f"Order {order_id} → Категория '{category_name}' → {s3_prefix}")

                            local_files = await self._download_account_from_s3(s3_prefix)
                            if not local_files:
                                logger.error(f"Аккаунт пуст: {s3_prefix}")
                                continue

                            for rel_path, data in local_files.items():
                                full_rel_path = f"{safe_category}/{rel_path}"
                                zipf.writestr(full_rel_path, data)
                                total_files += 1

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

        # Очистка S3
        try:
            for item in order.items:
                for s3_prefix in (getattr(item, 'reserved_accounts', []) or []):
                    prefix = s3_prefix.rstrip('/') + '/'
                    response = self.storage.s3_client.list_objects_v2(
                        Bucket=self.storage.bucket, Prefix=prefix
                    )
                    if 'Contents' in response:
                        objects = [{'Key': obj['Key']} for obj in response['Contents']]
                        self.storage.s3_client.delete_objects(
                            Bucket=self.storage.bucket, Delete={'Objects': objects}
                        )
        except Exception as e:
            logger.warning(f"Ошибка очистки S3 для заказа {order_id}: {e}")

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