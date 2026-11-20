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

from app.ai.client import LLMClient
from app.api import auth, handoff, interview, services, workflow
from app.api.auth import AuthenticatedUser, OptionalUser, StaffUser
from app.api.errors import ApiError
from app.postings import service as postings
from app.postings.service import ApplicationResolution
from app.api.schemas import (
    AnswerIn,
    AnswerListOut,
    AnswerOut,
    AssessmentOut,
    ConfirmIn,
    InterviewGuideIn,
    InterviewGuideOut,
    InterviewKindIn,
    ApplicationDetailOut,
    ApplicationListOut,
    AssessmentStatus,
    CandidateTextOut,
    ComparisonOut,
    Contour,
    CrossAssessmentListOut,
    DeadlineStatus,
    FunnelOut,
    HandoffAttemptDetailOut,
    HandoffCreateIn,
    HandoffCreatedOut,
    HandoffDeadlineExtendedOut,
    HandoffDeadlineExtendIn,
    HandoffFeedbackCreatedOut,
    HandoffFeedbackIn,
    HandoffFeedbackListOut,
    HandoffListOut,
    HandoffSummaryOut,
    HealthOut,
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
    VacancyListOut,
    PostingSnapshotIn,
)
from app.db import repository as repo
from app.db.enums import CheckResult, HandoffStatus, InterviewKind, UserRole
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
def list_vacancies(session: SessionDep, contour: ContourQuery = Contour.WORKING, user: OptionalUser = None):
    auth.ensure_not_department(user)
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
    user: OptionalUser = None,
):
    auth.ensure_not_department(user)
    filters = services.ApplicationFilters(
        applicability=applicability,
        stage_code=stage_code,
        formal_result=formal_result,
        formal_preliminary=formal_preliminary,
        assessment_status=assessment_status,
    )
    return services.list_applications(session, vacancy_id, contour, filters, sort=sort)


@router.get("/applications/{application_id}", response_model=ApplicationDetailOut)
def get_application(application_id: uuid.UUID, session: SessionDep, user: OptionalUser = None):
    if user is not None and user.role == UserRole.DEPARTMENT:
        if not repo.has_department_application_access(session, user.id, application_id):
            raise ApiError(
                403,
                "FORBIDDEN_SCOPE",
                "Доступ к карточке отклика разрешён только назначенному получателю",
                {"application_id": str(application_id)},
            )
    return services.get_application(session, application_id)


@router.get('/applications/{application_id}/posting-resolution', response_model=ApplicationResolution)
def get_posting_resolution(
    application_id: uuid.UUID,
    session: SessionDep,
    user: OptionalUser = None,
):
    auth.ensure_not_department(user)
    try:
        return postings.resolve_application(session, application_id)
    except ValueError as error:
        if str(error) != 'application_not_found':
            raise
        raise ApiError(404, 'APPLICATION_NOT_FOUND', 'Отклик не найден') from error


@router.post('/posting-snapshots', status_code=201)
def create_posting_snapshot(body: PostingSnapshotIn, session: SessionDep, actor: StaffUser):
    try:
        result = postings.create_snapshot(session, body.application_ids, actor_id=actor.id)
    except ValueError as error:
        raise ApiError(422, 'INVALID_SNAPSHOT_SELECTION', 'Выборка должна содержать существующие прямые отклики') from error
    session.commit()
    return result


@router.get('/posting-snapshots/{snapshot_id}')
def get_posting_snapshot(snapshot_id: uuid.UUID, session: SessionDep, actor: StaffUser):
    try:
        return postings.read_snapshot(session, snapshot_id)
    except ValueError as error:
        if str(error) != 'snapshot_not_found':
            raise
        raise ApiError(404, 'SNAPSHOT_NOT_FOUND', 'Снимок не найден') from error


@router.get('/applications/{application_id}/comparison', response_model=ComparisonOut)
def get_comparison(
    application_id: uuid.UUID,
    profile_id: uuid.UUID,
    session: SessionDep,
    user: OptionalUser = None,
):
    auth.ensure_not_department(user)
    return services.get_comparison(session, application_id, profile_id)


@router.get("/candidate-texts/{candidate_text_id}", response_model=CandidateTextOut)
def get_candidate_text(candidate_text_id: uuid.UUID, session: SessionDep, user: OptionalUser = None):
    if user is not None and user.role == UserRole.DEPARTMENT:
        if not repo.has_department_text_access(session, user.id, candidate_text_id):
            raise ApiError(
                403,
                "FORBIDDEN_SCOPE",
                "Доступ к тексту кандидата разрешён только для переданного вам отклика",
                {"candidate_text_id": str(candidate_text_id)},
            )
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
def move_stage(
    application_id: uuid.UUID,
    body: StageMoveIn,
    session: SessionDep,
    user: StaffUser,
    response: Response,
):
    result, created = workflow.move_stage(session, application_id, body, user)
    if not created:
        response.status_code = 200
    return result


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
    department: str | None = None,
):
    return workflow.funnel(session, contour, vacancy_id, position_id, period_from, period_to, department=department)


# --- Гайд интервью, ответы, подтверждение требования (interview.md v0.4, interview-01) ---------

LLMDep = Annotated[LLMClient, Depends(interview.get_llm_client)]


