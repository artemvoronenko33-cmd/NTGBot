# app/bot/handlers_worker.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
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
        "👷 Добро пожаловать в панель работника!",
        reply_markup=get_worker_menu()
    )


# ==================== Inline обработчики ====================

@router.callback_query(F.data == "worker_upload_start")
async def start_upload_inline(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.message.edit_text("📂 Загрузка аккаунтов\n\nВыберите категорию:")

    result = await session.execute(text("SELECT id, name FROM categories ORDER BY name"))
    categories = result.fetchall()

    if not categories:
        await callback.answer("Нет категорий")
        return

    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat_{cat.id}")
    builder.adjust(2)

    await callback.message.answer("Выберите категорию:", reply_markup=builder.as_markup())
    await state.set_state(WorkerStates.waiting_for_category)
    await callback.answer()


@router.callback_query(F.data.startswith("cat_"))
async def choose_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    category_id = int(callback.data.split("_")[1])

    result = await session.execute(
        text("SELECT id, name FROM products WHERE category_id = :cid AND is_active = true ORDER BY name"),
        {"cid": category_id}
    )
    products = result.fetchall()

    if not products:
        await callback.message.edit_text("❌ В этой категории нет активных продуктов.")
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for p in products:
        builder.button(text=p.name, callback_data=f"prod_{p.id}")
    builder.adjust(1)

    await callback.message.edit_text("📋 Выберите продукт:", reply_markup=builder.as_markup())
    await state.update_data(category_id=category_id)
    await callback.answer()


@router.callback_query(F.data.startswith("prod_"))
async def choose_product(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    product_id = int(callback.data.split("_")[1])

    result = await session.execute(
        text("""
            SELECT p.name as product_name, c.name as category_name 
            FROM products p 
            JOIN categories c ON p.category_id = c.id 
            WHERE p.id = :pid
        """),
        {"pid": product_id}
    )
    prod = result.fetchone()

    if not prod:
        await callback.answer("Продукт не найден")
        return

    await state.update_data(
        product_id=product_id,
        product_name=prod.product_name,
        category_name=prod.category_name
    )

    await callback.message.edit_text(
        f"✅ Выбран продукт:\n"
        f"**{prod.product_name}**\n"
        f"Категория: {prod.category_name}\n\n"
        f"Теперь отправьте ZIP-архив с аккаунтами.",
        parse_mode="Markdown"
    )
    await state.set_state(WorkerStates.waiting_for_files)
    await callback.answer()


# ==================== Обработка ZIP ====================

@router.message(WorkerStates.waiting_for_files, F.document)
async def process_files(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    product_id = data.get("product_id")
    product_name = data.get("product_name")
    category_name = data.get("category_name")

    if not product_id:
        await message.answer("❌ Сессия устарела. Начните заново /worker")
        await state.clear()
        return

    await message.answer("⏳ Загружаю аккаунты в DigitalOcean Spaces...")

    file = await message.bot.get_file(message.document.file_id)
    file_content = await message.bot.download_file(file.file_path)
    zip_bytes = file_content.read()

    try:
        uploaded = await storage_service.unpack_and_upload_accounts(
            zip_content=zip_bytes,
            product_id=product_id,
            category_name=category_name,
            product_name=product_name,
            worker_id=message.from_user.id
        )

        for acc in uploaded:
            account_item = AccountItem(**{
                "product_id": acc["product_id"],
                "s3_prefix": acc["s3_prefix"],
                "account_name": acc["account_name"],
                "file_count": acc["file_count"],
                "total_size": acc["total_size"],
                "added_by_worker_id": acc["added_by_worker_id"]
            })
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
        await message.answer(f"❌ Ошибка загрузки: {str(e)}")
        await state.clear()


@router.message(F.text == "❌ Отмена")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_worker_menu())