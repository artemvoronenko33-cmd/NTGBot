from fastapi import FastAPI
from app.web.webhook import router as webhook_router


def create_app() -> FastAPI:
    app = FastAPI(title="Bot Webhook", docs_url=None, redoc_url=None)
    app.include_router(webhook_router)
    return app
