# app/bot/hd_admin.py
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.menu_admin.cmd_admin import cmd_workers, cmd_queue_status, cmd_deficit, cmd_maintenance_off, cmd_maintenance_on, \
    cmd_full_health
from app.bot.menu_admin.kb_admin import get_main_admin_kb, get_orders_admin_kb, get_workers_admin_kb, get_bot_admin_kb
from app.bot.states import AdminStates
from app.db.engine import async_session
from app.db.models import User, Order, OrderItem, Payment, AccountItem
from app.db.models.order import OrderStatusHistory
from app.services.order_delivery import OrderDeliveryService
from config import settings  # или откуда импортируется settings
from sqlalchemy import select, delete

logger = logging.getLogger(__name__)
router = Router(name="admin_router")

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer(
        "🛠️ <b>Админ-панель</b>\nВыберите раздел:",
        reply_markup=get_main_admin_kb(),
        parse_mode="HTML"
    )
# ==================== ГЛАВНОЕ МЕНЮ ====================
@router.message(F.text == "📦 Заказы")
async def admin_orders_section(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await message.answer("📦 Раздел Заказы:", reply_markup=get_orders_admin_kb())

@router.message(F.text == "👷 Работники")
async def admin_workers_section(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await message.answer("👷 Раздел Работники:", reply_markup=get_workers_admin_kb())

@router.message(F.text == "🤖 Бот")
async def admin_bot_section(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await message.answer("🤖 Раздел Бот:", reply_markup=get_bot_admin_kb())

@router.message(F.text == "🔙 Выйти из админки")
async def admin_exit(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await message.answer("👋 Вы вышли из админ-панели.", reply_markup=ReplyKeyboardRemove())


# ==================== ПОДМЕНЮ ЗАКАЗЫ ====================
@router.message(F.text == "📋 Статус очереди")
async def admin_status(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await cmd_queue_status(message)

@router.message(F.text == "🔄 Синхронизация аккаунтов")
async def admin_sync(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await cmd_sync_accounts(message)

@router.message(F.text == "📉 Дефицит аккаунтов")
async def admin_deficit(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await cmd_deficit(message)

#@router.message(F.text == "📊 Зарезервированные")
#async def admin_reserved(message: Message):
#    if message.from_user.id not in settings.ADMIN_IDS: return
#    await message.answer("📊 Зарезервированные аккаунты (в разработке)")


# ==================== ПОДМЕНЮ РАБОТНИКИ ====================
@router.message(F.text == "👥 Список работников")
async def admin_workers_list(message: Message, session: AsyncSession):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await cmd_workers(message, session)   # ← передаём session


@router.message(F.text == "➕ Добавить работника")
async def admin_addworker_btn(message: Message, state: FSMContext):
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    await message.answer("Введите ID пользователя, которого хотите назначить работником:")
    await state.set_state(AdminStates.waiting_for_add_worker_id)
@router.message(AdminStates.waiting_for_add_worker_id)
async def process_add_worker_id(message: Message, state: FSMContext, session: AsyncSession):
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом. Попробуйте снова.")
        return

    try:
        user = await session.get(User, target_id)
        if not user:
            user = User(id=target_id, is_worker=True)
            session.add(user)
            action = "создан и назначен"
        else:
            if user.is_worker:
                await message.answer(f"✅ Пользователь `{target_id}` уже работник.")
                await state.clear()
                return
            user.is_worker = True
            action = "назначен"

        await session.commit()
        await message.answer(f"✅ Пользователь `{target_id}` успешно **{action}** работником.")
    except Exception as e:
        await session.rollback()
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()


@router.message(F.text == "➖ Удалить работника")
async def admin_delworker_btn(message: Message, state: FSMContext):
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    await message.answer("Введите ID пользователя, у которого хотите снять статус работника:")
    await state.set_state(AdminStates.waiting_for_del_worker_id)
@router.message(AdminStates.waiting_for_del_worker_id)
async def process_del_worker_id(message: Message, state: FSMContext, session: AsyncSession):
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    try:
        user = await session.get(User, target_id)
        if user and user.is_worker:
            user.is_worker = False
            await session.commit()
            await message.answer(f"✅ У пользователя `{target_id}` снят статус работника.")
        else:
            await message.answer("❌ Пользователь не найден или не является работником.")
    except Exception as e:
        await session.rollback()
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()


# ==================== ПОДМЕНЮ БОТ ====================
@router.message(F.text == "🩺 Health Check")
async def admin_health(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await cmd_full_health(message)

@router.message(F.text == "🛠️ Включить сервис")
async def admin_maintenance_on(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await cmd_maintenance_on(message)

@router.message(F.text == "✅ Выключить сервис")
async def admin_maintenance_off(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await cmd_maintenance_off(message)


# ==================== НАЗАД ====================
@router.message(F.text == "🔙 Назад")
async def admin_back(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS: return
    await message.answer("🛠️ Админ-панель:", reply_markup=get_main_admin_kb())


@router.message(Command("delete_orders"))
async def delete_orders(message: Message, session: AsyncSession, state: FSMContext):
    """Начать процесс удаления заказов"""
    await message.answer("Отправь ID заказов через запятую (например: 24,25,30)")
    await state.set_state("waiting_for_order_ids_to_delete")
@router.message(StateFilter("waiting_for_order_ids_to_delete"))
async def process_order_ids(message: Message, session: AsyncSession, state: FSMContext):
    try:
        order_ids = [int(x.strip()) for x in message.text.split(',') if x.strip().isdigit()]

        if not order_ids:
            await message.answer("Не найдено корректных ID.")
            await state.clear()
            return

        # Удаляем всё связанное
        await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
        await session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))  # ← Добавлено
        await session.execute(delete(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(order_ids)))

        # Удаляем заказы
        result = await session.execute(delete(Order).where(Order.id.in_(order_ids)))

        await session.commit()

        await message.answer(f"✅ Успешно удалено {result.rowcount} заказов (включая все связанные записи).")

    except Exception as e:
        await session.rollback()
        error_msg = str(e)[:200].replace('<', '&lt;').replace('>', '&gt;')  # экранируем
        await message.answer(f"Ошибка: {error_msg}")
    finally:
        await state.clear()


@router.callback_query(F.data =="sync_accounts")
async def cmd_sync_accounts(message: Message):
    """Синхронизация БД ↔ S3 + группировка зарезервированных аккаунтов по заказу"""
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("⛔ Нет доступа.")
        return

    await message.answer("🔄 Выполняю сверку и анализ...")

    try:
        delivery = OrderDeliveryService()
        deleted_count = 0
        reserved_by_order = {}  # order_id -> list of accounts

        async with async_session() as session:
            stmt = select(AccountItem).where(
                AccountItem.status.in_(["free", "reserved"])
            ).limit(500)

            result = await session.execute(stmt)
            accounts = result.scalars().all()

            for acc in accounts:
                file_count = await delivery._get_file_count(acc.s3_prefix)

                if file_count == 0:
                    await delivery._move_to_lost_empty(acc.s3_prefix)
                    await session.delete(acc)
                    deleted_count += 1
                elif acc.status == "reserved" and acc.reserved_for_order_id:
                    order_id = acc.reserved_for_order_id
                    if order_id not in reserved_by_order:
                        reserved_by_order[order_id] = []
                    reserved_by_order[order_id].append({
                        "prefix": acc.s3_prefix,
                        "files": file_count
                    })

            await session.commit()

        # ==================== ФОРМИРОВАНИЕ ОТВЕТА ====================
        text = f"✅ <b>Синхронизация завершена</b>\n\n"
        text += f"Удалено пустых аккаунтов: <b>{deleted_count}</b>\n\n"

        if reserved_by_order:
            text += f"<b>Зарезервированные аккаунты:</b>\n\n"
            # Сортируем по номеру заказа
            for order_id in sorted(reserved_by_order.keys()):
                accounts_list = reserved_by_order[order_id]
                text += f"📋 <b>Заказ #{order_id}</b> — {len(accounts_list)} аккаунтов\n"
                for acc in accounts_list:
                    text += f"   📦 <code>{acc['prefix']}</code> ({acc['files']} файлов)\n"
                text += "\n"
        else:
            text += "Зарезервированных аккаунтов нет."

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Ошибка в /sync_accounts")
        await message.answer("❌ Произошла ошибка при сверке.")

