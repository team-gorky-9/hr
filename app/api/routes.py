"""Маршруты API (контракт api.md v0.3): раздел 2 — чтение, раздел 3 — рабочий цикл кадровика.

Обработчики синхронные (def, не async def): сессия SQLAlchemy синхронная (ADR-002 Р8),
FastAPI сам выполняет такие обработчики в пуле потоков. Сессия выдаётся на запрос
через Depends(get_session) и закрывается после ответа. Маршруты чтения в базу не пишут;
маршруты записи делают commit в своём сервисе (app/api/workflow.py).
"""
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import services, workflow
from app.api.auth import StaffUser
from app.api.schemas import (
    CrossAssessmentListOut,
    FunnelOut,
    RejectionReasonListOut,
    ReserveCreatedOut,
    ReserveEntryOut,
    ReserveIn,
    ReserveListOut,
    ReserveWithdrawIn,
    StageHistoryOut,
    StageMoveIn,
    StageMoveOut,
    StageRefListOut,
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
    sort: Literal['fit', 'date'] = 'date',
):
    filters = services.ApplicationFilters(
        applicability=applicability,
        stage_code=stage_code,
        formal_result=formal_result,
        formal_preliminary=formal_preliminary,
        assessment_status=assessment_status,
    )
    return services.list_applications(session, vacancy_id, contour, filters, sort=sort)


@router.get("/applications/{application_id}", response_model=ApplicationDetailOut)
def get_application(application_id: uuid.UUID, session: SessionDep):
    return services.get_application(session, application_id)


@router.get('/applications/{application_id}/comparison', response_model=ComparisonOut)
def get_comparison(application_id: uuid.UUID, profile_id: uuid.UUID, session: SessionDep):
    return services.get_comparison(session, application_id, profile_id)


@router.get("/candidate-texts/{candidate_text_id}", response_model=CandidateTextOut)
def get_candidate_text(candidate_text_id: uuid.UUID, session: SessionDep):
    return services.get_candidate_text(session, candidate_text_id)


# =============================================================================
# Этап 2: действия кадровика, резерв, кросс-оценки, воронка (api.md v0.3, раздел 3)
# Все маршруты требуют заголовок X-User-Login с ролью hr или admin (app/api/auth.py).
# =============================================================================

@router.get("/references/stages", response_model=StageRefListOut)
def list_stages(session: SessionDep, user: StaffUser):
    return workflow.list_stages(session)


@router.get("/references/rejection-reasons", response_model=RejectionReasonListOut)
def list_rejection_reasons(session: SessionDep, user: StaffUser):
    return workflow.list_rejection_reasons(session)


@router.post("/applications/{application_id}/stage", response_model=StageMoveOut, status_code=201)
def move_stage(application_id: uuid.UUID, body: StageMoveIn, session: SessionDep, user: StaffUser):
    return workflow.move_stage(session, application_id, body, user)


@router.get("/applications/{application_id}/history", response_model=StageHistoryOut)
def get_history(application_id: uuid.UUID, session: SessionDep, user: StaffUser):
    return workflow.get_history(session, application_id)


@router.get("/candidates/{candidate_id}/cross-assessments", response_model=CrossAssessmentListOut)
def get_cross_assessments(candidate_id: uuid.UUID, session: SessionDep, user: StaffUser):
    return workflow.cross_assessments(session, candidate_id)


@router.post("/reserve", response_model=ReserveCreatedOut, status_code=201)
def add_to_reserve(body: ReserveIn, session: SessionDep, user: StaffUser, response: Response):
    result = workflow.add_to_reserve(session, body, user)
    if not result.created:
        response.status_code = 200  # у кандидата уже есть действующая запись на эту цель
    return result


@router.post("/reserve/{reserve_id}/withdraw", response_model=ReserveEntryOut)
def withdraw_reserve(reserve_id: uuid.UUID, body: ReserveWithdrawIn, session: SessionDep, user: StaffUser):
    return workflow.withdraw_reserve(session, reserve_id, body, user)


@router.get("/positions/{position_id}/reserve", response_model=ReserveListOut)
def list_reserve(position_id: uuid.UUID, session: SessionDep, user: StaffUser,
                 contour: ContourQuery = Contour.WORKING):
    return workflow.list_reserve(session, position_id, contour)


@router.get("/analytics/funnel", response_model=FunnelOut)
def get_funnel(
    session: SessionDep,
    user: StaffUser,
    contour: ContourQuery = Contour.WORKING,
    vacancy_id: uuid.UUID | None = None,
    position_id: uuid.UUID | None = None,
    period_from: Annotated[date | None, Query(description="Начало периода закрытий, включительно (МСК)")] = None,
    period_to: Annotated[date | None, Query(description="Конец периода закрытий, включительно (МСК)")] = None,
):
    return workflow.funnel(session, contour, vacancy_id, position_id, period_from, period_to)
