# app/bot/keyboard.py
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,  # ← ДОБАВЛЕНО
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List
from config import settings

from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Главное меню (Reply — кнопки внизу экрана)
main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🛒 Ассортимент"),
            KeyboardButton(text="🛒 Корзина")
        ],
        [
            KeyboardButton(text="👤 Личный кабинет"),
            KeyboardButton(text="💳 Баланс")
        ],
        [
            KeyboardButton(text=" Поиск по биржам"),
            KeyboardButton(text="🎟 Реферальная программа")
        ]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите раздел меню..."
)

def cabinet_kb():
    """Inline клавиатура для Личного кабинета"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Мои заказы", callback_data="my_orders")
    #builder.button(text="👥 Рефералы", callback_data="referrals")
    #builder.button(text="⚙️ Настройки", callback_data="settings")
    builder.adjust(1)
    return builder.as_markup()

def categories_kb(categories):
    """Генерирует кнопки категорий"""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat_{cat.id}")
    builder.adjust(2)
    return builder.as_markup()

def products_kb(products):
    """Генерирует кнопки товаров"""
    builder = InlineKeyboardBuilder()
    for prod in products:
        price_fmt = f"{prod.price / 100:.2f}"
        builder.button(text=f"{prod.name} | {price_fmt}{settings.CURRENCY_SYMBOL}", callback_data=f"prod_{prod.id}")
    builder.adjust(1)
    builder.button(text="🔙 Назад к категориям", callback_data="back_to_cats")
    return builder.as_markup()

def product_detail_kb(product_id, category_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 В корзину", callback_data=f"add_{product_id}")
    builder.button(text="🔙 Назад", callback_data=f"cat_{category_id}")
    builder.adjust(2)
    return builder.as_markup()

def cart_view_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Оформить заказ", callback_data="checkout")
    builder.button(text="🗑 Очистить корзину", callback_data="clear_cart")
    return builder.as_markup()

def checkout_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 С баланса", callback_data="pay_order_f_balance")
    builder.button(text="❌ Отмена", callback_data="cancel_checkout")
    builder.adjust(2)
    return builder.as_markup()

def payment_link_kb(url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Перейти к оплате", url=url)
    return builder.as_markup()

def balance_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пополнить баланс", callback_data="topup_start")
    builder.button(text="📋 История", callback_data="balance_history")
    return builder.as_markup()

def cancel_topup_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="topup_cancel")
    return builder.as_markup()

TOPUP_CURRENCIES: dict[str, tuple[str, str]] = {
    "USDTTRC": ("USDT TRC-20", "💵"),
    "USDTBEP": ("USDT BEP-20", "💵"),
    "ETH":     ("ETH",         "🔷"),
    "LTC":     ("LTC",         "⚡️"),
    "BTC":     ("BTC",         "🟠"),
    "BNB":     ("BNB",         "🟡"),
    "SOL":     ("SOL",         "🟣"),
    "XMR":     ("XMR",         "🔒"),
}

def topup_currency_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ticker, (name, emoji) in TOPUP_CURRENCIES.items():
        builder.button(text=f"{emoji} {name}", callback_data=f"topup_cur_{ticker}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="topup_cancel"))
    return builder.as_markup()

def admin_order_kb(order_id: int, is_paid: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_paid:
        builder.button(
            text="♻️ Оформить возврат",
            callback_data=f"refund_order_{order_id}"
        )
    return builder.as_markup()



def get_admin_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📤 Загрузить аккаунты")
    builder.button(text="📊 Мои загруженные аккаунты")
    builder.button(text="🔙 Вернуться в главное меню")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def get_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )