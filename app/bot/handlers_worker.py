# app/bot/handlers_worker.py
"""
Handler'ы для worker'а (загрузка аккаунтов).
Используется callback-based навигация (inline-кнопки) + FSM только для ZIP.
"""

import logging
from typing import Optional

# aiogram
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

# Модели БД
from app.db.models import User, AccountItem

# Repository слой
from app.db.repositories import CategoryRepository

# Services
from app.services import storage_service
from app.services.worker_logger import (
    log_upload_initiated,
    log_upload_completed,
    log_upload_failed,
    log_category_selected,
    log_product_selected,
    log_upload_cancelled,
    log_session_expired,
    log_validation_error,
    log_storage_error,
)

# FSM States
from app.bot.states import WorkerUploadStates

# Keyboards
from app.bot.keyboard.worker_kb import (
    get_worker_menu,
    get_cancel_kb,
    worker_categories_kb,
    worker_products_kb,
)

logger = logging.getLogger(__name__)
router = Router(name="worker_router")


# ==================== /worker Command ====================
@router.message(Command("worker"))
async def cmd_worker(message: Message, session: AsyncSession):
    """Точка входа в панель работника"""
    user = await session.get(User, message.from_user.id)

    if not user or not getattr(user, 'is_worker', False):
        await message.answer("⛔ У вас нет доступа к панели работника.")
        logger.warning(f"Unauthorized worker access attempt from user {message.from_user.id}")
        return

    await message.answer(
        "👷 <b>Добро пожаловать в панель работника!</b>\n\n"
        "Выберите действие:",
        reply_markup=get_worker_menu(),
        parse_mode="HTML"
    )
    logger.info(f"Worker {message.from_user.id} accessed worker panel")


# ==================== Шаг 1: Выбор категории через inline-кнопки ====================
@router.message(F.text == "📤 Загрузить аккаунты")
async def start_upload_accounts(message: Message, session: AsyncSession, state: FSMContext):
    """
    Шаг 1: Показываем категории для выбора через inline-кнопки.
    Загружаем их через CategoryRepository.
    """
    try:
        # Получаем категории через repository (ORM, безопасно)
        categories = await CategoryRepository.get_all_active_categories(session)

        if not categories:
            await message.answer("❌ Пока нет категорий в базе.")
            logger.warning(f"Worker {message.from_user.id} tried to upload but no categories found")
            return

        # Очищаем старое состояние
        await state.clear()

        # Инициируем новый upload (временно сохраняем worker_id)
        await state.update_data(worker_id=message.from_user.id)

        await message.answer(
            "📂 <b>Выберите категорию для загрузки аккаунтов:</b>",
            reply_markup=worker_categories_kb(categories),  # ← Inline-кнопки
            parse_mode="HTML"
        )

        logger.info(f"Worker {message.from_user.id} started upload process. Categories available: {len(categories)}")

    except Exception as e:
        logger.exception(f"Error in start_upload_accounts for worker {message.from_user.id}: {e}")
        await message.answer("❌ Ошибка при загрузке категорий. Попробуйте позже.")


