import asyncio
import logging

import uvicorn
from aiogram import Dispatcher

from app.bot.bot_instance import bot
from app.bot.handlers import router
from app.web.app import create_app
from config import settings

from app.db.middleware import DBSessionMiddleware   # ← добавь импорт
from app.bot.handlers_worker import router as worker_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def run_bot() -> None:
    dp = Dispatcher()

    # === Middleware ===
    session_middleware = DBSessionMiddleware()
    dp.message.middleware(session_middleware)
    dp.callback_query.middleware(session_middleware)  # на всякий случай

    dp.include_router(router)
    dp.include_router(worker_router)
    logging.info("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


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
    await asyncio.gather(run_bot(), run_web())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен.")
