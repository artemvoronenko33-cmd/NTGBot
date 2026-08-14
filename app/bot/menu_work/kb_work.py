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
    #builder.button(text="🔙 Главное меню")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# ==================== INLINE КЛАВИАТУРЫ ДЛЯ ВЫБОРА ====================

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def worker_categories_kb(categories):
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"worker_cat_{cat.id}")
    builder.adjust(2)
    builder.button(text="❌ Отмена", callback_data="worker_cancel")
    return builder.as_markup()


def worker_products_top_kb(products_with_counts, category_id):
    """Топ-8 товаров + кнопки Поиск / Весь список (для воркера)"""
    builder = InlineKeyboardBuilder()

    for prod, free_count in products_with_counts:
        text = f"{prod.name}"
        if free_count > 0:
            text += f" ({free_count})"
        builder.button(text=text, callback_data=f"worker_prod_{prod.id}")

    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(text="🔍 Поиск", callback_data=f"worker_search_{category_id}"),
        InlineKeyboardButton(text="📋 Весь список", callback_data=f"worker_all_{category_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="worker_back_to_cats"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="worker_cancel"))

    return builder.as_markup()


def worker_products_kb(products_with_counts):
    """Полный или отфильтрованный список товаров"""
    builder = InlineKeyboardBuilder()
    for prod, free_count in products_with_counts:
        text = f"{prod.name}"
        if free_count > 0:
            text += f" ({free_count})"
        builder.button(text=text, callback_data=f"worker_prod_{prod.id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="worker_back_to_cats"))
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
