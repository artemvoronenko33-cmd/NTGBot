# app/bot/menu_work.py
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
#        [
#            KeyboardButton(text=" Поиск по биржам"),
#            KeyboardButton(text="🎟 Реферальная программа")
#        ]
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

def categories_kb(categories_with_counts):
    """Генерирует кнопки категорий с количеством свободных"""
    builder = InlineKeyboardBuilder()
    for cat, free_count in categories_with_counts:
        text = f"{cat.name} ({free_count} свободно)" if free_count > 0 else cat.name
        builder.button(text=text, callback_data=f"cat_{cat.id}")
    builder.adjust(2)
    return builder.as_markup()

def products_kb(products_with_counts):
    """Генерирует кнопки товаров с количеством свободных"""
    builder = InlineKeyboardBuilder()
    for prod, free_count in products_with_counts:
        price_fmt = f"{prod.price / 100:.2f}"
        text = f"{prod.name} | {price_fmt}{settings.CURRENCY_SYMBOL}"
        if free_count > 0:
            text += f" ({free_count} свободно)"
        builder.button(text=text, callback_data=f"prod_{prod.id}")
    builder.button(text="🔙 Назад к категориям", callback_data="back_to_cats")
    builder.adjust(1)

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

def get_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


def products_top_kb(products_with_counts, category_id):
    """Топ-8 товаров + кнопки (исправленный layout)"""
    builder = InlineKeyboardBuilder()

    # Добавляем товары (по 1 в строку)
    for prod, free_count in products_with_counts:
        price_fmt = f"{prod.price / 100:.2f}"
        text = f"{prod.name} | {price_fmt}{settings.CURRENCY_SYMBOL}"
        if free_count > 0:
            text += f" ({free_count})"
        builder.button(text=text, callback_data=f"prod_{prod.id}")

    # Дополнительные кнопки — в отдельной строке
    builder.button(text="🔍 Поиск", callback_data=f"search_in_cat_{category_id}")
    builder.adjust(1)  # каждый элемент в своей строке
    #builder.button(text="📋 Весь список", callback_data=f"all_products_{category_id}")
    builder.button(text="🔙 Назад к категориям", callback_data="back_to_cats")


    return builder.as_markup()