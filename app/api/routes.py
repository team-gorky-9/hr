"""Маршруты Этапа 1: только чтение (контракт api.md v0.2, раздел 2).

Обработчики синхронные (def, не async def): сессия SQLAlchemy синхронная (ADR-002 Р8),
FastAPI сам выполняет такие обработчики в пуле потоков. Сессия выдаётся на запрос
через Depends(get_session) и закрывается после ответа. Маршруты ничего не пишут в базу.
"""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import services
from app.api.schemas import (
    ApplicationDetailOut,
    ComparisonOut,
    ApplicationListOut,
    AssessmentStatus,
    CandidateTextOut,
    Contour,
    HealthOut,
    VacancyListOut,
)
from app.db.enums import CheckResult
from app.db.session import get_session

router = APIRouter(prefix="/api/v1")

SessionDep = Annotated[Session, Depends(get_session)]
ContourQuery = Annotated[
    Contour, Query(description="working — рабочие данные (по умолчанию); training — учебный срез (py-9001)")
]


@router.get("/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
def health(session: SessionDep):
    """Приложение отвечает; база доступна, если на ней выполняется простой запрос."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "db": "error"}, status_code=503)
    return HealthOut(status="ok", db="ok")


@router.get("/vacancies", response_model=VacancyListOut)
def list_vacancies(session: SessionDep, contour: ContourQuery = Contour.WORKING):
    return services.list_vacancies(session, contour)


@router.get("/vacancies/{vacancy_id}/applications", response_model=ApplicationListOut)
def list_applications(
    vacancy_id: uuid.UUID,
    session: SessionDep,
    contour: ContourQuery = Contour.WORKING,
    stage_code: str | None = None,
    formal_result: CheckResult | None = None,
    formal_preliminary: bool | None = None,
    assessment_status: AssessmentStatus | None = None,
    applicability: Literal['confirmed', 'mismatch', 'unresolved', 'not_covered'] | None = None,
):
    filters = services.ApplicationFilters(
        applicability=applicability,
        stage_code=stage_code,
        formal_result=formal_result,
        formal_preliminary=formal_preliminary,
        assessment_status=assessment_status,
    )
    return services.list_applications(session, vacancy_id, contour, filters)


@router.get("/applications/{application_id}", response_model=ApplicationDetailOut)
def get_application(application_id: uuid.UUID, session: SessionDep):
    return services.get_application(session, application_id)


@router.get('/applications/{application_id}/comparison', response_model=ComparisonOut)
def get_comparison(application_id: uuid.UUID, profile_id: uuid.UUID, session: SessionDep):
    return services.get_comparison(session, application_id, profile_id)


@router.get("/candidate-texts/{candidate_text_id}", response_model=CandidateTextOut)
def get_candidate_text(candidate_text_id: uuid.UUID, session: SessionDep):
    return services.get_candidate_text(session, candidate_text_id)
