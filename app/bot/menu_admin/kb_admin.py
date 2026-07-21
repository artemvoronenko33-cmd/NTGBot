from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def get_main_admin_kb() -> ReplyKeyboardMarkup:
    kb = [
        [
            KeyboardButton(text="📦 Заказы"),
            KeyboardButton(text="👷 Работники")
        ],
        [KeyboardButton(text="🤖 Бот")],
        #[KeyboardButton(text="🔙 Выйти из админки")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_orders_admin_kb() -> ReplyKeyboardMarkup:
    kb = [
        [
            KeyboardButton(text="📋 Статус очереди"),
            KeyboardButton(text="📉 Дефицит аккаунтов")
        ],
        [KeyboardButton(text="🔄 Синхронизация аккаунтов")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_workers_admin_kb() -> ReplyKeyboardMarkup:
    kb = [

        [
            KeyboardButton(text="➕ Добавить работника"),
            KeyboardButton(text="➖ Удалить работника")
        ],
        [KeyboardButton(text="👥 Список работников")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_bot_admin_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🩺 Health Check")],
        [
            KeyboardButton(text="🛠️ Включить сервис"),
            KeyboardButton(text="✅ Выключить сервис")
        ],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==================== Клавиатуры для импорта товаров ====================

def admin_import_categories_kb(categories):
    """ReplyKeyboard для выбора категории при импорте"""
    builder = ReplyKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name)
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def admin_import_cancel_kb():
    """Клавиатура с кнопкой отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )