# app/bot/handlers.py
import asyncio
import logging
from io import BytesIO

import qrcode
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update, func

from app.bot.keyboards import (
    main_menu_kb, categories_kb, products_kb, product_detail_kb,
    cart_view_kb, checkout_confirm_kb, payment_link_kb,
    balance_kb, cancel_topup_kb, topup_currency_kb, TOPUP_CURRENCIES,
    cabinet_kb,
)
from app.bot.states import TopUpStates
from app.db.models import User, Category, Product, Order, OrderItem, Payment, TopUp
from app.db.engine import async_session
from app.services.redis_cart import add_to_cart, get_cart, clear_cart
from app.services.payment import create_invoice, generate_address
from app.services.rates import get_price_usd, usd_to_crypto
from config import settings
from app.bot.bot_instance import bot

from app.services.balance import (
    check_rate_limit,
    record_transaction,
    get_user_balance_history,
    TransactionType
)

from app.services.payment_logger import (
    log_payment_start,
    log_payment_success,
    log_payment_failed,
    log_topup_initiated,
    log_topup_completed,
    log_refund,
    log_rate_limit_hit,
    log_large_payment_admin_notified,
)

logger = logging.getLogger(__name__)
router = Router()

def _make_qr(data: str) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ==================== Личный кабинет ====================
@router.message(F.text == "👤 Личный кабинет")
async def personal_cabinet(message: Message):
    async with async_session() as session:
        user = await session.get(User, message.from_user.id)
        order_count = (await session.execute(
            select(func.count(Order.id)).where(Order.user_id == message.from_user.id)
        )).scalar() or 0

    if not user:
        await message.answer("❌ Профиль не найден. Напишите /start")
        return

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 @{user.username or 'нет'}\n"
        f"💰 Баланс: <b>${user.balance / 100:.2f}</b>\n"
        f"📦 Заказов: <b>{order_count}</b>\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y')}\n"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=cabinet_kb())


# ==================== Мои заказы ====================
@router.callback_query(F.data == "my_orders")
async def my_orders(callback: CallbackQuery):
    async with async_session() as session:
        orders = (await session.execute(
            select(Order)
            .where(Order.user_id == callback.from_user.id)
            .order_by(Order.created_at.desc())
            .limit(10)
        )).scalars().all()

    if not orders:
        await callback.message.edit_text("📭 У вас пока нет заказов.", reply_markup=cabinet_kb())
        await callback.answer()
        return

    text = "📦 <b>Ваши последние заказы</b>\n\n"
    for order in orders:
        status_emoji = {"pending": "⏳", "paid": "✅", "completed": "✅", "cancelled": "❌", "refunded": "♻️"}.get(order.status, "❓")
        text += (
            f"{status_emoji} <b>Заказ #{order.id}</b>\n"
            f"💰 Сумма: ${order.total_price:.2f}\n"
            f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📝 Статус: {order.status}\n\n"
        )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=cabinet_kb())
    await callback.answer()


# ==================== Рефералы ====================
#@router.callback_query(F.data == "referrals")
#async def referrals(callback: CallbackQuery):
#    await callback.answer("👥 Раздел рефералов в разработке...", show_alert=True)


# ==================== Настройки ====================
#@router.callback_query(F.data == "settings")
#async def settings(callback: CallbackQuery):
#    await callback.answer("⚙️ Настройки в разработке...", show_alert=True)


# ==================== /start ====================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        stmt = select(User).where(User.id == message.from_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            new_user = User(
                id=message.from_user.id,
                username=message.from_user.username,
                language_code=message.from_user.language_code or "ru"
            )
            session.add(new_user)
            await session.commit()

    await message.answer(
        f"👋 Привет, {message.from_user.full_name}!",
        reply_markup=main_menu_kb
    )


# ==================== Ассортимент (кнопка меню) ====================
@router.message(F.text == "🛒 Ассортимент")
async def show_categories(message: Message):
    async with async_session() as session:
        stmt = select(Category).order_by(Category.id)
        result = await session.execute(stmt)
        cats = result.scalars().all()

        if not cats:
            await message.answer("📭 Категорий пока нет.")
            return

        await message.answer(
            "📂 Выберите категорию:",
            reply_markup=categories_kb(cats)
        )



