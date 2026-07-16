import asyncio
import sys

if sys.platform == "win32":
    # Создаём и устанавливаем политику
    loop = asyncio.SelectorEventLoop()
    asyncio.set_event_loop(loop)
    print("SelectorEventLoop set directly")

import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from aiogram import Dispatcher
from fastapi import FastAPI

from app.bot.bot_instance import bot
from app.bot.menu_user.hd_user import router
from app.web.app import create_app
from config import settings

from app.db.middleware import DBSessionMiddleware
from app.bot.menu_work.hb_work import router as worker_router
from app.bot.menu_admin.hd_admin import router as admin_router

from app.services.order_queue import OrderQueueService

from app.db.middleware import MaintenanceMiddleware

# ====================== WINDOWS FIX ======================
if sys.platform == "win32":
    # Создаём и устанавливаем политику
    loop = asyncio.SelectorEventLoop()
    asyncio.set_event_loop(loop)
    print("[OK] SelectorEventLoop set directly")

# ====================== ЛОГИРОВАНИЕ ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.ERROR)


# ====================== LIFESPAN ======================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Запуск бота и веб-сервера...")
    yield
    logger.info("🛑 Начинаем graceful shutdown...")
    await bot.session.close()
    logger.info("[OK] Ресурсы закрыты.")


def create_web_app() -> FastAPI:
    app = create_app()

    @app.get("/health")
    @app.get("/")
    async def health_check():
        return {"status": "healthy"}

    # Привязываем lifespan
    app.router.lifespan_context = lifespan
    return app


# ====================== BOT ======================
async def run_bot() -> None:
    dp = Dispatcher()

    session_middleware = DBSessionMiddleware()

    dp.message.middleware(session_middleware)
    dp.callback_query.middleware(session_middleware)
    dp.message.middleware(MaintenanceMiddleware())
    dp.callback_query.middleware(MaintenanceMiddleware())

    dp.include_router(router)
    dp.include_router(admin_router)
    dp.include_router(worker_router)

    # Запускаем фоновую задачу
    processor_task = asyncio.create_task(order_processor())

    logger.info("🤖 Aiogram polling запущен...")
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            handle_signals=False
        )
    except Exception as e:
        if not isinstance(e, asyncio.CancelledError):
            logger.error(f"Polling error: {e}")
    finally:
        # Корректно отменяем фоновую задачу
        if not processor_task.done():
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Polling завершён.")


async def order_processor():
    """Надёжная обработка заказов с автоперезапуском и уведомлениями"""
    from app.db.engine import async_session
    queue_service = OrderQueueService()
    error_count = 0
    max_errors_before_cooldown = 5
    cooldown_seconds = 300  # 5 минут

    while True:
        try:
            async with async_session() as session:
                processed = await queue_service.process_single_order(session)

            error_count = 0
            await asyncio.sleep(2 if processed else 5)  # разная пауза

        except asyncio.CancelledError:
            logger.info("Order processor остановлен gracefully")
            break
        except Exception as e:
            error_count += 1
            logger.error(
                f"Ошибка order_processor (попытка {error_count}/{max_errors_before_cooldown}): {e}",
                exc_info=True
            )

            # Уведомление админа
            if error_count >= max_errors_before_cooldown:
                try:
                    from app.bot.bot_instance import bot
                    await bot.send_message(
                        settings.ADMIN_IDS[0],
                        f"🚨 order_processor упал {error_count} раз подряд!\n"
                        f"Последняя ошибка: {str(e)[:500]}"
                    )
                except Exception as notify_err:
                    logger.error(f"Failed to notify admin: {notify_err}")

            await asyncio.sleep(cooldown_seconds if error_count >= max_errors_before_cooldown else 20)


# ====================== MAIN ======================
async def main() -> None:
    web_app = create_web_app()

    config = uvicorn.Config(
        web_app,
        host=settings.WEBHOOK_HOST,
        port=settings.WEBHOOK_PORT,
        log_level="warning",
        timeout_keep_alive=65,
    )
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(
            run_bot(),
            server.serve(),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Приложение завершило работу.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Необработанная ошибка: {e}")