"""Единый формат ошибок API (контракт api.md, п. 1): {"error": {"code", "message", "details"}}.

Любая ошибка — своя (ApiError), ошибка валидации FastAPI, «маршрут не найден» Starlette
или непредвиденное исключение — уходит клиенту в одном и том же виде, чтобы фронтенду
хватало одной функции разбора ошибок.
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Ошибка, которую обработчик маршрута сознательно возвращает клиенту."""

    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def not_found(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(404, code, message, {key: str(value) for key, value in details.items()})


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


# Коды для ответов Starlette, которые возникают до нашего кода (нет маршрута, не тот метод).
_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Поле input не возвращаем: в нём то, что прислал клиент, а ответ не должен ничего повторять.
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(
            error_body("VALIDATION_ERROR", "Некорректные параметры запроса", {"errors": errors}), status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Текст исключения клиенту не отдаём: в нём могут оказаться данные из базы.
        # Подробности — в журнале сервера.
        logger.exception("Необработанная ошибка API", exc_info=exc)
        return JSONResponse(error_body("INTERNAL_ERROR", "Внутренняя ошибка сервера"), status_code=500)
