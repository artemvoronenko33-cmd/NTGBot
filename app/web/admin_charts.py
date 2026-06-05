# app/web/admin_charts.py
"""
Модуль графиков и аналитики
✅ Маршрут вынесен на /bot/charts (чтобы SQLAdmin не перехватывал)
✅ Кнопка в меню добавляется автоматически через middleware
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, extract
from app.db.engine import async_session
from app.db.models import Order, Product, OrderItem
from datetime import datetime, timedelta
import json

router = APIRouter()


# ============================================================================
# 📈 ЭНДПОИНТ: Отрисовка страницы графиков
# ============================================================================

@router.get("/bot/charts", response_class=HTMLResponse)
async def charts_page(request: Request):
    """Страница с графиками и аналитикой"""

    # 1. Проверка авторизации
    if not request.session.get("authenticated"):
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with async_session() as db:
            # --- ДАННЫЕ 1: Выручка по дням (30 дней) ---
            since = datetime.utcnow() - timedelta(days=30)
            rev_data = (await db.execute(
                select(
                    func.date_trunc('day', Order.created_at).label('d'),
                    func.sum(Order.total_price).label('r'),
                    func.count(Order.id).label('c')
                )
                .where(Order.created_at >= since, Order.status.in_(["paid", "completed", "shipped"]))
                .group_by('d').order_by('d')
            )).all()

            # --- ДАННЫЕ 2: Топ-10 товаров по выручке ---
            top_data = (await db.execute(
                select(
                    Product.name,
                    func.sum(OrderItem.quantity * OrderItem.price_at_purchase).label('rev'),
                    func.sum(OrderItem.quantity).label('qty')
                )
                .join(OrderItem, Product.id == OrderItem.product_id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.status.in_(["paid", "completed", "shipped"]))
                .group_by(Product.id, Product.name)
                .order_by(func.sum(OrderItem.quantity * OrderItem.price_at_purchase).desc())
                .limit(10)
            )).all()

            # --- ДАННЫЕ 3: Активность по дням недели ---
            act_data = (await db.execute(
                select(func.extract('dow', Order.created_at).label('w'), func.count(Order.id).label('c'))
                .where(Order.status.in_(["paid", "completed", "shipped"]))
                .group_by('w')
            )).all()

            day_names = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']
            act_map = {int(r.w): r.c for r in act_data}
            activity_counts = [act_map.get(i, 0) for i in range(7)]

    except Exception as e:
        return HTMLResponse(status_code=500,
                            content=f"<div class='p-4 text-center'><h3 class='text-danger'>❌ {str(e)[:200]}</h3><a href='/admin'>← Назад</a></div>")

    # --- ПОДГОТОВКА ДАННЫХ ДЛЯ JS ---
    rev_labels = [r.d.strftime('%d.%m') for r in rev_data]
    rev_vals = [float(r.r) if r.r else 0 for r in rev_data]
    ord_vals = [r.c for r in rev_data]

    prod_names = [p.name[:20] for p in top_data]  # Обрезаем длинные названия
    prod_rev = [float(p.rev) if p.rev else 0 for p in top_data]
    prod_qty = [p.qty for p in top_data]

    max_act = max(activity_counts) if activity_counts else 1

    # --- HTML ШАБЛОН ---
    html_content = f"""
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>📈 Графики</title>
<link href="https://cdn.jsdelivr.net/npm/tabler@1.0.0-beta20/dist/css/tabler.min.css" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
    body {{ background: #f6f9fb; font-family: system-ui, sans-serif; }}
    .card {{ margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .chart-box {{ position: relative; height: 300px; width: 100%; }}
    .hm {{ display: inline-block; width: 40px; height: 60px; margin: 4px; border-radius: 6px; text-align: center; line-height: 30px; font-size: 12px; font-weight: 700; color: #fff; }}
</style></head>
<body>
    <div class="page">
        <!-- Header -->
        <header class="navbar navbar-light bg-white border-bottom">
            <div class="container-xl d-flex justify-content-between align-items-center">
                <h1 class="navbar-brand mb-0">📈 Аналитика</h1>
                <a href="/admin" class="btn btn-outline-primary btn-sm">⬅️ Вернуться в админку</a>
            </div>
        </header>

        <!-- Content -->
        <div class="container-xl py-4">

            <!-- 1. Линейный график: Выручка и заказы -->
            <div class="card">
                <div class="card-header"><h3 class="card-title">📈 Выручка и заказы (последние 30 дней)</h3></div>
                <div class="card-body"><div class="chart-box"><canvas id="revChart"></canvas></div></div>
            </div>

            <!-- 2. Топ товаров -->
            <div class="row">
                <div class="col-lg-7">
                    <div class="card">
                        <div class="card-header"><h3 class="card-title">🏆 Топ товаров по выручке</h3></div>
                        <div class="card-body"><div class="chart-box"><canvas id="prodChart"></canvas></div></div>
                    </div>
                </div>
                <div class="col-lg-5">
                    <div class="card">
                        <div class="card-header"><h3 class="card-title">📊 По количеству продаж</h3></div>
                        <div class="card-body"><div class="chart-box"><canvas id="qtyChart"></canvas></div></div>
                    </div>
                </div>
            </div>

            <!-- 3. Тепловая карта: Активность по дням недели -->
            <div class="card">
                <div class="card-header"><h3 class="card-title">🗓️ Активность по дням недели (ср. заказов)</h3></div>
                <div class="card-body text-center py-4">
                    <div id="heatmap" class="d-flex flex-wrap justify-content-center">
                        {''.join(f'<span class="hm" style="background:hsl({120 - (v / max_act) * 120}, 70%, 45%)" title="{day_names[i]}: {v} заказов">{day_names[i]}<br>{v}</span>' for i, v in enumerate(activity_counts))}
                    </div>
                    <p class="text-muted small mt-3">🟢 Мало заказов | 🟡 Средне | 🔴 Много</p>
                </div>
            </div>

            <footer class="footer mt-4 py-3 text-center text-muted small">
                🤖 Bot Admin • Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}
            </footer>
        </div>
    </div>

    <!-- Scripts для графиков -->
    <script>
        // 1. График выручки
        new Chart(document.getElementById('revChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(rev_labels)},
                datasets: [
                    {{ label: 'Выручка ($)', data: {json.dumps(rev_vals)}, borderColor: '#206bc4', backgroundColor: 'rgba(32,107,196,0.1)', fill: true, tension: 0.3, yAxisID: 'y' }},
                    {{ label: 'Заказы', data: {json.dumps(ord_vals)}, borderColor: '#40c057', backgroundColor: 'rgba(64,192,87,0.1)', fill: true, tension: 0.3, yAxisID: 'y1' }}
                ]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, scales: {{ y: {{ position: 'left' }}, y1: {{ position: 'right', grid: {{ drawOnChartArea: false }} }} }} }}
        }});

        // 2. Топ товаров (Бар)
        new Chart(document.getElementById('prodChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(prod_names)},
                datasets: [{{ label: 'Выручка', data: {json.dumps(prod_rev)}, backgroundColor: 'rgba(54,162,235,0.7)' }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: {{ legend: {{ display: false }} }} }}
        }});

        // 3. Топ товаров (Круговая)
        new Chart(document.getElementById('qtyChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(prod_names)},
                datasets: [{{ data: {json.dumps(prod_qty)}, backgroundColor: ['#FF6384','#36A2EB','#FFCE56','#4BC0C0','#9966FF','#FF9F40','#C9CBCF','#4BC0C0','#36A2EB','#FF6384'] }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false }}
        }});
    </script>
