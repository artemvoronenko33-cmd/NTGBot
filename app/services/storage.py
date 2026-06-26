# app/services/storage.py
import boto3
from botocore.exceptions import ClientError
import os
import zipfile
import tempfile
from io import BytesIO
from datetime import datetime
from typing import List, Dict
import logging
import re
import shutil

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self):
        self.storage_type = os.getenv("STORAGE_TYPE", "s3").lower()
        self.bucket = os.getenv("DO_SPACES_BUCKET")

        if self.storage_type == "s3":
            self.s3_client = boto3.client(
                's3',
                endpoint_url=os.getenv("DO_SPACES_ENDPOINT"),
                aws_access_key_id=os.getenv("DO_SPACES_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("DO_SPACES_SECRET_KEY"),
                region_name=os.getenv("DO_SPACES_REGION", "fra1")
            )
            logger.info("✅ Connected to DigitalOcean Spaces")
        else:
            self.local_path = os.getenv("LOCAL_STORAGE_PATH", "data/accounts")
            os.makedirs(self.local_path, exist_ok=True)

    def _generate_slug(self, name: str) -> str:
        """Генерирует slug для категории/продукта"""
        slug = re.sub(r'[^a-z0-9а-яё]+', '-', name.lower().strip())
        return re.sub(r'-+', '-', slug).strip('-')

    async def unpack_and_upload_accounts(
            self,
            zip_content: bytes,
            product_id: int,
            category_name: str,  # Название категории
            product_name: str,  # Название продукта
            worker_id: int
    ) -> List[Dict]:
        """
        Распаковывает ZIP и загружает аккаунты с правильной структурой:
        accounts/{category_slug}/{product_slug}/YYYYMMDD_HHMMSS_AccountName/
        """
        uploaded_accounts = []
        category_slug = self._generate_slug(category_name)
        product_slug = self._generate_slug(product_name)
        date_prefix = datetime.now().strftime("%Y%m%d")

        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "temp.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_content)

            extract_path = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_path, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            # Обрабатываем каждую папку внутри архива как отдельный аккаунт
            for item in os.listdir(extract_path):
                item_path = os.path.join(extract_path, item)
                if not os.path.isdir(item_path):
                    continue

                account_name = item
                timestamp = datetime.now().strftime("%H%M%S")

                # Итоговая структура:
                # accounts/{category_slug}/{product_slug}/{date}_{time}_{account_name}/
                s3_prefix = f"accounts/{category_slug}/{product_slug}/{date_prefix}_{timestamp}_{account_name}/"

                file_count = 0
                total_size = 0

                for root, _, files in os.walk(item_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, item_path)
                        s3_key = s3_prefix + rel_path

                        with open(file_path, "rb") as f:
                            file_data = f.read()

                        if self.storage_type == "s3":
                            self.s3_client.put_object(
                                Bucket=self.bucket,
                                Key=s3_key,
                                Body=file_data,
                                ACL='private'
                            )

                        file_count += 1
                        total_size += len(file_data)

                uploaded_accounts.append({
                    "s3_prefix": s3_prefix,
                    "account_name": account_name,
                    "file_count": file_count,
                    "total_size": total_size,
                    "product_id": product_id,
                    "added_by_worker_id": worker_id,
                    "category_slug": category_slug,
                    "product_slug": product_slug
                })

                logger.info(f"✅ Загружен аккаунт: {account_name} ({file_count} файлов) → {s3_prefix}")

        return uploaded_accounts