"""Archive-to-vacancy entry point reusing the existing application repository."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import StaffUser
from app.api.errors import ApiError
from app.api.schemas import Contour
from app.db import repository as repo
from app.db.enums import ApplicationSource, VacancyStatus
from app.db.models import Application, Candidate, ReserveEntry, StageEvent, Vacancy
from app.db.session import get_session
from app.search.api import require_search_access, work_bearer

router = APIRouter(prefix="/api/v1/archive", tags=["archive"])


class ReconsiderIn(BaseModel):
    candidate_id: uuid.UUID
    vacancy_id: uuid.UUID
    reserve_id: uuid.UUID
    contour: Contour
    confirmation: str = Field(min_length=1, max_length=2000)


class ReconsiderOut(BaseModel):
    application_id: uuid.UUID
    created: bool


@router.post("/reconsiderations", response_model=ReconsiderOut, status_code=201)
def reconsider(
    body: ReconsiderIn,
    response: Response,
    user: StaffUser,
    session: Annotated[Session, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)],
):
    require_search_access(body.contour, credentials)
    if not body.confirmation.strip():
        raise ApiError(422, "CONFIRMATION_REQUIRED", "Укажите, когда и как кандидат согласился на рассмотрение")
    candidate = session.scalar(select(Candidate).where(Candidate.id == body.candidate_id).with_for_update())
    if candidate is None or candidate.is_synthetic != (body.contour == Contour.TRAINING):
        raise ApiError(404, "CANDIDATE_NOT_FOUND", "Запись кандидата недоступна в выбранном контуре")
    # A candidate lock serializes repeated commands; the database also has a unique candidate/vacancy pair.
    existing = session.scalar(select(Application).where(
        Application.candidate_id == candidate.id, Application.vacancy_id == body.vacancy_id))
    if existing:
        response.status_code = 200
        return ReconsiderOut(application_id=existing.id, created=False)
    vacancy = session.scalar(select(Vacancy).where(Vacancy.id == body.vacancy_id).with_for_update())
    if vacancy is None or vacancy.status != VacancyStatus.OPEN:
        raise ApiError(409, "VACANCY_NOT_OPEN", "Вакансия недоступна для нового рассмотрения")
    entry = session.scalar(select(ReserveEntry).where(ReserveEntry.id == body.reserve_id).with_for_update())
    if (entry is None or entry.candidate_id != candidate.id or entry.position_id != vacancy.position_id
            or entry.status != "active" or (entry.valid_until and entry.valid_until < repo.moscow_today())
            or not (entry.contact_basis or "").strip()):
        raise ApiError(409, "CONTACT_BASIS_REQUIRED", "Нужна действующая подборка по целевой должности с основанием контакта")
    application = repo.create_application(
        session, candidate_id=candidate.id, vacancy_id=vacancy.id,
        source=ApplicationSource.RESPONSE, applied_at=repo.moscow_today(),
        actor_user_id=user.id, posting_title=vacancy.position.title,
    )
    event = session.scalar(select(StageEvent).where(StageEvent.application_id == application.id))
    event.comment = (
        f"Новое рассмотрение из архива. Подборка {entry.id}. "
        f"Основание контакта: {entry.contact_basis}. "
        f"Согласие на рассмотрение записал HR: {body.confirmation.strip()}"
    )
    session.commit()
    return ReconsiderOut(application_id=application.id, created=True)
