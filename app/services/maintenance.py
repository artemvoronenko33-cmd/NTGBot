from sqlalchemy import select, update
from app.db.engine import async_session
from app.db.models.system_settings import SystemSettings


class MaintenanceService:
    @staticmethod
    async def get_settings():
        async with async_session() as session:
            result = await session.execute(select(SystemSettings))
            return result.scalar_one_or_none()

    @staticmethod
    async def enable_maintenance(message: str = None, updated_by: int = None, until=None):
        async with async_session() as session:
            settings = await session.execute(select(SystemSettings))
            settings = settings.scalar_one_or_none()

            if not settings:
                settings = SystemSettings()
                session.add(settings)

            settings.maintenance_mode = True
            if message:
                settings.maintenance_message = message
            settings.maintenance_until = until
            settings.updated_by = updated_by

            await session.commit()
            return True

    @staticmethod
    async def disable_maintenance():
        async with async_session() as session:
            await session.execute(
                update(SystemSettings)
                .where(SystemSettings.id == 1)
                .values(maintenance_mode=False, maintenance_until=None)
            )
            await session.commit()
            return True