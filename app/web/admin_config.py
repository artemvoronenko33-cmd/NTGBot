# app/web/admin_config.py
"""
Конфигурация админ-панели SQLAdmin
✅ Все функции на уровне модуля — никаких NameError
"""

# ============================================================================
# 🔗 ИМПОРТЫ
# ============================================================================

from sqladmin import ModelView
from starlette.responses import RedirectResponse, JSONResponse
from sqlalchemy import select, func, text
from app.db.engine import async_session
from app.db.models import User, Product, Category, Order, OrderItem, StatsCache, StatsDaily, StatsProduct
from app.services.stats_updater import refresh_stats
from datetime import datetime, timedelta, date
import json
from markupsafe import Markup  # ✅ Для рендеринга HTML

# ============================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (на уровне модуля ✅)
# ============================================================================

def format_number(value) -> str:
    """Форматирует число без валюты (для счётчиков)"""
    try:
        return f"{int(float(value)):,}" if value is not None else "0"
    except (ValueError, TypeError):
        return str(value or "0")


def format_currency(value, symbol: str = "$") -> str:
    """Форматирует число как валюту"""
    try:
        return f"{symbol}{float(value):,.2f}" if value is not None else f"{symbol}0.00"
    except (ValueError, TypeError):
        return f"{symbol}0.00"


def format_date(value) -> str:
    """Форматирует дату/время"""
    if not value:
        return "—"
    try:
        return value.strftime("%d.%m %H:%M") if hasattr(value, 'strftime') else str(value)
    except:
        return str(value)


def format_date_only(value) -> str:
    """Форматирует только дату (без времени)"""
    if not value:
        return "—"
    try:
        return value.strftime("%d.%m.%Y") if hasattr(value, 'strftime') else str(value)
    except:
        return str(value)


def _format_metric_value(obj, prop) -> str:
    """
    Универсальный форматтер для метрик:
    - выручка → с $
    - счётчики → без $
    """
    value = getattr(obj, 'metric_value', None)
    name = getattr(obj, 'metric_name', '')

    # Метрики в валюте
    if name in ['total_revenue', 'balance', 'revenue']:
        return format_currency(value, symbol="$")
    # Метрики-счётчики
    elif name in ['total_users', 'total_orders', 'active_products', 'qty_sold']:
        return format_number(value)
    # По умолчанию — просто число
    else:
        return format_number(value) if value is not None else "0"


def render_refresh_button(obj, prop) -> str:
    """Рендерит кнопку обновления с JS-обработчиком"""
    html = f"""
    <button class="btn btn-sm btn-primary" 
            onclick="refreshStats(this)">🔄 Обновить</button>
    <script>
    async function refreshStats(btn) {{
        btn.disabled = true;
        const original = btn.innerHTML;
        btn.innerHTML = '⏳...';
        try {{
            const resp = await fetch('/api/refresh-stats', {{ method: 'POST' }});
            const data = await resp.json();
            if (resp.ok) {{
                btn.innerHTML = '✅';
                setTimeout(() => location.reload(), 500);
            }} else {{
                btn.innerHTML = '❌';
                alert('Ошибка: ' + (data.error || 'Неизвестная'));
            }}
        }} catch(e) {{
            btn.innerHTML = '⚠️';
            console.error(e);
        }} finally {{
            setTimeout(() => {{ btn.disabled = false; btn.innerHTML = original; }}, 3000);
        }}
    }}
    </script>
    """
    return Markup(html)  # ✅ Помечаем как безопасный HTML


# ============================================================================
# 📊 ADMIN: СВОДНАЯ СТАТИСТИКА
# ============================================================================

