"""应用工厂入口：uvicorn app.main:create_app --factory。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router
from app.core.config import Settings
from app.api.incidents import DatabaseResource, router as incidents_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    database = DatabaseResource(settings)

    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            database.close()

    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.database = database
    application.include_router(router)
    application.include_router(incidents_router)
    return application
