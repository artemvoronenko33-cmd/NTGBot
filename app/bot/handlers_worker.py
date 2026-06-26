# app/bot/handlers_worker.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.models import User, AccountItem
from app.services import storage_service
from app.bot.states import WorkerStates
from app.bot.keyboard.worker_kb import get_worker_menu, get_cancel_kb

router = Router(name="worker_router")


@router.message(Command("worker"))
async def cmd_worker(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user or not getattr(user, 'is_worker', False):
        await message.answer("⛔ У вас нет доступа к панели работника.")
        return

    await message.answer(
        "👷 Добро пожаловать в панель работника!\n\n"
        "Выберите действие:",
        reply_markup=get_worker_menu()
    )


@router.message(F.text == "📤 Загрузить аккаунты")
async def start_upload_accounts(message: Message, state: FSMContext, session: AsyncSession):
    """Шаг 1: Выбор категории"""
    result = await session.execute(
        text("SELECT id, name FROM categories ORDER BY name")
    )
    categories = result.fetchall()

    if not categories:
        await message.answer("❌ Пока нет категорий в базе.")
        return

    text_msg = "📂 **Выберите категорию:**\n\n"
    for cat in categories:
        text_msg += f"🆔 {cat.id} — {cat.name}\n"

    text_msg += "\nОтправьте ID категории:"

    await message.answer(text_msg, reply_markup=get_cancel_kb(), parse_mode="Markdown")
    await state.set_state(WorkerStates.waiting_for_category)


@router.message(WorkerStates.waiting_for_category)
async def process_category(message: Message, state: FSMContext, session: AsyncSession):
    """Шаг 2: Выбор продукта после категории"""
    try:
        category_id = int(message.text.strip())

        result = await session.execute(
            text("""
                SELECT id, name 
                FROM products 
                WHERE category_id = :cat_id AND is_active = true 
                ORDER BY name
            """),
            {"cat_id": category_id}
        )
        products = result.fetchall()

        if not products:
            await message.answer("❌ В этой категории нет активных продуктов.")
            return

        text_msg = "📋 **Выберите продукт:**\n\n"
        for p in products:
            text_msg += f"🆔 {p.id} — {p.name}\n"

        text_msg += "\nОтправьте ID продукта:"

        await message.answer(text_msg, reply_markup=get_cancel_kb(), parse_mode="Markdown")
        await state.update_data(category_id=category_id)
        await state.set_state(WorkerStates.waiting_for_product)   # ← Новое состояние!

    except ValueError:
        await message.answer("❌ Введите корректный ID категории (число).")


@router.message(WorkerStates.waiting_for_product)
async def process_product(message: Message, state: FSMContext, session: AsyncSession):
    """Шаг 3: Подтверждение продукта и ожидание ZIP"""
    try:
        product_id = int(message.text.strip())

        result = await session.execute(
            text("""
                SELECT p.name as product_name, c.name as category_name 
                FROM products p 
                JOIN categories c ON p.category_id = c.id 
                WHERE p.id = :pid AND p.is_active = true
            """),
            {"pid": product_id}
        )
        prod = result.fetchone()

        if not prod:
            await message.answer("❌ Продукт не найден или неактивен.")
            return

        await state.update_data(
            product_id=product_id,
            product_name=prod.product_name,
            category_name=prod.category_name
        )

        await message.answer(
            f"✅ Выбран продукт:\n"
            f"**{prod.product_name}**\n"
            f"Категория: {prod.category_name}\n\n"
            f"Теперь отправьте **ZIP-архив** с папками-аккаунтами.",
            parse_mode="Markdown",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(WorkerStates.waiting_for_files)

    except ValueError:
        await message.answer("❌ Введите корректный ID продукта.")


@router.message(WorkerStates.waiting_for_files, F.document)
async def process_files(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    product_id = data.get("product_id")
    product_name = data.get("product_name")
    category_name = data.get("category_name")

    if not all([product_id, product_name]):
        await message.answer("❌ Сессия устарела. Начните заново командой /worker")
        await state.clear()
        return

    await message.answer("⏳ Обрабатываю и загружаю архив...")

    file = await message.bot.get_file(message.document.file_id)
    file_content = await message.bot.download_file(file.file_path)
    zip_bytes = file_content.read()

    try:
        uploaded = await storage_service.unpack_and_upload_accounts(
            zip_content=zip_bytes,
            product_id=product_id,
            category_name=category_name or "unknown",
            product_name=product_name,
            worker_id=message.from_user.id
        )

        for acc in uploaded:
            account_item = AccountItem(
                product_id=acc["product_id"],
                s3_prefix=acc["s3_prefix"],
                account_name=acc["account_name"],
                file_count=acc["file_count"],
                total_size=acc["total_size"],
                added_by_worker_id=acc["added_by_worker_id"]
            )
            session.add(account_item)

        await session.commit()

        await message.answer(
            f"✅ Успешно загружено **{len(uploaded)}** аккаунтов!\n\n"
            f"Категория: {category_name}\n"
            f"Продукт: {product_name}",
            reply_markup=get_worker_menu()
        )
        await state.clear()

    except Exception as e:
        await session.rollback()
        await message.answer(f"❌ Ошибка при загрузке: {str(e)}")
        await state.clear()


@router.message(F.text == "❌ Отмена")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=get_worker_menu())