# app/bot/handlers_admin.py
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from config import settings  # или откуда импортируется settings
from sqlalchemy import text
from app.bot.keyboards import get_admin_menu, get_cancel_kb


router = Router(name="admin_router")

@router.message(Command("admin"))
async def cmd_worker(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user or not getattr(user, 'is_worker', False):
        await message.answer("⛔ У вас нет доступа к панели работника.")
        return

    await message.answer(
        "👷 Добро пожаловать в панель работника!\n\n"
        "Выберите действие:",
        reply_markup=get_admin_menu()
    )

@router.message(Command("addworker"))
async def cmd_addworker(message: Message, session: AsyncSession):
    """Назначить пользователя работником"""
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("⛔ У вас нет прав администратора.")
        return

    try:
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "❌ Использование:\n"
                "`/addworker <user_id>`\n\n"
                "Пример: `/addworker 726313576`",
                parse_mode="Markdown"
            )
            return

        target_id = int(parts[1])

        user = await session.get(User, target_id)

        if not user:
            user = User(
                id=target_id,
                is_worker=True
            )
            session.add(user)
            action = "создан и назначен"
        else:
            if user.is_worker:
                await message.answer(f"✅ Пользователь `{target_id}` уже является работником.")
                return
            user.is_worker = True
            action = "назначен"

        await session.commit()

        await message.answer(
            f"✅ Пользователь `{target_id}` успешно **{action}** работником.\n"
            f"Теперь он может использовать команду /worker",
            parse_mode="Markdown"
        )

    except ValueError:
        await message.answer("❌ User ID должен быть числом.")
    except Exception as e:
        await session.rollback()
        await message.answer(f"❌ Произошла ошибка: {str(e)}")


@router.message(Command("delworker"))
async def cmd_delworker(message: Message, session: AsyncSession):
    """Снять статус работника"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    try:
        target_id = int(message.text.split()[1])
        user = await session.get(User, target_id)

        if user and user.is_worker:
            user.is_worker = False
            await session.commit()
            await message.answer(f"✅ У пользователя `{target_id}` снят статус работника.")
        else:
            await message.answer("❌ Пользователь не найден или не является работником.")
    except Exception:
        await message.answer("❌ Использование: `/delworker <user_id>`")


@router.message(Command("workers"))
async def cmd_workers(message: Message, session: AsyncSession):
    """Список всех работников"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    from sqlalchemy import text

    result = await session.execute(
        text("SELECT id, username, balance FROM users WHERE is_worker = true ORDER BY id")
    )
    workers = result.fetchall()

    if not workers:
        await message.answer("👷 Пока нет работников.")
        return

    lines = ["👷 **Список работников:**\n"]
    for w in workers:
        username = w.username or "—"
        balance = w.balance or 0
        # Используем безопасный формат без MarkdownV2 проблем
        lines.append(f"• {w.id} | {username} | Баланс: {balance}₽")

    text_msg = "\n".join(lines)

    await message.answer(text_msg, parse_mode=None)