import importlib

libs = [
    "aiogram", "sqlalchemy", "asyncpg", "redis", "httpx",
    "pydantic_settings", "alembic", "fastapi", "uvicorn", "cryptography", "structlog"
]

print("📦 Проверка установленных библиотек:")
for lib in libs:
    try:
        mod = importlib.import_module(lib)
        ver = getattr(mod, "__version__", "N/A")
        print(f"  ✅ {lib:15} {ver}")
    except ImportError:
        print(f"  ❌ {lib:15} не найден")