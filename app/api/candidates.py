"""Staff candidate index and bounded HTTP adapter for the established ingest pipeline."""
import hashlib
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.auth import StaffUser
from app.api.errors import ApiError
from app.api.schemas import Contour
from app.api.services import get_application
from app.db import repository as repo
from app.db.enums import AuditAction, DocumentKind, FileFormat, VacancyStatus
from app.db.models import Application, Candidate, SelectionStage, SourceDocument, StageEvent, Vacancy
from app.db.session import get_session
from app.ingest.extract import ExtractError, extract_text
from app.ingest.package import InputFile, Route
from app.ingest.pipeline import import_uploaded_resume
from app.ingest.report import ItemStatus, ReportItem
from app.search.api import require_search_access, work_bearer

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])
SessionDep = Annotated[Session, Depends(get_session)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]
MAX_UPLOAD = 10 * 1024 * 1024


class CandidateRow(BaseModel):
    application_id: UUID
    candidate_id: UUID
    candidate_code: str
    headline: str | None
    source: str
    channel: str
    vacancy_title: str
    stage_title: str
    stage_days: int | None
    formal_result: str | None
    assessment_status: str


class CandidatePage(BaseModel):
    items: list[CandidateRow]
    total: int
    offset: int
    limit: int


@router.get("", response_model=CandidatePage)
def candidates(user: StaffUser, session: SessionDep, credentials: Credentials,
               contour: Contour = Contour.TRAINING,
               q: Annotated[str, Query(max_length=200)] = "",
               offset: Annotated[int, Query(ge=0)] = 0,
               limit: Annotated[int, Query(ge=1, le=100)] = 50):
    require_search_access(contour, credentials)
    query = (select(Application, Candidate, SourceDocument, SelectionStage, Vacancy)
             .join(Candidate, Candidate.id == Application.candidate_id)
             .join(SourceDocument, SourceDocument.id == Candidate.source_document_id)
             .join(SelectionStage, SelectionStage.code == Application.current_stage_code)
             .outerjoin(Vacancy, Vacancy.id == Application.vacancy_id)
             .where(Candidate.is_synthetic == (contour == Contour.TRAINING)))
    if q.strip():
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(or_(Candidate.code.ilike(pattern, escape="\\"), Candidate.headline.ilike(pattern, escape="\\"),
                                Vacancy.title.ilike(pattern, escape="\\"), Application.external_position_title.ilike(pattern, escape="\\")))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(query.order_by(Candidate.created_at.desc(), Application.id).offset(offset).limit(limit)).all()
    ids = [a.id for a, *_ in rows]
    entered = dict(session.execute(select(StageEvent.application_id, func.max(StageEvent.created_at))
                    .where(StageEvent.application_id.in_(ids)).group_by(StageEvent.application_id)).all()) if ids else {}
    result = []
    for application, candidate, document, stage, vacancy in rows:
        detail = get_application(session, application.id)
        at = entered.get(application.id)
        days = max(0, (datetime.now(timezone.utc) - (at.replace(tzinfo=timezone.utc) if at and at.tzinfo is None else at)).days) if at else None
        result.append(CandidateRow(application_id=application.id, candidate_id=candidate.id,
            candidate_code=candidate.code, headline=detail.candidate.headline,
            source=application.source, channel=document.channel,
            vacancy_title=vacancy.title if vacancy else application.external_position_title or "Внешнее рассмотрение",
            stage_title=stage.title, stage_days=days,
            formal_result=detail.assessment.formal_result if detail.assessment else None,
            assessment_status=detail.assessment_status))
    return CandidatePage(items=result, total=total, offset=offset, limit=limit)


@router.post("/upload", response_model=ReportItem, status_code=201)
async def upload(request: Request, response: Response, user: StaffUser, session: SessionDep,
                 credentials: Credentials, vacancy_id: UUID,
                 filename: Annotated[str, Query(min_length=1, max_length=255)],
                 contour: Contour):
    require_search_access(contour, credentials)
    filename = PurePosixPath(filename.replace("\\", "/")).name
    extension = PurePosixPath(filename).suffix.lower()
    formats = {".txt": FileFormat.TXT, ".pdf": FileFormat.PDF, ".docx": FileFormat.DOCX}
    if extension not in formats:
        raise ApiError(422, "UNSUPPORTED_FORMAT", "Выберите TXT, PDF с текстовым слоем или DOCX")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_UPLOAD:
            raise ApiError(413, "FILE_TOO_LARGE", "Файл превышает 10 МБ")
        content.extend(chunk)
    if not content:
        raise ApiError(422, "EMPTY_FILE", "Файл пуст")
    vacancy = session.scalar(select(Vacancy).where(Vacancy.id == vacancy_id).with_for_update())
    if vacancy is None or vacancy.status != VacancyStatus.OPEN:
        raise ApiError(409, "VACANCY_NOT_OPEN", "Выберите открытую вакансию")
    try:
        text = extract_text(bytes(content), extension)
    except ExtractError as error:
        raise ApiError(422, error.code, str(error)) from error
    digest = hashlib.sha256(content).hexdigest()
    # Stable generated code; the same file is reused rather than creating a second person.
    code = "upload" + digest[:16].translate(str.maketrans("0123456789", "ghijklmnop")) + "-0001"
    # Serialize uploads of identical bytes even when two users select different vacancies.
    session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True))))
    route = Route(DocumentKind.RESUME, vacancy.channel, formats[extension],
                  vacancy.position.code, code, contour == Contour.TRAINING)
    result = import_uploaded_resume(session, InputFile(filename, bytes(content), text), route, vacancy)
    if result.status not in (ItemStatus.IMPORTED, ItemStatus.APPLICATION_ADDED, ItemStatus.DUPLICATE_SKIPPED):
        session.rollback()
        raise ApiError(409 if result.status == ItemStatus.CONFLICT else 422, "IMPORT_REJECTED",
                       result.reason or "Файл требует ручной проверки")
    if result.status == ItemStatus.DUPLICATE_SKIPPED:
        response.status_code = 200
    else:
        initial = session.scalar(select(StageEvent).where(StageEvent.application_id == result.application_id)
                                 .order_by(StageEvent.seq).limit(1))
        if initial and initial.actor_user_id is None:
            initial.actor_user_id = user.id
    repo.write_audit(session, action=AuditAction.OTHER, user_id=user.id, entity_type="resume_upload",
                     entity_id=str(result.application_id), details={"sha256": digest, "status": result.status})
    session.commit()
    return result
