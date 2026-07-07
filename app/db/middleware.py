# app/db/middleware.py

from aiogram.types import Message, CallbackQuery
from app.services.maintenance import MaintenanceService
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable
#from sqlalchemy.ext.asyncio import AsyncSession
from config import settings  # ваш config с ADMIN_IDS

from app.db.session import AsyncSessionLocal   # или как у тебя называется

class DBSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)


class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id

            # Пропускаем админов всегда
            if user_id in settings.ADMIN_IDS:
                return await handler(event, data)

            # Проверяем maintenance для обычных пользователей
            settings_obj = await MaintenanceService.get_settings()
            if settings_obj and settings_obj.maintenance_mode:
                msg = settings_obj.maintenance_message or "Ведутся технические работы."
                if isinstance(event, Message):
                    await event.answer(msg)
                elif isinstance(event, CallbackQuery):
                    await event.answer(msg, show_alert=True)
                return  # блокируем

        return await handler(event, data)