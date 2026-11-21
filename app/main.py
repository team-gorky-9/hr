"""Точка входа HTTP-приложения: uv run uvicorn app.main:app

Документация маршрутов: /docs (Swagger UI) и /openapi.json.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.routes import router
from app.api.interaction import install_gateway, router as interaction_router
from app.api.archive import router as archive_router
from app.api.candidates import router as candidates_router
from app.api.public_vacancies import router as public_vacancies_router
from app.api.analytics_read import router as analytics_read_router
from app.config import settings
from app.management.api import router as management_router
from app.matching.api import router as matching_router
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
    install_gateway(app)
    app.include_router(interaction_router)
    app.include_router(router)
    app.include_router(archive_router)
    app.include_router(candidates_router)
    app.include_router(public_vacancies_router)
    app.include_router(analytics_read_router)
    app.include_router(search_router)
    app.include_router(matching_router)
    app.include_router(management_router)
    app.include_router(create_reporting_router())
    return app


app = create_app()
