"""HTTP /api/v1/matching — только кадровик и администратор (X-User-Login, как остальной legacy API).
Рабочий контур дополнительно требует серверный ключ поиска, как /api/v1/search."""
import uuid
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from app.api.auth import StaffUser
from app.db.session import get_session
from app.matching.schemas import (
    CandidatesForVacancyIn,
    CandidatesForVacancyOut,
    SuggestionOut,
    VacanciesForCandidateIn,
    VacanciesForCandidateOut,
)
from app.matching.service import candidates_for_vacancy, vacancies_for_candidate
from app.matching.suggestions import create_suggestion, get_suggestion, suggestion_out
from app.search.api import require_search_access, run_search, work_bearer
from app.search.schemas import SearchErrorResponse

router = APIRouter(prefix="/api/v1/matching", tags=["matching"])


class ResumeUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=12_000_000)
    contour: Literal["training", "working"]


class LiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: uuid.UUID
    contour: Literal["training", "working"]
    limit: int = Field(default=20, ge=1, le=50)


class FactsCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_facts_id: str = Field(min_length=64, max_length=64)
    corrected: dict
    reason: str = Field(min_length=1, max_length=1000)
    contour: Literal["training", "working"]


class TextCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_text_id: uuid.UUID
    text: str = Field(min_length=50, max_length=150000)
    reason: str = Field(min_length=1, max_length=1000)
    contour: Literal["training", "working"]


