# app/bot/handlers_worker.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User, AccountItem, Product
from app.services import storage_service
from app.bot.states import WorkerStates
from app.bot.keyboards import get_worker_menu, get_cancel_kb


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
    # Получаем список продуктов для выбора
    products = await session.execute("SELECT id, name FROM products WHERE is_active = true")
    products_list = products.fetchall()

    if not products_list:
        await message.answer("❌ Пока нет активных продуктов.")
        return

    text = "Выберите продукт (тип аккаунта), для которого загружаете:\n\n"
    for p in products_list:
        text += f"ID: {p.id} — {p.name}\n"

    await message.answer(text + "\n\nОтправьте ID продукта:", reply_markup=get_cancel_kb())
    await state.set_state(WorkerStates.waiting_for_category)


@router.message(WorkerStates.waiting_for_category)
async def process_category(message: Message, state: FSMContext, session: AsyncSession):
    try:
        product_id = int(message.text.strip())
        await state.update_data(product_id=product_id)
        await message.answer(
            "✅ Продукт выбран.\n\n"
            "Теперь отправьте **ZIP-архив** с одной или несколькими папками-аккаунтами.",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(WorkerStates.waiting_for_files)
    except ValueError:
        await message.answer("❌ Введите корректный ID продукта (число).")


@router.message(WorkerStates.waiting_for_files, F.document)
async def process_files(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    product_id = data.get("product_id")
    worker_id = message.from_user.id

    await message.answer("⏳ Обрабатываю архив...")

    # Скачиваем файл
    document = message.document
    file = await message.bot.get_file(document.file_id)
    file_content = await message.bot.download_file(file.file_path)

    try:
        uploaded = await storage_service.unpack_and_upload_accounts(
            zip_content=file_content.read(),
            product_id=product_id,
            category_name="default",  # можно улучшить позже
            worker_id=worker_id,
            account_name_prefix=""
        )

        # Сохраняем в БД
        for acc in uploaded:
            account_item = AccountItem(
                product_id=acc["product_id"],
                s3_prefix=acc["s3_prefix"],
                account_name=acc["account_name"],
                file_count=acc["file_count"],
                total_size=acc["total_size"],
                added_by_worker_id=acc["added_by_worker_id"],
                metadata_json=None  # можно расширить позже
            )
            session.add(account_item)

        await session.commit()

        await message.answer(
            f"✅ Успешно загружено **{len(uploaded)}** аккаунтов!\n"
            f"Можно загружать следующий архив или вернуться в меню.",
            reply_markup=get_worker_menu()
        )
        await state.clear()

    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке: {str(e)}")
        await state.clear()