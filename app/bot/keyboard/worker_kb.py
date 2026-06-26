# app/bot/keyboard/worker_kb.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_worker_menu() -> ReplyKeyboardMarkup:
    builder = InlineKeyboardBuilder()  # Можно оставить Reply, но лучше Inline
    builder.button(text="📤 Загрузить аккаунты", callback_data="worker_upload_start")
    builder.button(text="📊 Мои загруженные аккаунты", callback_data="worker_my_accounts")
    builder.button(text="🔙 Главное меню", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()


def get_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )