"""应用工厂入口：uvicorn app.main:create_app --factory。"""
from fastapi import FastAPI

from app.api.health import router
from app.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.include_router(router)
    return application
