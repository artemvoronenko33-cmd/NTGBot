import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import os
from io import BytesIO
import zipfile
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self):
        self.storage_type = os.getenv("STORAGE_TYPE", "s3").lower()
        self.bucket = os.getenv("DO_SPACES_BUCKET")

        if self.storage_type == "s3":
            try:
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=os.getenv("DO_SPACES_ENDPOINT"),
                    aws_access_key_id=os.getenv("DO_SPACES_ACCESS_KEY"),
                    aws_secret_access_key=os.getenv("DO_SPACES_SECRET_KEY"),
                    region_name=os.getenv("DO_SPACES_REGION", "fra1")
                )
                logger.info("✅ DigitalOcean Spaces подключен успешно")
            except Exception as e:
                logger.error(f"❌ Ошибка подключения к Spaces: {e}")
                self.storage_type = "local"  # fallback
        else:
            self.local_path = os.getenv("LOCAL_STORAGE_PATH", "data/accounts")
            os.makedirs(self.local_path, exist_ok=True)
            logger.info(f"📁 Локальное хранилище: {self.local_path}")

    async def upload_file(self, file_content: bytes, filename: str, category: str = "default") -> str:
        """Загружает файл и возвращает ключ (s3_key или локальный путь)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = filename.replace(" ", "_")
        key = f"accounts/{category}/{timestamp}_{safe_filename}"

        try:
            if self.storage_type == "s3":
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=file_content,
                    ACL='private'
                )
                logger.info(f"📤 Загружен в Spaces: {key}")
                return key
            else:
                # Локальный режим
                local_dir = os.path.join(self.local_path, category)
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(local_dir, f"{timestamp}_{safe_filename}")
                with open(local_path, "wb") as f:
                    f.write(file_content)
                return local_path
        except Exception as e:
            logger.error(f"Ошибка загрузки файла {filename}: {e}")
            raise

    async def download_file(self, file_key: str) -> bytes:
        """Скачивает файл по ключу"""
        try:
            if self.storage_type == "s3":
                response = self.s3_client.get_object(Bucket=self.bucket, Key=file_key)
                return response['Body'].read()
            else:
                with open(file_key, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.error(f"Ошибка скачивания {file_key}: {e}")
            raise

    async def create_zip_archive(self, items: List[Dict], order_id: int) -> BytesIO:
        """Создаёт zip в памяти из списка аккаунтов"""
        zip_buffer = BytesIO()
        archive_name = f"order_{order_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
            for item in items:
                try:
                    file_bytes = await self.download_file(item['file_key'])
                    zip_file.writestr(item['file_name'], file_bytes)
                except Exception as e:
                    logger.warning(f"Не удалось добавить файл {item.get('file_name')}: {e}")

        zip_buffer.seek(0)
        logger.info(f"📦 Создан архив для заказа {order_id} ({len(items)} файлов)")
        return zip_buffer