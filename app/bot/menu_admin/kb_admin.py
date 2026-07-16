from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_admin_kb() -> ReplyKeyboardMarkup:
    kb = [
        [
            KeyboardButton(text="📦 Заказы"),
            KeyboardButton(text="👷 Работники")
        ],
        [KeyboardButton(text="🤖 Бот")],
        [KeyboardButton(text="🔙 Выйти из админки")],
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