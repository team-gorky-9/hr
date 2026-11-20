"""Точка входа HTTP-приложения: uv run uvicorn app.main:app

Документация маршрутов: /docs (Swagger UI) и /openapi.json.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.routes import router
from app.config import settings
from app.reporting.api import create_router as create_reporting_router
from app.search.api import router as search_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Кадры — API подбора",
        version="0.3.0",
        description="Вакансии, отклики, оценки и очищенные тексты; действия кадровика: этапы с историей, "
        "кросс-оценки, кадровый резерв, воронка (контракт api.md v0.3). Персональные данные кандидатов не отдаются. "
        "Маршруты действий требуют заголовок X-User-Login (учебная авторизация стенда).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(search_router)
    app.include_router(create_reporting_router())
    return app


app = create_app()