# ==================== Выбор категории (callback) ====================
@router.callback_query(F.data.startswith("cat_"))
async def process_category(callback: CallbackQuery):
    logger.debug(f"Processing category selection. Data: {callback.data}")

    try:
        cat_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError) as e:
        logger.warning(f"Failed to parse category ID: {e}")
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return

    async with async_session() as session:
        stmt = select(Product).where(
            Product.category_id == cat_id,
            Product.is_active == True
        )
        result = await session.execute(stmt)
        prods = result.scalars().all()

        cat_stmt = select(Category).where(Category.id == cat_id)
        cat_res = await session.execute(cat_stmt)
        cat_obj = cat_res.scalar_one()

        if not prods:
            await callback.message.answer("📦 В этой категории пока нет товаров.")
            await callback.answer()
            return

        await callback.message.answer(
            f"📂 Товары: <b>{cat_obj.name}</b>",
            reply_markup=products_kb(prods)
        )

        await callback.answer()
        await callback.message.delete()


# ==================== Выбор товара (callback) ====================
@router.callback_query(F.data.startswith("prod_"))
async def process_product(callback: CallbackQuery):
    logger.debug(f"Processing product selection. Data: {callback.data}")

    try:
        prod_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    async with async_session() as session:
        stmt = select(Product).where(Product.id == prod_id)
        result = await session.execute(stmt)
        prod = result.scalar_one()

        price_fmt = f"{prod.price / 100:.2f}{settings.CURRENCY_SYMBOL}"
        text = f"📦 <b>{prod.name}</b>\n💰 {price_fmt}\n\n{prod.description}"

        await callback.message.answer(
            text,
            reply_markup=product_detail_kb(prod.id, prod.category_id)
        )
        await callback.answer()
        await callback.message.delete()

#==================== Корзина ====================
# 1. Нажатие "В корзину" в карточке товара
@router.callback_query(F.data.startswith("add_"))
async def add_item_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    await add_to_cart(callback.from_user.id, product_id)
    await callback.answer("✅ Товар добавлен в корзину!")


# 2. Просмотр корзины
@router.message(F.text.in_(["🛒 Корзина"]))
async def view_cart(message: Message):
    cart_items = await get_cart(message.from_user.id)

    if not cart_items:
        await message.answer("🛒 Корзина пуста. Добавьте товары из ассортимента.")
        return

    total_sum = 0
    text = "📦 <b>Ваша корзина:</b>\n\n"

    async with async_session() as session:
        for item in cart_items:
            stmt = select(Product).where(Product.id == item['product_id'])
            result = await session.execute(stmt)
            prod = result.scalar_one()

            sum_item = prod.price * item['qty']
            total_sum += sum_item
            text += f"• {prod.name} x{item['qty']} = {sum_item / 100}{settings.CURRENCY_SYMBOL}\n"

        text += f"\n💰 <b>Итого: {total_sum / 100}{settings.CURRENCY_SYMBOL}</b>"


        # ✅ Используем вынесенную клавиатуру
        await message.answer(text, reply_markup=cart_view_kb(), parse_mode="HTML")


