# scripts/sync_accounts_with_s3.py
import asyncio
from app.db.engine import async_session
from app.services.order_delivery import OrderDeliveryService
from app.db.models import AccountItem
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


async def sync_accounts():
    delivery = OrderDeliveryService()
    async with async_session() as session:
        stmt = select(AccountItem).where(AccountItem.status.in_(["free", "reserved"]))
        result = await session.execute(stmt)
        accounts = result.scalars().all()

        print(f"Проверяем {len(accounts)} аккаунтов...")

        for acc in accounts:
            exists = await delivery._account_exists_in_s3(acc.s3_prefix)
            if not exists and acc.status != "missing":
                acc.status = "missing"
                print(f"→ Помечен missing: {acc.s3_prefix}")

        await session.commit()
        print("Синхронизация завершена.")


if __name__ == "__main__":
    asyncio.run(sync_accounts())