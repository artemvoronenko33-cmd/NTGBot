# check_sync_connection.py
from sqlalchemy import create_engine, text
from config import settings

print(f"🔹 DB_URL: {settings.DB_URL}")
print(f"🔹 DB_URL_SYNC: {settings.DB_URL_SYNC}")
print(f"🔹 DB_URL_SYNC_FINAL: {settings.DB_URL_SYNC_FINAL}")

try:
    engine = create_engine(settings.DB_URL_SYNC_FINAL, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT current_user, version()"))
        user, version = result.one()
        print(f"✅ Подключение успешно!")
        print(f"   👤 Пользователь БД: {user}")
        print(f"   🐘 Версия: {version[:50]}...")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    print("\n💡 Проверьте:")
    print("   1. Контейнер PostgreSQL запущен: docker compose ps")
    print("   2. Пароль в DB_URL_SYNC совпадает с .env")
    print("   3. Пользователь botuser имеет права: docker compose exec postgres psql -U botuser -d botdb -c '\\du'")