# ==================== Шаг 1а: Выбор категории (Callback) ====================
@router.callback_query(F.data.startswith("worker_cat_"))
async def select_worker_category(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Callback для выбора категории.
    Показываем продукты выбранной категории.
    """
    logger.debug(f"Worker category selection: {callback.data}")

    try:
        category_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError) as e:
        logger.warning(f"Failed to parse category ID from callback: {e}")
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return

    try:
        # Получаем информацию о категории
        category = await CategoryRepository.get_category_by_id(session, category_id)
        if not category:
            logger.warning(f"Category {category_id} not found")
            await callback.answer("❌ Категория не найдена", show_alert=True)
            return

        # Получаем продукты этой категории
        products = await CategoryRepository.get_active_products_by_category(session, category_id)

        if not products:
            await callback.message.edit_text("📦 В этой категории пока нет активных продуктов.")
            await callback.answer()
            return

        # Сохраняем выбранную категорию в state
        await state.update_data(
            category_id=category_id,
            category_name=category.name
        )
        # 📊 Логируем выбор категории
        log_category_selected(callback.from_user.id, category_id, category.name)

        # Показываем продукты
        await callback.message.edit_text(
            f"📋 <b>Продукты категории: {category.name}</b>\n\n"
            f"Выберите продукт:",
            reply_markup=worker_products_kb(products),
            parse_mode="HTML"
        )
        await callback.answer()

        logger.info(f"Worker {callback.from_user.id} selected category {category_id} ({category.name})")

    except Exception as e:
        logger.exception(f"Error selecting category for worker {callback.from_user.id}: {e}")
        await callback.answer("❌ Ошибка при загрузке продуктов", show_alert=True)


# ==================== Шаг 1б: Выбор продукта (Callback) ====================
@router.callback_query(F.data.startswith("worker_prod_"))
async def select_worker_product(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Callback для выбора продукта.
    Переводим worker'а в режим ожидания ZIP.
    """
    logger.debug(f"Worker product selection: {callback.data}")

    try:
        product_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError) as e:
        logger.warning(f"Failed to parse product ID from callback: {e}")
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return

    try:
        # Получаем информацию о продукте
        product = await CategoryRepository.get_product_by_id(session, product_id)
        if not product:
            logger.warning(f"Product {product_id} not found")
            await callback.answer("❌ Продукт не найден", show_alert=True)
            return

        if not product.is_active:
            logger.warning(f"Product {product_id} is inactive")
            await callback.answer("❌ Этот продукт больше недоступен", show_alert=True)
            return

        # Получаем категорию из state
        data = await state.get_data()
        category_name = data.get("category_name", "Unknown")

        # Сохраняем выбранный продукт в state
        await state.update_data(
            product_id=product_id,
            product_name=product.name
        )

        # Переводим в режим ожидания ZIP
        await state.set_state(WorkerUploadStates.waiting_for_zip)

        # 📊 Логируем выбор продукта
        log_product_selected(callback.from_user.id, product_id, product.name, category_name)

        price_fmt = f"{product.price / 100:.2f}$"

        await callback.message.edit_text(
            f"✅ <b>Продукт выбран:</b>\n\n"
            f"📂 Категория: <code>{category_name}</code>\n"
            f"📦 Продукт: <code>{product.name}</code>\n"
            f"💰 Цена: <code>{price_fmt}</code>\n\n"
            f"<b>Теперь отправьте ZIP-архив</b> с папками-аккаунтами.\n\n"
            f"📋 Структура архива:\n"
            f"<code>archive.zip\n"
            f"├─ Account_1/\n"
            f"│  ├─ file1.txt\n"
            f"│  └─ file2.zip\n"
            f"└─ Account_2/\n"
            f"   └─ data.txt</code>",
            reply_markup=get_cancel_kb(),
            parse_mode="HTML"
        )
        await callback.answer()

        logger.info(
            f"Worker {callback.from_user.id} selected product {product_id} ({product.name}). "
            f"Waiting for ZIP..."
        )

    except Exception as e:
        logger.exception(f"Error selecting product for worker {callback.from_user.id}: {e}")
        await callback.answer("❌ Ошибка при обработке выбора", show_alert=True)