class StatsAdmin(ModelView, model=StatsCache):
    """Текущие метрики"""

    column_list = [
        "refresh_action",
        StatsCache.metric_name,
        StatsCache.metric_value,
        StatsCache.updated_at,
        StatsCache.description
    ]

    column_labels = {
        "refresh_action": "Действие",
        StatsCache.metric_name: "Метрика",
        StatsCache.metric_value: "Значение",
        StatsCache.updated_at: "Обновлено",
        StatsCache.description: "Описание"
    }

    # ✅ Все форматтеры ссылаются на функции модульного уровня
    column_formatters = {
        "refresh_action": render_refresh_button,
        StatsCache.metric_value: _format_metric_value,
        StatsCache.updated_at: lambda obj, prop: format_date(obj.updated_at),
    }

    column_filters = []  # Отключаем для совместимости с SQLAlchemy 2.0
    column_searchable_list = [StatsCache.metric_name, StatsCache.description]
    column_sortable_list = [StatsCache.metric_name, StatsCache.metric_value, StatsCache.updated_at]
    column_default_sort = [(StatsCache.metric_name, False)]

    can_create = False
    can_delete = False
    can_edit = False

    name = "📊 Статистика"
    name_plural = "📊 Статистика"
    icon = "fa-solid fa-chart-line"
    page_size = 20


# ============================================================================
# 📅 ADMIN: ЕЖЕДНЕВНАЯ СТАТИСТИКА          (DELETE)
# ============================================================================

class StatsDailyAdmin(ModelView, model=StatsDaily):
    """История метрик по дням"""

    column_list = [
        "refresh_action",
        StatsDaily.stat_date,
        StatsDaily.metric_name,
        StatsDaily.metric_value
    ]

    column_labels = {
        "refresh_action": "Действие",
        StatsDaily.stat_date: "Дата",
        StatsDaily.metric_name: "Метрика",
        StatsDaily.metric_value: "Значение"
    }

    column_formatters = {
        "refresh_action": render_refresh_button,
        StatsDaily.metric_value: _format_metric_value,
        StatsDaily.stat_date: lambda obj, prop: format_date_only(obj.stat_date),
    }

    column_filters = []
    column_searchable_list = [StatsDaily.metric_name]
    column_sortable_list = [StatsDaily.stat_date, StatsDaily.metric_value]
    column_default_sort = [(StatsDaily.stat_date, True)]

    can_create = False
    can_delete = True
    can_edit = False

    name = "📅 По дням"
    name_plural = "📅 По дням"
    icon = "fa-solid fa-calendar-days"
    page_size = 50


# ============================================================================
# 🏆 ADMIN: СТАТИСТИКА ПО ТОВАРАМ         (DELETE)
# ============================================================================

class StatsProductsAdmin(ModelView, model=StatsProduct):
    """Топ товаров по выручке"""

    column_list = [
        "refresh_action",
        StatsProduct.product_name,
        StatsProduct.revenue,
        StatsProduct.qty_sold,
        StatsProduct.period_start,
        StatsProduct.period_end
    ]

    column_labels = {
        "refresh_action": "Действие",
        StatsProduct.product_name: "Товар",
        StatsProduct.revenue: "Выручка",
        StatsProduct.qty_sold: "Продано",
        StatsProduct.period_start: "С",
        StatsProduct.period_end: "По"
    }

    column_formatters = {
        "refresh_action": render_refresh_button,
        StatsProduct.revenue: lambda obj, prop: format_currency(obj.revenue, symbol="$"),
        StatsProduct.qty_sold: lambda obj, prop: format_number(obj.qty_sold),
        StatsProduct.period_start: lambda obj, prop: format_date_only(obj.period_start),
        StatsProduct.period_end: lambda obj, prop: format_date_only(obj.period_end),
    }

    column_filters = []
    column_sortable_list = [StatsProduct.revenue, StatsProduct.qty_sold]
    column_default_sort = [(StatsProduct.revenue, True)]

    can_create = False
    can_delete = True
    can_edit = False

    name = "🏆 Товары"
    name_plural = "🏆 Товары"
    icon = "fa-solid fa-trophy"
    page_size = 20


# ============================================================================
# 👥 USERS, 📦 PRODUCTS, 🗂 CATEGORIES, 📋 ORDERS (без изменений)
# ============================================================================

