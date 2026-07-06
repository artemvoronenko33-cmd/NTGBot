import asyncio
import logging

import uvicorn
from aiogram import Dispatcher

from app.bot.bot_instance import bot
from app.bot.handlers import router
from app.web.app import create_app
from config import settings

from app.db.middleware import DBSessionMiddleware
from app.bot.handlers_worker import router as worker_router
from app.bot.handlers_admin import router as admin_router

from app.services.order_queue import OrderQueueService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

async def run_bot() -> None:
    dp = Dispatcher()

    # === Middleware ==
    session_middleware = DBSessionMiddleware()
    dp.message.middleware(session_middleware)
    dp.callback_query.middleware(session_middleware)

    dp.include_router(router)
    dp.include_router(admin_router)
    dp.include_router(worker_router)

    # === Background task для обработки заказов ===
    asyncio.create_task(order_processor())

    logging.info("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

async def order_processor():
    """Фоновая обработка заказов"""
    from app.db.engine import async_session
    from app.services.order_queue import OrderQueueService

    queue_service = OrderQueueService()

    while True:
        try:
            async with async_session() as session:
                # Запускаем обработку одной итерации
                await queue_service.process_single_order(session)
                await asyncio.sleep(2)  # небольшая пауза
        except Exception as e:
            logger.error(f"Error in order processor: {e}")
            await asyncio.sleep(10)

async def run_web() -> None:
    web_app = create_app()
    config = uvicorn.Config(
        web_app,
        host=settings.WEBHOOK_HOST,
        port=settings.WEBHOOK_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    try:
        await asyncio.gather(
            run_bot(),
            run_web(),
            return_exceptions=False
        )
    except Exception as e:
        logging.error("Fatal error in main event loop: %s", e)
        raise
    finally:
        logging.info("Закрываем ресурсы бота...")
        await bot.session.close()
        logging.info("Ресурсы закрыты успешно.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен.")