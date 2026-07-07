from fastapi import FastAPI
from app.web.webhook import router as webhook_router
#from app.db.middleware import MaintenanceMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="Bot Webhook", docs_url=None, redoc_url=None)
    #app.add_middleware(MaintenanceMiddleware)
    app.include_router(webhook_router)
    return app