@router.post("/applications/{application_id}/interview-guide", response_model=InterviewGuideOut, status_code=201)
def create_interview_guide(application_id: uuid.UUID, body: InterviewGuideIn, session: SessionDep, user: StaffUser,
                           llm: LLMDep, response: Response):
    guide, created = interview.create_guide(session, application_id, body, user, llm)
    if not created:
        response.status_code = 200  # возвращена уже существующая версия гайда
    return guide


@router.get("/applications/{application_id}/interview-guide", response_model=InterviewGuideOut)
def get_interview_guide(application_id: uuid.UUID, session: SessionDep, user: StaffUser,
                        kind: InterviewKindIn = InterviewKindIn.PHONE,
                        guide_version: Annotated[int | None, Query(ge=1)] = None):
    return interview.get_guide(session, application_id, InterviewKind(kind), guide_version)


@router.post("/interviews/{interview_id}/questions/{question_id}/answers", response_model=AnswerOut, status_code=201)
def add_interview_answer(interview_id: uuid.UUID, question_id: uuid.UUID, body: AnswerIn, session: SessionDep,
                         user: StaffUser, response: Response):
    answer, created = interview.add_answer(session, interview_id, question_id, body, user)
    if not created:
        response.status_code = 200  # повтор запроса с тем же request_id
    return answer


@router.get("/interviews/{interview_id}/questions/{question_id}/answers", response_model=AnswerListOut)
def list_interview_answers(interview_id: uuid.UUID, question_id: uuid.UUID, session: SessionDep, user: StaffUser):
    return interview.list_answers(session, interview_id, question_id)


@router.post("/assessments/{assessment_id}/formal-checks/{requirement_id}/confirm", response_model=AssessmentOut,
             status_code=201)
def confirm_formal_check(assessment_id: uuid.UUID, requirement_id: uuid.UUID, body: ConfirmIn, session: SessionDep,
                         user: StaffUser, response: Response):
    assessment, created = interview.confirm_requirement(session, assessment_id, requirement_id, body, user)
    if not created:
        response.status_code = 200  # повтор запроса с тем же request_id
    return assessment


# =============================================================================
# Этап 2б: передача руководителю, очередь ожиданий, ответ департамента (workflow-01)
# =============================================================================

@router.get("/applications/{application_id}/handoff-summary", response_model=HandoffSummaryOut)
def get_handoff_summary(application_id: uuid.UUID, session: SessionDep, user: AuthenticatedUser):
    return handoff.get_handoff_summary(session, application_id, user)


@router.post("/applications/{application_id}/handoffs", response_model=HandoffCreatedOut, status_code=201)
def create_handoff(
    application_id: uuid.UUID,
    body: HandoffCreateIn,
    session: SessionDep,
    user: StaffUser,
    response: Response,
):
    result = handoff.create_additional_handoff(session, application_id, body, user)
    if not result.created:
        response.status_code = 200
    return result


@router.get("/applications/{application_id}/handoffs", response_model=HandoffListOut)
def list_application_handoffs(application_id: uuid.UUID, session: SessionDep, user: AuthenticatedUser):
    return handoff.list_application_handoffs(session, application_id, user)


@router.get("/handoffs", response_model=HandoffListOut)
def list_handoffs(
    session: SessionDep,
    user: AuthenticatedUser,
    contour: ContourQuery = Contour.WORKING,
    status: HandoffStatus | None = None,
    deadline_status: DeadlineStatus | None = None,
    department: str | None = None,
    recipient_user_id: uuid.UUID | None = None,
    actor_login: str | None = None,
    vacancy_id: uuid.UUID | None = None,
    position_id: uuid.UUID | None = None,
):
    return handoff.list_handoffs(
        session,
        user,
        contour=contour,
        status=status,
        deadline_status=deadline_status,
        department=department,
        recipient_user_id=recipient_user_id,
        actor_login=actor_login,
        vacancy_id=vacancy_id,
        position_id=position_id,
    )


@router.get("/handoffs/{attempt_id}", response_model=HandoffAttemptDetailOut)
def get_handoff_detail(attempt_id: uuid.UUID, session: SessionDep, user: AuthenticatedUser):
    return handoff.get_handoff_detail(session, attempt_id, user)


@router.post(
    "/applications/{application_id}/handoffs/{attempt_id}/deadline",
    response_model=HandoffDeadlineExtendedOut,
    status_code=201,
)
def extend_handoff_deadline(
    application_id: uuid.UUID,
    attempt_id: uuid.UUID,
    body: HandoffDeadlineExtendIn,
    session: SessionDep,
    user: StaffUser,
    response: Response,
):
    result = handoff.extend_handoff_deadline(session, application_id, attempt_id, body, user)
    if not result.created:
        response.status_code = 200
    return result


@router.post("/applications/{application_id}/feedback", response_model=HandoffFeedbackCreatedOut, status_code=201)
def record_feedback(
    application_id: uuid.UUID,
    body: HandoffFeedbackIn,
    session: SessionDep,
    user: AuthenticatedUser,
    response: Response,
):
    result = handoff.record_feedback(session, application_id, body, user)
    if not result.created:
        response.status_code = 200
    return result


@router.get("/applications/{application_id}/feedback", response_model=HandoffFeedbackListOut)
def list_feedback(
    application_id: uuid.UUID,
    session: SessionDep,
    user: AuthenticatedUser,
    attempt_id: uuid.UUID | None = None,
):
    return handoff.list_feedback(session, application_id, user, attempt_id=attempt_id)
