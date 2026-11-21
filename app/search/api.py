"""Единая HTTP-точка входа поиска в app.main."""
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas import Contour
from app.config import settings
from app.db.session import get_session
from app.search.encoder import get_local_encoder
from app.search.schemas import SearchErrorResponse, SearchRequest, SearchResponse
from app.search.service import search_candidates

router = APIRouter(prefix="/api/v1/search", tags=["search"])
work_bearer = HTTPBearer(scheme_name="SearchWorkBearer", auto_error=False,
                         description="Серверный ключ требуется только для рабочего контура")


def require_search_access(contour: Contour, credentials: HTTPAuthorizationCredentials | None) -> None:
    """Рабочий контур — только с серверным ключом поиска; учебный доступен без него.
    Общая проверка для /search и /matching (wave-3-matching-stage-1)."""
    if contour == Contour.WORKING:
        token = settings.hr_search_work_token
        expected = token.get_secret_value() if token is not None else ""
        if not (expected and credentials and secrets.compare_digest(
                credentials.credentials.encode(), expected.encode())):
            raise ApiError(401, "SEARCH_AUTH_REQUIRED", "Требуется доступ к рабочему поиску")


def run_search(session: Session, body: SearchRequest, *, read_only: bool = True) -> SearchResponse:
    """Поиск в снимке только для чтения; сбой базы — 503 SEARCH_UNAVAILABLE, а не пустая выдача.
    read_only=False — для операции, которая в той же транзакции сохраняет результат (подборка 3C)."""
    factory = get_local_encoder if settings.hr_search_semantic_enabled else None
    try:
        # API открывает свежую Session. При переданном тестовом Connection
        # внешняя транзакция уже контролирует снимок и точки сохранения.
        if read_only and isinstance(session.get_bind(), Engine) and not session.in_transaction():
            session.connection(execution_options={
                "isolation_level": "REPEATABLE READ", "postgresql_readonly": True,
            })
        return search_candidates(session, body, encoder_factory=factory,
                                 threshold=settings.hr_search_dense_threshold)
    except SQLAlchemyError:
        raise ApiError(503, "SEARCH_UNAVAILABLE", "Поиск временно недоступен") from None


@router.post("/candidates", response_model=SearchResponse, openapi_extra={"security": [{}]},
             responses={code: {"model": SearchErrorResponse} for code in (401, 422, 500, 503)})
def search_route(body: SearchRequest, response: Response,
                 session: Annotated[Session, Depends(get_session)],
                 credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(work_bearer)]):
    require_search_access(body.contour, credentials)
    result = run_search(session, body)
    response.headers["Cache-Control"] = "private, no-store"
    return result
