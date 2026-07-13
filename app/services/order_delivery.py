# app/services/order_delivery.py
import logging
import zipfile
import tempfile
import os
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.models import Order, OrderItem, AccountItem, OrderStatus
from app.services.storage import StorageService  # существующий

logger = logging.getLogger(__name__)


class OrderDeliveryService:
    def __init__(self):
        self.storage = StorageService()

    async def reserve_accounts_for_order(self, session: AsyncSession, order_id: int) -> bool:
        """Резервирует аккаунты для заказа (без новой транзакции)"""
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
            ).with_for_update().limit(needed)

            result = await session.execute(stmt)
            available_accounts = result.scalars().all()

            reserved_count = len(available_accounts)

            if reserved_count > 0:
                item.reserved_accounts = item.reserved_accounts or []
                item.reserved_accounts.extend([acc.s3_prefix for acc in available_accounts])

                for acc in available_accounts:
                    acc.is_reserved = True
                    acc.reserved_for_order_id = order_id
                    acc.reserved_at = datetime.utcnow()
                    acc.status = "reserved"

                item.delivered_quantity = (item.delivered_quantity or 0) + reserved_count

            delivery_info["items"][str(item.product_id)] = {
                "needed": item.quantity,
                "delivered": item.delivered_quantity,
                "product_name": item.product_name
            }

            if reserved_count < needed:
                success = False

        # Общий прогресс
        total_needed = sum(i.quantity for i in order.items)
        total_delivered = sum((i.delivered_quantity or 0) for i in order.items)
        delivery_info["overall"] = int((total_delivered / total_needed) * 100) if total_needed > 0 else 100

        order.delivery_info = delivery_info

        if success and total_delivered >= total_needed:
            order.status = OrderStatus.PROCESSING.value
        else:
            order.status = OrderStatus.PARTIAL.value

        return success

    async def build_order_archive(self, session: AsyncSession, order_id: int) -> Tuple[Optional[bytes], str]:
        """Собирает архив заказа"""
        order = await session.get(Order, order_id)
        if not order:
            return None, ""

        password = os.urandom(12).hex()
        archive_name = f"order_{order_id}.zip"

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                archive_path = os.path.join(tmp_dir, archive_name)

                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
                    zipf.setpassword(password.encode('utf-8'))

                    for item in order.items:
                        for s3_prefix in (item.reserved_accounts or []):
                            local_files = await self._download_account_from_s3(s3_prefix)
                            for rel_path, data in local_files.items():
                                zipf.writestr(rel_path, data)

                with open(archive_path, 'rb') as f:
                    archive_bytes = f.read()

            # Обновляем заказ
            if not order.delivery_info:
                order.delivery_info = {}
            order.delivery_info["password"] = password
            order.status = OrderStatus.COMPLETED.value

        except Exception as e:
            logger.error(f"Failed to build archive for order {order_id}: {e}", exc_info=True)
            return None, ""

        # Удаление из S3 — вне транзакции
        try:
            for item in order.items:
                for s3_prefix in (item.reserved_accounts or []):
                    response = self.storage.s3_client.list_objects_v2(
                        Bucket=self.storage.bucket,
                        Prefix=s3_prefix
                    )
                    if 'Contents' in response:
                        objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                        self.storage.s3_client.delete_objects(
                            Bucket=self.storage.bucket,
                            Delete={'Objects': objects_to_delete}
                        )
                        logger.info(f"Deleted account folder: {s3_prefix}")
        except Exception as e:
            logger.error(f"Failed to delete S3 accounts for order {order_id}: {e}")

        return archive_bytes, password

    async def _download_account_from_s3(self, s3_prefix: str) -> Dict[str, bytes]:
        """Скачивает аккаунт с сохранением структуры папки"""
        files = {}
        try:
            response = self.storage.s3_client.list_objects_v2(
                Bucket=self.storage.bucket,
                Prefix=s3_prefix
            )

            account_folder_name = s3_prefix.strip('/').split('/')[-1]  # имя папки аккаунта

            for obj in response.get('Contents', []):
                key = obj['Key']
                # rel_path = account_folder_name / оставшаяся часть
                rel_path_from_prefix = key[len(s3_prefix):].lstrip('/')
                full_rel_path = f"{account_folder_name}/{rel_path_from_prefix}" if rel_path_from_prefix else account_folder_name

                file_obj = self.storage.s3_client.get_object(
                    Bucket=self.storage.bucket, Key=key
                )
                files[full_rel_path] = file_obj['Body'].read()

            logger.info(f"Downloaded account folder '{account_folder_name}' with {len(files)} files")
        except Exception as e:
            logger.error(f"Failed to download {s3_prefix}: {e}")

        return files