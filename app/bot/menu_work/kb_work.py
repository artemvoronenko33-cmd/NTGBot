# app/bot/menu_work/kb_work.py
"""
Клавиатуры для работника (worker).
Inline-кнопки для выбора категорий и продуктов.
"""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.db.models import Category, Product


def get_worker_menu() -> ReplyKeyboardMarkup:
    """
    Основное меню работника (Reply KB).
    Кнопки внизу экрана.
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text="📤 Загрузить аккаунты")
    #builder.button(text="📊 Мои загруженные аккаунты")
    builder.button(text="🔙 Главное меню")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# ==================== INLINE КЛАВИАТУРЫ ДЛЯ ВЫБОРА ====================

def worker_categories_kb(categories: List[Category]) -> InlineKeyboardMarkup:
    """
    Inline-клавиатура со списком категорий для работника.

    Args:
        categories: Список объектов Category

    Returns:
        InlineKeyboardMarkup с кнопками категорий

    Callback формат: worker_cat_{category_id}
    """
    builder = InlineKeyboardBuilder()

    for cat in categories:
        builder.button(
            text=f"📂 {cat.name}",
            callback_data=f"worker_cat_{cat.id}"
        )

    # Кнопки расположены в 2 колонны для компактности
    builder.adjust(2)

    # Добавляем кнопку отмены отдельным рядом
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="worker_cancel")
    )

    return builder.as_markup()


def worker_products_kb(products: List[Product]) -> InlineKeyboardMarkup:
    """
    Inline-клавиатура со списком продуктов для работника.

    Args:
        products: Список объектов Product

    Returns:
        InlineKeyboardMarkup с кнопками продуктов

    Callback формат: worker_prod_{product_id}
    """
    builder = InlineKeyboardBuilder()

    for prod in products:
        # Показываем название и цену
        price_fmt = f"{prod.price / 100:.2f}$"
        builder.button(
            text=f"📦 {prod.name} | {price_fmt}",
            callback_data=f"worker_prod_{prod.id}"
        )

    # Каждый продукт на отдельной строке (более удобно для выбора)
    builder.adjust(1)

    # Добавляем навигационные кнопки отдельным рядом
    builder.row(
        InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="worker_back_to_cats"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="worker_cancel")
    )

    return builder.as_markup()


def worker_zip_confirmation_kb() -> InlineKeyboardMarkup:
    """
    Inline-клавиатура после успешной загрузки ZIP.
    Опции: загрузить ещё или вернуться в меню.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Загрузить ещё", callback_data="worker_upload_again")
    builder.button(text="🔙 Главное меню", callback_data="worker_main_menu")
    builder.adjust(1)
    return builder.as_markup()

#=============================== Кнопки Отмены =============================================

def get_cancel_inline_kb(text: str = "❌ Отмена") -> InlineKeyboardMarkup:
    """
    Универсальная inline-кнопка отмены.
    Используется в edit_text / edit_message_text.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data="worker_cancel")
    return builder.as_markup()
