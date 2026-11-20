"""Поддержка обязательного Idempotency-Key для POST/PATCH-команд."""
from dataclasses import dataclass
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Actor
from .db.models import IdempotencyRecord
from .errors import ServiceError


@dataclass(frozen=True)
class IdempotencyScope:
    actor_id: uuid.UUID
    organization_id: uuid.UUID
    method: str
    path: str
    idempotency_key: uuid.UUID
    request_hash: str


def parse_idempotency_key(raw_key: str | None) -> uuid.UUID:
    """Проверить наличие и формат UUID заголовка Idempotency-Key."""
    if not raw_key or not raw_key.strip():
        raise ServiceError(
            422,
            "VALIDATION_ERROR",
            "Для изменяющих запросов обязателен заголовок Idempotency-Key (UUID).",
            field="Idempotency-Key",
        )
    try:
        return uuid.UUID(raw_key.strip())
    except ValueError as exc:
        raise ServiceError(
            422,
            "VALIDATION_ERROR",
            "Заголовок Idempotency-Key должен быть корректным UUID.",
            field="Idempotency-Key",
        ) from exc


def hash_canonical_payload(payload: Any) -> str:
    """Вычислить детерминированный SHA-256 от нормализованных параметров команды."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_scope(
    *,
    actor: Actor,
    method: str,
    path: str,
    idempotency_key: uuid.UUID,
    canonical_payload: Any,
) -> IdempotencyScope:
    return IdempotencyScope(
        actor_id=actor.actor_id,
        organization_id=actor.organization_id,
        method=method.upper(),
        path=path,
        idempotency_key=idempotency_key,
        request_hash=hash_canonical_payload(canonical_payload),
    )


def find_replay(session: Session, scope: IdempotencyScope) -> tuple[int, dict[str, Any]] | None:
    """Найти сохранённый ответ по Idempotency-Key; при другом теле бросить 409 IDEMPOTENCY_CONFLICT."""
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == scope.actor_id,
            IdempotencyRecord.organization_id == scope.organization_id,
            IdempotencyRecord.method == scope.method,
            IdempotencyRecord.path == scope.path,
            IdempotencyRecord.idempotency_key == scope.idempotency_key,
        )
    )
    if record is None:
        return None
    if record.request_hash != scope.request_hash:
        raise ServiceError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "Этот Idempotency-Key уже использован для другого запроса.",
            field="Idempotency-Key",
        )
    return record.status_code, record.response_body


def save_record(
    session: Session,
    scope: IdempotencyScope,
    *,
    status_code: int,
    response_body: dict[str, Any],
) -> None:
    """Записать результат команды в той же транзакции, что и предметное изменение."""
    session.add(
        IdempotencyRecord(
            actor_id=scope.actor_id,
            organization_id=scope.organization_id,
            method=scope.method,
            path=scope.path,
            idempotency_key=scope.idempotency_key,
            request_hash=scope.request_hash,
            status_code=status_code,
            response_body=response_body,
        )
    )
