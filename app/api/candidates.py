"""Кадровый реестр кандидатов, включая записи без откликов."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.auth import StaffUser
from app.api.routes import SessionDep
from app.api.schemas import Contour
from app.db import repository as repo
from app.db.enums import ApplicationSource, Channel, UserRole
from app.db.models import Application, Candidate, CandidateText, ReserveEntry, SelectionStage, SourceDocument, Vacancy

router = APIRouter(prefix="/api/v1")


class CandidateApplication(BaseModel):
    application_id: UUID
    vacancy_id: UUID | None
    vacancy_title: str
    source: ApplicationSource
    stage_title: str
    applied_at: date | None


class CandidateRow(BaseModel):
    candidate_id: UUID
    candidate_code: str
    full_name: str | None = None
    headline: str | None
    channel: Channel
    is_training: bool
    current_text_id: UUID | None
    in_archive: bool
    applications: list[CandidateApplication] = Field(default_factory=list)


class CandidateList(BaseModel):
    items: list[CandidateRow]


@router.get("/candidates", response_model=CandidateList)
def list_candidates(
    session: SessionDep,
    user: StaffUser,
    response: Response,
    contour: Contour = Contour.WORKING,
    vacancy_id: UUID | None = None,
) -> CandidateList:
    """Показать по одной строке на кандидата, без имени, контактов и сырого резюме."""
    in_archive = (
        select(ReserveEntry.id)
        .where(ReserveEntry.candidate_id == Candidate.id, repo.active_reserve_condition())
        .exists()
    )
    query = (
        select(Candidate, SourceDocument.channel, CandidateText.id, in_archive,
               Application, Vacancy.title, SelectionStage.title)
        .join(SourceDocument, SourceDocument.id == Candidate.source_document_id)
        .outerjoin(CandidateText, (CandidateText.candidate_id == Candidate.id) & CandidateText.is_current)
        .outerjoin(Application, Application.candidate_id == Candidate.id)
        .outerjoin(Vacancy, Vacancy.id == Application.vacancy_id)
        .outerjoin(SelectionStage, SelectionStage.code == Application.current_stage_code)
        .where(Candidate.is_synthetic.is_(contour == Contour.TRAINING))
        .order_by(Candidate.created_at.desc(), Candidate.code, Application.vacancy_id.is_(None),
                  Application.applied_at.desc().nulls_last(), Application.created_at.desc(), Application.id)
    )
    if vacancy_id is not None:
        matches_vacancy = (
            select(Application.id)
            .where(Application.vacancy_id == vacancy_id, Application.candidate_id == Candidate.id)
            .correlate(Candidate)
            .exists()
        )
        query = query.where(matches_vacancy)

    rows: dict[UUID, CandidateRow] = {}
    for candidate, channel, text_id, archived, application, vacancy_title, stage_title in session.execute(query):
        if candidate.id not in rows:
            rows[candidate.id] = CandidateRow(
                candidate_id=candidate.id,
                candidate_code=candidate.code,
                headline=candidate.headline,
                channel=channel,
                is_training=candidate.is_synthetic,
                current_text_id=text_id,
                in_archive=archived,
            )
        if application is not None:
            rows[candidate.id].applications.append(
                CandidateApplication(
                    application_id=application.id,
                    vacancy_id=application.vacancy_id,
                    vacancy_title=vacancy_title or application.external_position_title or "Без вакансии",
                    source=application.source,
                    stage_title=stage_title or "Этап не указан",
                    applied_at=application.applied_at,
                )
            )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "X-User-Login"
    items = list(rows.values())
    if user.role in (UserRole.HR, UserRole.ADMIN):
        for item in items:
            pii = repo.get_candidate_pii(
                session,
                item.candidate_id,
                user_id=user.id,
                purpose="единая база: имя кандидата",
            )
            item.full_name = pii.full_name if pii else None
        if items:
            session.commit()
    return CandidateList(items=items)