class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.username, User.balance, User.language_code, User.created_at]
    column_labels = {User.username: "Имя", User.balance: "Баланс"}
    column_searchable_list = [User.username, User.id]
    column_sortable_list = [User.id, User.created_at, User.balance]
    column_default_sort = [(User.created_at, True)]
    can_create = False
    can_delete = False
    can_edit = True
    name = "Пользователь"
    name_plural = "👥 Пользователи"
    icon = "fa-solid fa-users"
    column_formatters = {User.balance: lambda obj, prop: format_currency(obj.balance, symbol="$")}


class ProductAdmin(ModelView, model=Product):
    column_list = [Product.id, Product.name, Product.price, Product.is_active, Product.category_id]
    column_labels = {Product.name: "Название", Product.price: "Цена"}
    column_searchable_list = [Product.name]
    column_filters = []
    column_editable_list = [Product.price, Product.is_active]
    can_create = True
    can_delete = True
    can_edit = True
    name = "Товар"
    name_plural = "📦 Товары"
    icon = "fa-solid fa-box"
    column_formatters = {Product.price: lambda obj, prop: format_currency(obj.price, symbol="$")}


class CategoryAdmin(ModelView, model=Category):
    column_list = [Category.id, Category.name]
    column_labels = {Category.name: "Название"}
    column_searchable_list = [Category.name]
    can_create = True
    can_delete = True
    can_edit = True
    name = "Категория"
    name_plural = "🗂 Категории"
    icon = "fa-solid fa-folder"


# app/web/admin_config.py

class OrderAdmin(ModelView, model=Order):
    """Заказы — минимализм и стабильность"""

    # === СПИСОК (таблица) ===
    column_list = [Order.id, Order.user_id, Order.total_price, Order.status, Order.created_at]
    column_labels = {
        Order.user_id: "ID Клиента",
        Order.total_price: "Сумма",
        Order.status: "Статус",
        Order.created_at: "Дата"
    }
    column_searchable_list = [Order.id, Order.user_id]
    column_sortable_list = [Order.id, Order.created_at, Order.total_price]
    column_default_sort = [(Order.id, True)]
    column_filters = []

    can_create = False
    can_delete = False
    can_edit = True
    can_view_details = True

    name = "Заказ"
    name_plural = "📋 Заказы"
    icon = "fa-solid fa-cart-shopping"
    page_size = 50

    # Форматтеры для СПИСКА (здесь obj — экземпляр Order ✅)
    column_formatters = {
        Order.total_price: lambda obj, prop: format_currency(obj.total_price, "$"),
    }

    # === ДЕТАЛИ (просмотр) ===
    # ✅ Только реальные атрибуты модели
    column_details_list = [
        Order.id,
        Order.user,  # 👤 Клиент
        Order.total_price,
        Order.status,
        Order.created_at,
        Order.items,  # 🛒 Товары
        #Order.status_history  # 📜 История
    ]

    # ❌ УБИРАЕМ column_formatters_detail — пусть SQLAdmin форматирует сам!


    # ✅ Загружаем связанные данные
    column_select_related_list = ["user", "items", "items.product", "status_history"]


# ============================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def get_status_color(status: str) -> str:
    """Возвращает цвет бейджа для статуса"""
    colors = {
        "paid": "success",
        "completed": "success",
        "shipped": "info",
        "created": "warning",
        "cancelled": "danger"
    }
    return colors.get(status, "secondary")





def format_history_list(history) -> str:
    """Форматирует историю статусов в простой текст"""
    if not history:
        return "Нет истории"

    if hasattr(history, '__iter__') and not isinstance(history, str):
        parts = []
        for h in sorted(history, key=lambda x: x.changed_at or datetime.min):
            date_str = h.changed_at.strftime("%d.%m %H:%M") if h.changed_at else ""
            old = h.old_status or "—"
            parts.append(f"{old} → {h.new_status} ({date_str})")
        return "; ".join(parts)
    return str(history)


# ============================================================================
# РЕГИСТРАЦИЯ ВИДОВ
# ============================================================================

ADMIN_VIEWS = [
    #StatsAdmin,  # 📊 Сводная
    # StatsDailyAdmin,  # 📅 По дням
    # StatsProductsAdmin,  # 🏆 Товары
    UserAdmin,
    ProductAdmin,
    CategoryAdmin,
    OrderAdmin,
]


def format_money():
    return None