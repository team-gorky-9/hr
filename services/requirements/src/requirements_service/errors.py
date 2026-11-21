"""Единый формат ошибок HTTP API согласно wave-1-common."""
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

SAFE_ERROR_PATH_FIELDS = frozenset({
    "code", "title", "position_code", "content", "expected_revision", "change_reason",
    "reviewer_actor_id", "result", "note", "override_reason", "approval_basis",
    "text", "transcription_basis", "kind", "file", "status", "contour",
    "limit", "cursor", "Idempotency-Key", "Authorization",
})


class ErrorDetail(BaseModel):
    """Тело блока error в ответах об ошибках."""

    code: str
    message: str
    field: str | None = None
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    """Корневая обёртка ошибки API."""

    error: ErrorDetail


class ServiceError(Exception):
    """Управляемая доменная или транспортная ошибка сервиса."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        field: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field = field
        self.headers = headers or {}


def get_request_id(request: Request) -> str:
    """Вернуть request_id текущего запроса (UUID-строка)."""
    rid = getattr(request.state, "request_id", None)
    if rid is None:
        rid = str(uuid.uuid4())
        request.state.request_id = rid
    return rid


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    field: str | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Сформировать JSONResponse с единой структурой error."""
    payload = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            field=field,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=headers or {},
    )


def _safe_validation_field(loc: tuple[Any, ...]) -> str | None:
    """Преобразовать путь ошибки Pydantic в безопасное имя поля без утечки значений."""
    parts = [p for p in loc if p not in ("body", "query", "path", "header")]
    if not parts:
        return None
    safe_parts = [
        str(p) if isinstance(p, int) or p in SAFE_ERROR_PATH_FIELDS else "*"
        for p in parts
    ]
    return ".".join(safe_parts)


def install_error_handlers(app: FastAPI) -> None:
    """Зарегистрировать глобальные обработчики исключений FastAPI."""

    @app.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            field=exc.field,
            request_id=get_request_id(request),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        field = _safe_validation_field(errors[0]["loc"]) if errors else None
        return error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Проверьте корректность входных данных.",
            field=field,
            request_id=get_request_id(request),
        )
