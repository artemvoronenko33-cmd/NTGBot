# app/web/main.py
"""
Точка входа: FastAPI + SQLAdmin + API + Dashboard
✅ ИСПРАВЛЕНО: импорт SessionMiddleware из starlette
"""

# ============================================================================
# 🔗 ИМПОРТЫ
# ============================================================================

# FastAPI
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

# Starlette (для middleware и редиректов)
from starlette.middleware.sessions import SessionMiddleware  # ✅ ИСПРАВЛЕНО
from starlette.responses import RedirectResponse, JSONResponse

# WSGI для SQLAdmin
from fastapi.middleware.wsgi import WSGIMiddleware

# SQLAlchemy
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

# SQLAdmin
from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend

from app.db.models import Product
# Проектные модули
from config import settings
from app.db.engine import async_session
from app.web.admin_config import ADMIN_VIEWS

from app.web.admin_charts import setup_charts  # ✅ Импортируем установщик
import os


# ============================================================================
# 🔐 АВТОРИЗАЦИЯ ДЛЯ SQLADMIN — ✅ ГАРАНТИРОВАННО РАБОЧАЯ ВЕРСИЯ
# ============================================================================

class AdminAuth(AuthenticationBackend):
    """
    Защита админки паролем — универсальная совместимость
    """

    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        # ✅ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: устанавливаем middlewares как атрибут экземпляра
        # Это работает во всех версиях SQLAdmin
        object.__setattr__(self, 'middlewares', [])

    async def login(self, request: Request) -> bool:
        """Обработка формы входа"""
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        if username == settings.ADMIN_LOGIN and password == settings.ADMIN_PASSWORD:
            request.session.update({"authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        """Выход из системы"""
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        """Проверка авторизации для каждого запроса"""
        # Если сессии ещё нет — создаём пустую (защита от ошибок)
        if not hasattr(request, 'session'):
            request.session = {}
        return request.session.get("authenticated", False)


# ============================================================================
# 🗄 ПОДКЛЮЧЕНИЕ К БД
# ============================================================================

DB_URL_SYNC = settings.DB_URL.replace("+asyncpg", "", 1)
sync_engine = create_engine(DB_URL_SYNC, echo=False, pool_pre_ping=True)
sync_session_maker = sessionmaker(bind=sync_engine)

# ============================================================================
# 🚀 СОЗДАНИЕ ПРИЛОЖЕНИЯ
# ============================================================================

app = FastAPI(
    title="🤖 Bot Admin Panel",
    description="Админка + API + Dashboard",
    version="1.0"
)

# ✅ Обязательно добавьте этот middleware!
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.ADMIN_SECRET_KEY,  # Ключ из .env
    https_only=False,
    same_site="lax"
)

# ✅ Подключаем графики (роутер + кнопку в меню)
setup_charts(app)

admin = Admin(
    app=app,
    engine=sync_engine,
    session_maker=sync_session_maker,
    title="🤖 Bot Admin",
    logo_url="https://cdn-icons-png.flaticon.com/512/4712/4712035.png",
    favicon_url="https://cdn-icons-png.flaticon.com/512/4712/4712035.png",
    base_url="/admin",
    authentication_backend=AdminAuth(secret_key=settings.ADMIN_SECRET_KEY),
)


# Регистрация моделей
for view_class in ADMIN_VIEWS:
    admin.add_view(view_class)


# ============================================================================
# 🔗 MIDDLEWARE: Кнопка "📈 Графики" в меню (на уровне модуля!)
# ============================================================================

@app.middleware("http")
async def inject_charts_link(request: Request, call_next):
    """Добавляет кнопку '📈 Графики' в боковое меню админки"""
    response = await call_next(request)

    # Внедряем только в HTML-страницы админки
    if response.headers.get("content-type", "").startswith("text/html") and "/admin" in str(request.url):
        body = b"".join([chunk async for chunk in response.body_iterator])

        # Скрипт для добавления кнопки (кириллица в .encode('utf-8'))
        inject_script = """
        <script>
        document.addEventListener('DOMContentLoaded', () => {
            const menu = document.querySelector('.sidebar-menu') || document.querySelector('.navbar-nav');
            if (menu && !document.getElementById('charts-sidebar-link')) {
                const li = document.createElement('li');
                li.className = 'nav-item';
                li.innerHTML = '<a class="nav-link" href="/admin/charts" id="charts-sidebar-link"><span class="nav-link-icon d-md-none d-lg-inline-block"><i class="fa-solid fa-chart-line"></i></span><span class="nav-link-title">📈 Графики</span></a>';
                menu.appendChild(li);
            }
        });
        </script>
        """.encode('utf-8')

        body = body.replace(b'</body>', inject_script + b'</body>')

        from starlette.responses import Response
        response.headers["content-length"] = str(len(body))
        return Response(content=body, status_code=response.status_code, headers=dict(response.headers),
                        media_type=response.media_type)

    return response


# ============================================================================
# 🔄 API: Обновление статистики (вне /admin!)
# ============================================================================

@app.post("/api/refresh-stats")  # ✅ Изменили путь: НЕ /admin/api/...
async def refresh_stats_endpoint(request: Request):
    """Обновление статистики по кнопке"""

    # Проверка авторизации
    if not request.session or not request.session.get("authenticated"):
        from starlette.responses import JSONResponse
        return JSONResponse(status_code=403, content={"error": "Unauthorized"})

    try:
        from app.services.stats_updater import refresh_stats
        async with async_session() as db:
            result = await refresh_stats(db, notify_admin=False)

        return {"status": "ok", "message": "Статистика обновлена"}
    except Exception as e:
        from starlette.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": str(e)})


# ============================================================================
# 🔗 ЗАВИСИМОСТИ ДЛЯ API
# ============================================================================

async def get_db():
    """Зависимость для асинхронной сессии БД"""
    async with async_session() as session:
        yield session


# ============================================================================
# 📊 API: СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ
# ============================================================================

@app.get("/admin/api/user-stats")
async def get_user_stats(
        db: AsyncSession = Depends(get_db),
        x_admin_token: str = Header(...)
):
    """Статистика пользователей (защищено токеном)"""
    if x_admin_token != settings.ADMIN_API_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный токен")

    from app.db.models import User, Order

    stmt = select(
        User.id, User.username, User.balance,
        func.count(Order.id).label("orders_count"),
        func.sum(Order.total_price).label("total_spent"),
        func.max(Order.created_at).label("last_order_at")
    ).join(Order, Order.user_id == User.id, isouter=True
           ).group_by(User.id).order_by(func.count(Order.id).desc())

    result = await db.execute(stmt)
    return [
        {
            "user_id": r.id,
            "username": r.username,
            "balance": r.balance,
            "orders_count": r.orders_count or 0,
            "total_spent": float(r.total_spent or 0),
            "last_order_at": r.last_order_at.isoformat() if r.last_order_at else None
        }
        for r in result.all()
    ]


# ============================================================================
# 📦 API: ДЕТАЛИ ЗАКАЗА
# ============================================================================

@app.get("/admin/api/orders/{order_id}")
async def get_order_details(
        order_id: int,
        db: AsyncSession = Depends(get_db),
        x_admin_token: str = Header(...)
):
    from fastapi import HTTPException
    from app.db.models import Order, OrderItem, Product, User

    """Детали заказа с товарами"""
    if x_admin_token != settings.ADMIN_API_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный токен")

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    user = (await db.execute(select(User).where(User.id == order.user_id))).scalar_one_or_none()
    items = (await db.execute(
        select(OrderItem, Product).join(Product, OrderItem.product_id == Product.id)
        .where(OrderItem.order_id == order_id)
    )).all()

    return {
        "order": {"id": order.id, "status": order.status, "total_price": order.total_price},
        "user": {"id": user.id if user else None, "username": user.username if user else None},
        "items": [
            {
                "product_name": prod.name,
                "quantity": oi.quantity,
                "price": oi.price_at_purchase,
                "subtotal": oi.quantity * oi.price_at_purchase
            }
            for oi, prod in items
        ]
    }


# ============================================================================
# 📈 API: ПРОДАЖИ ТОВАРОВ
# ============================================================================

@app.get("/admin/api/product-sales")
async def get_product_sales(
        days: int = 30,
        db: AsyncSession = Depends(get_db),
        x_admin_token: str = Header(...)
):
    """Статистика продаж товаров"""
    if x_admin_token != settings.ADMIN_API_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный токен")

    from datetime import datetime, timedelta
    from app.db.models import OrderItem, Product, Order

    since = datetime.utcnow() - timedelta(days=days)

    stmt = select(
        Product.id, Product.name,
        func.sum(OrderItem.quantity).label("total_qty"),
        func.sum(OrderItem.quantity * OrderItem.price_at_purchase).label("revenue")
    ).join(Order, Order.id == OrderItem.order_id) \
        .join(Product, Product.id == OrderItem.product_id) \
        .where(Order.created_at >= since, Order.status.in_(["paid", "completed", "shipped"])
               ).group_by(Product.id, Product.name).order_by(func.sum(OrderItem.quantity).desc())

    result = await db.execute(stmt)

    return {
        "period_days": days,
        "products": [
            {
                "name": r.name,
                "quantity_sold": r.total_qty or 0,
                "revenue": float(r.revenue or 0)
            }
            for r in result.all()
        ]
    }



# ============================================================================
# 🔗 ПРОСТЫЕ ЭНДПОИНТЫ
# ============================================================================

@app.get("/")
def root():
    return {
        "admin_panel": "/admin (требует авторизации)",
        "📊 statistics": "/stats (требует авторизации)",  # ✅ Новая кнопка
        "api_docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "bot-admin-api"}