@router.post("/resumes/{candidate_id}/text")
def correct_resume_text(candidate_id: uuid.UUID, body: TextCorrection, user: StaffUser,
                        session: Annotated[Session, Depends(get_session)],
                        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    from sqlalchemy import select
    from app.db.models import Candidate
    from app.db import repository as repo
    from app.db.enums import AuditAction, FileFormat
    from app.ingest.redact import redact, RedactionError
    from app.api.errors import ApiError
    require_search_access(body.contour, credentials)
    candidate = session.scalar(select(Candidate).where(Candidate.id == candidate_id).with_for_update())
    if candidate is None or candidate.is_synthetic != (body.contour == "training"):
        raise ApiError(404, "CANDIDATE_NOT_FOUND", "Запись недоступна")
    previous = repo.get_current_text(session, candidate.id)
    if previous is None or previous.id != body.expected_text_id:
        raise ApiError(409, "TEXT_STALE", "Исходная версия текста уже изменена")
    try:
        cleaned = redact(body.text, FileFormat.TXT)
    except RedactionError:
        raise ApiError(422, "TEXT_NEEDS_REVIEW", "Текст требует проверки очистки") from None
    row = repo.add_candidate_text(session, candidate.id, text=cleaned.text, redaction_method="hr-correction-v1")
    repo.write_audit(session, action=AuditAction.OTHER, entity_type="resume_text_correction", entity_id=str(row.id),
                     details={"actor_id":str(user.id), "previous_text_id":str(previous.id), "reason":body.reason})
    session.commit()
    return {"candidate_id":str(candidate.id), "text_id":str(row.id), "version":row.version}


@router.post("/resumes/{candidate_id}/facts/correct")
def correct_resume_facts(candidate_id: uuid.UUID, body: FactsCorrection, user: StaffUser,
                         session: Annotated[Session, Depends(get_session)],
                         credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    from app.matching.corrections import correct_facts
    from app.db.models import Candidate
    from app.api.errors import ApiError
    require_search_access(body.contour, credentials)
    row = session.get(Candidate, candidate_id)
    if row is None or row.is_synthetic != (body.contour == "training"):
        raise ApiError(404, "CANDIDATE_NOT_FOUND", "Запись недоступна")
    result = correct_facts(session, candidate_id, body.expected_facts_id, body.corrected, body.reason, user)
    session.commit()
    return result


@router.get("/resumes/{candidate_id}/facts/{facts_id}")
def read_facts(candidate_id: uuid.UUID, facts_id: str, user: StaffUser,
               session: Annotated[Session, Depends(get_session)],
               credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    from app.assessment.artifacts import ProcessingArtifact
    from app.db.models import Candidate
    from app.api.errors import ApiError
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise ApiError(404, "CANDIDATE_NOT_FOUND", "Запись не найдена")
    contour = "training" if candidate.is_synthetic else "working"
    require_search_access(contour, credentials)
    row = session.get(ProcessingArtifact, facts_id)
    if row is None or row.scope != f"{contour}:candidate:{candidate_id}" or row.kind not in ("resume_facts", "fact_correction"):
        raise ApiError(404, "FACTS_NOT_FOUND", "Сведения не найдены")
    return row.payload


@router.post("/resumes", status_code=201)
def upload_resume(body: ResumeUpload, user: StaffUser,
                  session: Annotated[Session, Depends(get_session)],
                  credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    from app.matching.intake import intake
    require_search_access(body.contour, credentials)
    result = intake(session, body, user)
    session.commit()
    return result


@router.post("/vacancies/current/process")
def process_current(body: LiveRequest, user: StaffUser,
                    session: Annotated[Session, Depends(get_session)],
                    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    from app.ai import build_client
    from app.matching.catalog_adapter import current_catalog
    from app.matching.processing import execute_processing
    require_search_access(body.contour, credentials)
    snapshots, source_mode = current_catalog(session, body.contour)
    if not snapshots:
        from app.db.models import Candidate
        candidate = session.get(Candidate, body.candidate_id)
        if candidate is None or candidate.is_synthetic != (body.contour == "training"):
            from app.api.errors import ApiError
            raise ApiError(404, "CANDIDATE_NOT_FOUND", "Запись недоступна")
        from app.matching.processing import save_run
        empty = {"result": {"items": [], "needs_evaluation": [], "excluded": []},
                 "facts_id": None, "processed_profiles": [], "reused_profiles": [],
                 "confirmation_review_required": [], "coverage": "complete", "catalog_count": 0,
                 "evaluation_complete": True}
        result = save_run(session, body.candidate_id, body.contour, empty, [], source_mode)
        session.commit()
        return result
    # Existing input limit is for supplied snapshots. Process catalog in bounded chunks.
    combined = None
    for offset in range(0, len(snapshots), 50):
        request = VacanciesForCandidateIn(candidate_id=body.candidate_id, contour=body.contour,
                                         vacancies=snapshots[offset:offset+50], limit=50)
        part = execute_processing(session, request, build_client())
        if combined is None:
            combined = part
        else:
            for key in ("items", "needs_evaluation", "excluded"):
                combined["result"][key].extend(part["result"][key])
            for key in ("processed_profiles", "reused_profiles", "confirmation_review_required"):
                combined[key].extend(part[key])
    combined.update(source_mode=source_mode, catalog_count=len(snapshots), coverage="complete")
    combined["evaluation_complete"] = not (combined["result"]["needs_evaluation"] or combined["confirmation_review_required"])
    combined["result"]["items"].sort(key=lambda x: ({"met":0,"unknown":1,"not_met":2}[x["formal_result"]], str(x["vacancy_ref"]["id"])))
    combined["result"]["items"] = combined["result"]["items"][:body.limit]
    from app.matching.processing import save_run
    combined = save_run(session, body.candidate_id, body.contour, combined, snapshots, source_mode)
    session.commit()
    return combined


@router.post("/vacancies/process")
def process_vacancies_route(body: VacanciesForCandidateIn, response: Response, user: StaffUser,
                           session: Annotated[Session, Depends(get_session)],
                           credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    """Explicit processing of missing assessments. May call the configured LLM."""
    from app.ai import build_client
    from app.matching.processing import execute_processing

    require_search_access(body.contour, credentials)
    result = execute_processing(session, body, build_client())
    from app.matching.processing import save_run
    result = save_run(session, body.candidate_id, body.contour, result, body.vacancies, "provided")
    session.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/runs/{run_id}")
def read_processing_run(run_id: str, user: StaffUser,
                        session: Annotated[Session, Depends(get_session)],
                        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    from app.assessment.artifacts import ProcessingArtifact
    from app.api.errors import ApiError
    from app.db import repository as repo
    row = session.get(ProcessingArtifact, run_id)
    if row is None or row.kind != "matching_run":
        raise ApiError(404, "RUN_NOT_FOUND", "Результат не найден")
    require_search_access(row.payload["contour"], credentials)
    current = repo.get_current_text(session, uuid.UUID(row.payload["candidate_id"]))
    return {**row.payload, "is_snapshot": True,
            "source_is_current": current is not None and str(current.id) == row.payload["text_id"]}


@router.post("/candidates", response_model=CandidatesForVacancyOut,
             responses={code: {"model": SearchErrorResponse} for code in (401, 403, 409, 422, 503)})
def candidates_route(body: CandidatesForVacancyIn, response: Response, user: StaffUser,
                     session: Annotated[Session, Depends(get_session)],
                     credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    """Люди под выбранную вакансию (3A): поиск по search_query + статус оценки по точному профилю."""
    require_search_access(body.vacancy.contour, credentials)
    result = candidates_for_vacancy(session, body, run_search)
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/vacancies", response_model=VacanciesForCandidateOut,
             responses={code: {"model": SearchErrorResponse} for code in (401, 403, 404, 409, 422)})
def vacancies_route(body: VacanciesForCandidateIn, response: Response, user: StaffUser,
                    session: Annotated[Session, Depends(get_session)],
                    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    """Вакансии по присланному резюме (3B): сохранённые кросс-оценки по точному профилю каждой вакансии."""
    require_search_access(body.contour, credentials)
    result = vacancies_for_candidate(session, body)
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/suggestions", response_model=SuggestionOut, status_code=201,
             responses={code: {"model": SearchErrorResponse} for code in (401, 403, 409, 422, 503)})
def create_suggestion_route(body: CandidatesForVacancyIn, response: Response, user: StaffUser,
                            session: Annotated[Session, Depends(get_session)],
                            credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    """Подборка после публикации (3C): тот же поиск, что /matching/candidates, плюс сохранённый снимок.
    Каждый вызов — новый датированный расчёт; откликов и записей резерва не создаёт."""
    require_search_access(body.vacancy.contour, credentials)
    result = create_suggestion(session, body, user, partial(run_search, read_only=False))
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/suggestions/{suggestion_id}", response_model=SuggestionOut,
            responses={code: {"model": SearchErrorResponse} for code in (401, 403, 404)})
def read_suggestion_route(suggestion_id: uuid.UUID, response: Response, user: StaffUser,
                          session: Annotated[Session, Depends(get_session)],
                          credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    """Перечитать подборку. Право и контур проверяются заново; фрагмент — только из доступного источника."""
    row = get_suggestion(session, suggestion_id)
    require_search_access(row.contour, credentials)
    response.headers["Cache-Control"] = "private, no-store"
    return suggestion_out(session, row)