# ==================== Навигация: Назад к категориям ====================
@router.callback_query(F.data == "worker_back_to_cats")
async def worker_back_to_categories(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Вернуться к выбору категории"""
    logger.debug(f"Worker going back to categories")

    try:
        categories = await CategoryRepository.get_all_active_categories(session)

        if not categories:
            await callback.answer("❌ Категорий нет", show_alert=True)
            return

        # Очищаем выбор продукта, но сохраняем worker_id
        await state.update_data(product_id=None, product_name=None)

        await callback.message.edit_text(
            "📂 <b>Выберите категорию:</b>",
            reply_markup=worker_categories_kb(categories),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.exception(f"Error going back to categories: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== Отмена (Callback версия) ====================
@router.callback_query(F.data == "worker_cancel")
async def worker_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена процесса через callback"""
    await state.clear()

    await callback.message.edit_text(
        "❌ <b>Действие отменено.</b>\n\n"
        "Вернитесь в меню командой /worker или нажмите кнопку ниже.",
        reply_markup=None
    )
    # 📊 Логируем отмену
    current_state = await state.get_state()
    stage = "unknown"
    if current_state == WorkerUploadStates.waiting_for_zip:
        stage = "waiting_for_zip"
    log_upload_cancelled(callback.from_user.id, stage)
    await callback.answer()

    logger.info(f"Worker {callback.from_user.id} cancelled operation via callback")


# ==================== Вспомогательные Callbacks ====================
@router.callback_query(F.data == "worker_upload_again")
async def worker_upload_again(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Загрузить ещё (вернуться к выбору категории)"""
    try:
        # Очищаем state
        await state.clear()

        # Сохраняем worker_id
        await state.update_data(worker_id=callback.from_user.id)

        # Получаем категории
        categories = await CategoryRepository.get_all_active_categories(session)

        if not categories:
            await callback.message.edit_text("❌ Пока нет категорий в базе.")
            await callback.answer()
            return

        # Отправляем меню категорий
        await callback.message.edit_text(
            "📂 <b>Выберите категорию для загрузки новых аккаунтов:</b>",
            reply_markup=worker_categories_kb(categories),
            parse_mode="HTML"
        )
        await callback.answer()

        logger.info(f"Worker {callback.from_user.id} wants to upload more accounts")

    except Exception as e:
        logger.exception(f"Error in worker_upload_again: {e}")
        await callback.answer("❌ Ошибка при загрузке категорий", show_alert=True)


@router.callback_query(F.data == "worker_main_menu")
async def worker_main_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню работника"""
    await state.clear()

    await callback.message.edit_text(
        "👷 <b>Панель работника</b>\n\n"
        "Выберите действие:",
        reply_markup=get_worker_menu()  # ← Reply KB меню!
    )
    await callback.answer()

    logger.info(f"Worker {callback.from_user.id} returned to main menu")

# ==================== Шаг 3: Обработка ZIP-архива ====================
@router.message(WorkerUploadStates.waiting_for_zip, F.document)
async def process_zip_upload(message: Message, state: FSMContext, session: AsyncSession):
    """
    Шаг 3: Получаем ZIP-архив, обрабатываем и сохраняем в S3/Local storage.

    Ожидаемые данные в state:
    - category_id: int
    - category_name: str
    - product_id: int
    - product_name: str
    - worker_id: int
    """
    data = await state.get_data()

    # Валидация наличие необходимых данных
    required_keys = ['product_id', 'product_name', 'category_name', 'worker_id']
    if not all(key in data for key in required_keys):
        await message.answer("❌ Сессия устарела. Начните заново командой /worker")
        await state.clear()
        logger.warning(f"Worker {message.from_user.id} had corrupted state data")
        # 📊 Логируем истечение сессии
        log_session_expired(message.from_user.id)
        return

    product_id = data['product_id']
    product_name = data['product_name']
    category_name = data['category_name']
    worker_id = data['worker_id']

    await message.answer("⏳ Обрабатываю и загружаю архив...")

    try:
        # Загружаем файл от Telegram
        file = await message.bot.get_file(message.document.file_id)
        file_content = await message.bot.download_file(file.file_path)
        zip_bytes = file_content.read()

        # 📊 Логируем начало загрузки
        log_upload_initiated(
            worker_id=worker_id,
            product_id=product_id,
            product_name=product_name,
            category_name=category_name,
            file_size=len(zip_bytes)
        )

        # Обрабатываем архив через storage_service
        uploaded = await storage_service.unpack_and_upload_accounts(
            zip_content=zip_bytes,
            product_id=product_id,
            category_name=category_name,
            product_name=product_name,
            worker_id=worker_id
        )

        # Сохраняем AccountItems в БД
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

        # 📊 Логируем успешную загрузку
        log_upload_completed(
            worker_id=worker_id,
            product_id=product_id,
            accounts_count=len(uploaded),
            total_size=sum(acc["total_size"] for acc in uploaded)
        )

        # Уведомляем пользователя
        await message.answer(
            f"✅ <b>Успешно загружено {len(uploaded)} аккаунтов!</b>\n\n"
            f"📂 Категория: <code>{category_name}</code>\n"
            f"📦 Продукт: <code>{product_name}</code>",
            reply_markup=get_worker_menu(),
            parse_mode="HTML"
        )

        logger.info(
            f"Worker {worker_id} successfully uploaded {len(uploaded)} accounts "
            f"for product {product_id} ({product_name})"
        )

        await state.clear()

    except ValueError as e:
        await session.rollback()
        logger.warning(f"Validation error during upload for worker {worker_id}: {e}")

        # 📊 Логируем ошибку валидации
        log_validation_error(worker_id, product_id, str(e))

        await message.answer(f"❌ Ошибка валидации: {e}")
        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.exception(f"Unexpected error during upload for worker {worker_id}: {e}")

        # 📊 Логируем ошибку storage
        log_storage_error(
            worker_id,
            product_id,
            f"{type(e).__name__}: {str(e)}",
            error_type="unexpected"
        )

        await message.answer("❌ Внутренняя ошибка при загрузке архива. Попробуйте позже.")
        await state.clear()


# ==================== Отмена ====================
@router.message(F.text == "❌ Отмена")
async def cancel_handler(message: Message, state: FSMContext):
    """Отмена текущей операции"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_worker_menu()
    )
    logger.info(f"Worker {message.from_user.id} cancelled upload operation")