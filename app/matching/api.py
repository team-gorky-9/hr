"""HTTP /api/v1/matching — только кадровик и администратор (X-User-Login, как остальной legacy API).
Рабочий контур дополнительно требует серверный ключ поиска, как /api/v1/search."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.auth import StaffUser
from app.db.session import get_session
from app.matching.schemas import (
    CandidatesForVacancyIn,
    CandidatesForVacancyOut,
    VacanciesForCandidateIn,
    VacanciesForCandidateOut,
)
from app.matching.service import candidates_for_vacancy, vacancies_for_candidate
from app.search.api import require_search_access, run_search, work_bearer
from app.search.schemas import SearchErrorResponse

router = APIRouter(prefix="/api/v1/matching", tags=["matching"])


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