</body></html>
    """
    return HTMLResponse(content=html_content)


# ============================================================================
# 🔗 ФУНКЦИЯ ПОДКЛЮЧЕНИЯ (Вызывается из main.py)
# ============================================================================

def setup_charts(app):
    """
    Подключает роутер графиков и добавляет кнопку в боковое меню SQLAdmin
    """

    # 1. Регистрируем маршруты
    app.include_router(router)

    # 2. Добавляем Middleware для внедрения кнопки в меню
    @app.middleware("http")
    async def inject_charts_button(request: Request, call_next):
        response = await call_next(request)

        # Внедряем только в HTML-страницы админки
        if response.headers.get("content-type", "").startswith("text/html") and "/admin" in str(request.url):
            body = b"".join([chunk async for chunk in response.body_iterator])

            # Скрипт, который находит меню и добавляет кнопку "Графики"
            # Используем .encode('utf-8') чтобы избежать ошибки с кириллицей в bytes
            inject_script = """
            <script>
            document.addEventListener('DOMContentLoaded', () => {
                const menu = document.querySelector('.sidebar-menu') || document.querySelector('.navbar-nav');
                if (menu && !document.getElementById('charts-sidebar-link')) {
                    const li = document.createElement('li');
                    li.className = 'nav-item';
                    // Ссылка ведет на /bot/charts (наш новый маршрут)
                    li.innerHTML = '<a class="nav-link" href="/bot/charts" id="charts-sidebar-link"><span class="nav-link-icon d-md-none d-lg-inline-block"><i class="fa-solid fa-chart-line"></i></span><span class="nav-link-title">📈 Графики</span></a>';
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