# 3. Оформление заказа
@router.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery):
    # Простая проверка перед созданием заказа

    cart_items = await get_cart(callback.from_user.id)
    if not cart_items:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    total_sum = 0
    async with async_session() as session:
        for item in cart_items:
            stmt = select(Product).where(Product.id == item['product_id'])
            prod = (await session.execute(stmt)).scalar_one()
            total_sum += prod.price * item['qty']

        stmt = select(User).where(User.id == callback.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
    balance_usd = (user.balance / 100) if user else 0.0

    # ✅ Показываем итог и кнопку подтверждения
    await callback.message.answer(
        f"📋 <b>Подтверждение заказа</b>\n"
        f"Сумма: {total_sum / 100}{settings.CURRENCY_SYMBOL}\n"
        f"Товаров: {len(cart_items)}\n\n"
        f"💳 <b>Ваш баланс:</b> <b>${balance_usd:.2f}</b>\n"
        f"Нажмите «Оплатить» для перехода к оплате.",
        reply_markup=checkout_confirm_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# 4. Очистка корзины
@router.callback_query(F.data == "clear_cart")
async def clear_cart_handler(callback: CallbackQuery):
    await clear_cart(callback.from_user.id)
    await callback.message.edit_text("🗑 Корзина очищена.")
    await callback.answer()


# ==================== Назад ====================
@router.callback_query(F.data == "back_to_cats")
async def back_to_categories(callback: CallbackQuery):
    logger.debug("Navigating back to categories")
    await callback.message.delete()
    await show_categories(callback.message)
    await callback.answer()

# ==================== Оплата с баланса ====================
# app/bot/handlers.py
# app/bot/handlers.py

from app.services.balance import check_rate_limit, record_transaction, TransactionType
from app.bot.notifier import notify_payment_success, notify_admin_large_payment
import logging

logger = logging.getLogger(__name__)


@router.callback_query(F.data == "pay_order_f_balance")
async def pay_from_balance(callback: CallbackQuery):
    user_id = callback.from_user.id
    cart_items = await get_cart(user_id)

    if not cart_items:
        await callback.answer("🛒 Корзина пуста!", show_alert=True)
        return

    # 🔐 Rate-limit проверка
    if not await check_rate_limit(
            user_id,
            max_attempts=settings.PAYMENT_RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.PAYMENT_RATE_LIMIT_WINDOW
    ):
        await callback.answer(
            "⚠️ Слишком много попыток. Подождите 1 минуту.",
            show_alert=True
        )
        logger.warning("Rate limit hit for user %s", user_id)
        log_rate_limit_hit(user_id, settings.PAYMENT_RATE_LIMIT_ATTEMPTS,
                           settings.PAYMENT_RATE_LIMIT_WINDOW)
        return

    await callback.answer()
    await callback.message.edit_text("⏳ Обрабатываем оплату...")

    async with async_session() as session:
        try:
            # 1. Считаем сумму
            total_cents = 0
            products_data = []

            for item in cart_items:
                stmt = select(Product).where(Product.id == item["product_id"])
                prod = (await session.execute(stmt)).scalar_one_or_none()

                if not prod:
                    logger.error(f"Product {item['product_id']} not found during payment")
                    await session.rollback()
                    await callback.message.edit_text("❌ Один из товаров больше недоступен. Корзина очищена.")
                    await clear_cart(user_id)
                    return

                total_cents += prod.price * item["qty"]
                products_data.append((prod, item["qty"]))

            total_usd = total_cents / 100

            # 📊 Логируем начало платежа
            log_payment_start(user_id, order_id=None, amount_usd=total_usd,
                              payment_method="balance")

            # 2. Списываем баланс через сервис (атомарно + лог + история)
            new_balance = await record_transaction(
                session=session,
                user_id=user_id,
                amount_cents=-total_cents,
                transaction_type=TransactionType.ORDER_PAYMENT,
                description="Оплата заказа (корзина)",
                metadata={"cart_items": len(cart_items)},
                order_id=None,
                topup_id=None,
                ip_address=None,
            )

            # 3. Создаём заказ
            order = Order(
                user_id=user_id,
                status="paid",
                total_price=total_usd,
            )
            session.add(order)
            await session.flush()

            # 4. Создаём позиции заказа
            for prod, qty in products_data:
                session.add(OrderItem(
                    order_id=order.id,
                    product_id=prod.id,
                    product_name=prod.name,
                    quantity=qty,
                    price_at_purchase=prod.price / 100,
                ))

            # 5. Запись платежа
            payment = Payment(
                order_id=order.id,
                user_id=user_id,
                amount_usd=total_usd,
                status="completed",
                payment_method="balance",
            )
            session.add(payment)

            await session.commit()

            # ✅ Уведомление пользователя
            await callback.message.edit_text(
                f"✅ <b>Оплата прошла успешно!</b>\n\n"
                f"📋 Заказ #{order.id}\n"
                f"💵 Списано: ${total_usd:.2f}\n"
                f"💳 Баланс: ${new_balance / 100:.2f}",
            )
            await notify_payment_success(user_id, order.id)

            # 📊 Логируем успешный платёж
            log_payment_success(user_id, order.id, total_usd, "balance", new_balance)

            # 🔔 Админ-уведомление для крупных платежей
            if total_usd >= settings.LARGE_PAYMENT_THRESHOLD_USD:
                await notify_admin_large_payment(
                    user_id=user_id,
                    order_id=order.id,
                    amount_usd=total_usd,
                    username=callback.from_user.username,
                )
                # 📊 Логируем уведомление администратора
                log_large_payment_admin_notified(user_id, order.id, total_usd,
                                                 callback.from_user.username or "unknown")

            logger.info(
                "Balance payment completed: user=%s order=%s amount=%.2f",
                user_id, order.id, total_usd
            )

        except ValueError as e:
            await session.rollback()
            logger.warning("Payment failed for user %s: %s", user_id, e)
            # 📊 Логируем ошибку платежа
            log_payment_failed(user_id, order_id=None, amount_usd=total_cents / 100,
                               payment_method="balance", error_reason=str(e))
            await callback.message.edit_text(f"❌ Ошибка: {e}")
        except Exception as e:
            await session.rollback()
            logger.exception("Unexpected error during balance payment: user=%s", user_id)
            # 📊 Логируем непредвиденную ошибку
            log_payment_failed(user_id, order_id=None, amount_usd=total_cents / 100,
                               payment_method="balance", error_reason=f"Unexpected: {str(e)}")
            await callback.message.edit_text("❌ Внутренняя ошибка. Попробуйте позже.")

    # Очищаем корзину только после успешной оплаты
    await clear_cart(user_id)



# ==================== Оплата через WestWallet ====================
@router.callback_query(F.data == "pay_order")
async def pay_order(callback: CallbackQuery):
    cart_items = await get_cart(callback.from_user.id)
    if not cart_items:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text("⏳ Создаём счёт на оплату...")

    async with async_session() as session:
        # Собираем товары и считаем сумму
        products_data = []
        total_kopecks = 0
        for item in cart_items:
            stmt = select(Product).where(Product.id == item["product_id"])
            prod = (await session.execute(stmt)).scalar_one()
            total_kopecks += prod.price * item["qty"]
            products_data.append((prod, item["qty"]))

        total_usd = round(total_kopecks / 100, 2)

        # Создаём заказ
        order = Order(
            user_id=callback.from_user.id,
            status="pending_payment",
            total_price=total_usd,
        )
        session.add(order)
        await session.flush()  # получаем order.id

        for prod, qty in products_data:
            session.add(OrderItem(
                order_id=order.id,
                product_id=prod.id,
                quantity=qty,
                price_at_purchase=prod.price / 100,
            ))

        # Создаём инвойс в WestWallet
        try:
            invoice = await create_invoice(order.id, total_usd)
        except Exception as e:
            logger.error("WestWallet error: %s", e)
            await session.rollback()
            await callback.message.edit_text(
                "❌ Не удалось создать счёт на оплату. Попробуйте позже."
            )
            return

        # Сохраняем платёж
        payment = Payment(
            order_id=order.id,
            user_id=callback.from_user.id,
            invoice_token=invoice.token,
            invoice_url=invoice.url,
            amount_usd=total_usd,
            status="pending",
        )
        session.add(payment)
        await session.commit()

    await clear_cart(callback.from_user.id)

    await callback.message.edit_text(
        f"📋 <b>Заказ #{order.id} создан</b>\n"
        f"💵 Сумма: <b>${total_usd:.2f}</b>\n\n"
        f"Нажмите кнопку ниже для оплаты криптовалютой.\n"
        f"⏱ Счёт действителен <b>90 минут</b>.",
        reply_markup=payment_link_kb(invoice.url),
    )

# ==================== Возвраты ====================
# app/bot/handlers.py — добавьте новый хендлер

@router.callback_query(F.data.startswith("refund_order_"))
async def refund_order(callback: CallbackQuery):
    """
    Возврат средств за заказ.
    Доступно только админам (проверка через settings.ADMIN_IDS).
    Callback: refund_order_{order_id}
    """
    # Проверка прав админа
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("🔐 Доступ запрещён", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный формат", show_alert=True)
        return

    async with async_session() as session:
        # Получаем заказ и платеж
        stmt = select(Order, Payment).join(Payment).where(Order.id == order_id)
        result = await session.execute(stmt)
        row = result.first()

        if not row:
            await callback.answer("❌ Заказ не найден", show_alert=True)
            return

        order, payment = row

        # Проверка: уже возвращён?
        if payment.status == "refunded":
            await callback.answer("ℹ️ Возврат уже оформлен", show_alert=True)
            return

        # Возвращаем средства
        amount_cents = int(payment.amount_usd * 100)
        new_balance = await record_transaction(
            session=session,
            user_id=payment.user_id,
            amount_cents=amount_cents,  # плюс = зачисление
            transaction_type=TransactionType.REFUND,
            description=f"Возврат за заказ #{order_id}",
            order_id=order_id,
        )

        # Обновляем статусы
        payment.status = "refunded"
        order.status = "refunded"
        await session.commit()

        # 📊 Логируем возврат средств
        log_refund(payment.user_id, order_id, payment.amount_usd)

        logger.info(
            "Refund processed: order=%s user=%s amount=%.2f new_balance=%d",
            order_id, payment.user_id, payment.amount_usd, new_balance
        )

        # Уведомляем пользователя
        try:
            await bot.send_message(
                payment.user_id,
                f"♻️ <b>Возврат средств</b>\n\n"
                f"Заказ #{order_id} отменён.\n"
                f"💰 На баланс возвращено: <b>${payment.amount_usd:.2f}</b>\n"
                f"💳 Текущий баланс: ${new_balance / 100:.2f}",
            )
        except Exception:
            logger.exception("Failed to notify user %s about refund", payment.user_id)

    await callback.message.edit_text(f"✅ Возврат по заказу #{order_id} оформлен.")
    await callback.answer()


@router.callback_query(F.data == "cancel_checkout")
async def cancel_checkout(callback: CallbackQuery):
    await callback.message.edit_text("❌ Оформление отменено.")
    await callback.answer()

# ==================== Просмотр истории баланса (для пользователя) ====================
# app/bot/handlers.py

@router.callback_query(F.data == "balance_history")
async def show_balance_history(callback: CallbackQuery):
    async with async_session() as session:
        txs = await get_user_balance_history(
            session, callback.from_user.id, limit=10
        )

    if not txs:
        await callback.message.answer("📭 История транзакций пуста.")
        await callback.answer()
        return

    text = "📋 <b>Последние операции:</b>\n\n"
    for tx in txs:
        sign = "+" if tx.amount_cents > 0 else ""
        amount_str = f"{sign}{tx.amount_cents / 100:.2f}$"
        type_emoji = {
            "deposit": "📥",
            "order_payment": "🛒",
            "refund": "♻️",
            "admin_adjustment": "⚙️",
        }.get(tx.transaction_type, "•")

        text += f"{type_emoji} {amount_str} | {tx.description or tx.transaction_type}\n"
        text += f"   Баланс после: ${tx.balance_after / 100:.2f}\n"
        text += f"   {tx.created_at.strftime('%d.%m %H:%M')}\n\n"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ==================== Баланс ====================
@router.message(F.text == "💳 Баланс")
async def show_balance(message: Message):
    async with async_session() as session:
        stmt = select(User).where(User.id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()

    balance_usd = (user.balance / 100) if user else 0.0
    await message.answer(
        f"💳 <b>Ваш баланс:</b> <b>${balance_usd:.2f}</b>",
        reply_markup=balance_kb(),
    )


# ==================== Пополнение баланса ====================
@router.callback_query(F.data == "topup_start")
async def topup_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "🪙 <b>Выберите монету для пополнения:</b>",
        reply_markup=topup_currency_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_cur_"))
async def topup_currency_selected(callback: CallbackQuery, state: FSMContext):
    ticker = callback.data.removeprefix("topup_cur_")
    if ticker not in TOPUP_CURRENCIES:
        await callback.answer("❌ Неизвестная монета", show_alert=True)
        return

    cur_name, _ = TOPUP_CURRENCIES[ticker]
    await state.update_data(currency=ticker, currency_name=cur_name)
    await state.set_state(TopUpStates.waiting_for_amount)

    await callback.message.edit_text(
        f"✅ Выбрано: <b>{cur_name}</b>\n\n"
        f"💰 Введите сумму пополнения в USD\n"
        f"(минимум ${settings.TOPUP_MIN_USD:.0f}):",
        reply_markup=cancel_topup_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "topup_cancel")
async def topup_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Пополнение отменено.")
    await callback.answer()


@router.message(TopUpStates.waiting_for_amount)
async def topup_amount_received(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
    except (ValueError, AttributeError):
        await message.answer(
            "❌ Введите число, например: <code>5</code> или <code>10.50</code>",
            reply_markup=cancel_topup_kb(),
        )
        return

    if amount < settings.TOPUP_MIN_USD:
        await message.answer(
            f"⚠️ Минимальная сумма: ${settings.TOPUP_MIN_USD:.0f}",
            reply_markup=cancel_topup_kb(),
        )
        return

    data = await state.get_data()
    ticker = data.get("currency", settings.TOPUP_CURRENCY)
    cur_name = data.get("currency_name", ticker)

    await state.clear()
    await message.answer("⏳ Получаем курс и генерируем адрес...")

    # Получаем актуальный курс USD за 1 единицу монеты
    try:
        try:
            price_usd = await asyncio.wait_for(
                get_price_usd(ticker),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("Timeout getting price for ticker: %s", ticker)
            await message.answer(
                "⏱️ Сервис курсов временно недоступен. Попробуйте позже.",
                reply_markup=topup_currency_kb(),
            )
            return
    except Exception as e:
        logger.error("rates error: %s", e)
        await message.answer(
            "❌ Не удалось получить курс. Попробуйте чуть позже.",
            reply_markup=topup_currency_kb(),
        )
        return

    # Применяем комиссию к сумме в USD, затем конвертируем в crypto
    fee_mul = 1 + settings.TOPUP_FEE_PERCENT / 100
    pay_usd = amount * fee_mul
    amount_crypto = usd_to_crypto(pay_usd, price_usd, decimals=8)
    amount_str = f"{amount_crypto:.8f}"

    async with async_session() as session:
        topup = TopUp(
            user_id=message.from_user.id,
            amount_usd=amount,
            amount_usdt=amount_crypto,
            rate_usd=price_usd,
            address="",
            label="__pending__",
            status="pending",
        )
        session.add(topup)
        await session.flush()

        label = f"topup_{topup.id}"
        try:
            try:
                addr = await asyncio.wait_for(
                    generate_address(label, currency=ticker),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error("Timeout generating address for ticker: %s", ticker)
                await session.rollback()
                await message.answer(
                    f"⏱️ <b>{cur_name}</b> сервис временно недоступен.\n\n"
                    "Пожалуйста, выберите другую монету:",
                    reply_markup=topup_currency_kb(),
                )
                return
        except RuntimeError as e:
            err = str(e)
            logger.error("generate_address error: %s", err)
            await session.rollback()
            if "ip_not_allowed" in err:
                await message.answer(
                    f"⚠️ <b>{cur_name}</b> временно недоступна.\n\n"
                    "Пожалуйста, выберите другую монету:",
                    reply_markup=topup_currency_kb(),
                )
            elif "currency_not_found" in err:
                await message.answer(
                    "❌ Монета не поддерживается. Выберите другую:",
                    reply_markup=topup_currency_kb(),
                )
            else:
                await message.answer("❌ Ошибка платёжного сервиса. Попробуйте позже.")
            return
        except Exception as e:
            logger.error("generate_address unexpected error: %s", e)
            await session.rollback()
            await message.answer("❌ Не удалось создать адрес. Попробуйте позже.")
            return

        topup.address = addr.address
        topup.label = label
        await session.commit()

        # 📊 Логируем инициирование пополнения
        log_topup_initiated(message.from_user.id, topup.id, amount, ticker, addr.address)

        request_num = 1_000_000_000 + topup.id
        address = addr.address

    # Форматируем курс компактно (много знаков для дешёвых монет)
    if price_usd >= 1:
        rate_str = f"${price_usd:,.2f}"
    else:
        rate_str = f"${price_usd:,.6f}"

    text = (
        f"🪙 <b>Пополнение с помощью: {cur_name}</b>\n"
        f"🔹 <b>Заявка:</b> №{request_num}\n"
        f"💲 <b>Баланс будет пополнен на:</b> {amount:.2f} $\n"
        f"📈 <b>Курс:</b> 1 {ticker} = {rate_str}\n\n"
        f"💼 <b>Адрес:</b>\n<code>{address}</code>\n"
        f"🪙 <b>Сумма к оплате:</b> {amount_str} {ticker} ❗️\n\n"
        f"❗️Пожалуйста, переведите минимум {amount_str} {ticker}!\n"
        f"❗️Если вы отправите меньше {amount_str} — зачисление не состоится!\n\n"
        f"⚠️ <b>РЕКВИЗИТЫ ДЕЙСТВИТЕЛЬНЫ ТОЛЬКО ДЛЯ ОДНОГО ПЛАТЕЖА</b> ❗️\n"
        f"❌❌❌ Если вы отправите меньше {amount_str}, деньги будут потеряны и мы не сможем помочь!"
    )

    photo = BufferedInputFile(_make_qr(address), filename="qr.png")
    await message.answer_photo(photo, caption=text)


# ==================== ОТЛАДКА: ловим ВСЕ остальные callback'и ====================
@router.callback_query()
async def catch_all_callbacks(callback: CallbackQuery):
    print(f"⚠️ НЕОБРАБОТАННЫЙ CALLBACK: {callback.data}")
    await callback.answer(f"⚠️ No handler for: {callback.data}", show_alert=True)

