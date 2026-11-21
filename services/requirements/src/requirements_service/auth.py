"""Аутентификация и разрешение акторов: AUTH_MODE=fixture и AUTH_MODE=workforce."""
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, Protocol
import uuid

import httpx

from .errors import ServiceError

RoleName = Literal["hr", "admin", "department", "employee", "candidate"]
ScopeType = Literal["organization", "department", "self"]

HR_ADMIN_ROLES = frozenset({"hr", "admin"})
REVIEWER_ROLES = frozenset({"department", "hr", "admin"})


@dataclass(frozen=True)
class Grant:
    """Полномочие актора на область организации, подразделения или себя."""

    role: RoleName
    scope_type: ScopeType
    scope_id: uuid.UUID


@dataclass(frozen=True)
class Actor:
    """Авторитетное представление текущего пользователя."""

    actor_id: uuid.UUID
    login: str
    organization_id: uuid.UUID
    grants: tuple[Grant, ...]
    active: bool = True

    @property
    def roles(self) -> set[str]:
        return {g.role for g in self.grants}

    def has_any_role(self, *allowed_roles: str) -> bool:
        return bool(self.roles & set(allowed_roles))


class ActorDirectory(Protocol):
    """Интерфейс проверки токена и получения активных акторов организации."""

    def authenticate_bearer(self, authorization_header: str | None) -> Actor:
        """Проверить Authorization header и вернуть активного актора."""
        ...

    def get_actor_in_organization(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        authorization_header: str | None = None,
    ) -> Actor | None:
        """Найти активного актора внутри указанной организации."""
        ...


def _parse_actor(raw: dict) -> Actor:
    grants = tuple(
        Grant(
            role=g["role"],
            scope_type=g["scope_type"],
            scope_id=uuid.UUID(str(g["scope_id"])),
        )
        for g in raw.get("grants", [])
    )
    return Actor(
        actor_id=uuid.UUID(str(raw["actor_id"])),
        login=str(raw["login"]),
        organization_id=uuid.UUID(str(raw["organization_id"])),
        grants=grants,
        active=bool(raw.get("active", True)),
    )


def _extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise ServiceError(401, "AUTH_REQUIRED", "Требуется заголовок Authorization.")
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise ServiceError(401, "INVALID_SESSION", "Неверный формат токена авторизации.")
    return parts[1].strip()


class FixtureActorDirectory:
    """Автономная директория акторов по fixtures/wave-1/actors.json."""

    def __init__(self, actors_path: Path) -> None:
        payload = json.loads(actors_path.read_text(encoding="utf-8"))
        self._by_login: dict[str, Actor] = {}
        self._by_id: dict[uuid.UUID, Actor] = {}
        for item in payload.get("actors", []):
            actor = _parse_actor(item)
            self._by_login[actor.login] = actor
            self._by_id[actor.actor_id] = actor

    def authenticate_bearer(self, authorization_header: str | None) -> Actor:
        token = _extract_bearer_token(authorization_header)
        if not token.startswith("fixture:"):
            raise ServiceError(
                401,
                "INVALID_SESSION",
                "В режиме fixture принимается только токен вида Bearer fixture:<login>.",
            )
        login = token.removeprefix("fixture:")
        actor = self._by_login.get(login)
        if actor is None or not actor.active:
            raise ServiceError(401, "INVALID_SESSION", "Сессия недействительна или актор неактивен.")
        return actor

    def get_actor_in_organization(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        authorization_header: str | None = None,
    ) -> Actor | None:
        actor = self._by_id.get(actor_id)
        if actor is None or not actor.active or actor.organization_id != organization_id:
            return None
        return actor


class WorkforceActorDirectory:
    """Интеграционная директория акторов через сервис workforce."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_sec: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_sec = timeout_sec
        self._external_client = client

    def _request(self, method: str, path: str, headers: dict[str, str]) -> httpx.Response:
        try:
            if self._external_client is not None:
                return self._external_client.request(method, f"{self._base_url}{path}", headers=headers)
            with httpx.Client(timeout=self._timeout_sec) as client:
                return client.request(method, f"{self._base_url}{path}", headers=headers)
        except httpx.HTTPError as exc:
            raise ServiceError(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "Сервис аутентификации workforce недоступен.",
            ) from exc

    def authenticate_bearer(self, authorization_header: str | None) -> Actor:
        token = _extract_bearer_token(authorization_header)
        response = self._request("GET", "/api/v1/session", headers={"Authorization": f"Bearer {token}"})
        if response.status_code == 401:
            raise ServiceError(401, "INVALID_SESSION", "Сессия workforce недействительна.")
        if response.status_code >= 500:
            raise ServiceError(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "Сервис аутентификации workforce вернул ошибку.",
            )
        if response.status_code != 200:
            raise ServiceError(401, "INVALID_SESSION", "Не удалось подтвердить сессию.")
        data = response.json()
        actor_raw = data.get("actor", data)
        actor = _parse_actor(actor_raw)
        if not actor.active:
            raise ServiceError(401, "INVALID_SESSION", "Актор деактивирован.")
        return actor

    def get_actor_in_organization(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        authorization_header: str | None = None,
    ) -> Actor | None:
        headers: dict[str, str] = {}
        if authorization_header:
            headers["Authorization"] = authorization_header
        response = self._request("GET", f"/api/v1/actors/{actor_id}", headers=headers)
        if response.status_code == 404:
            return None
        if response.status_code >= 500:
            raise ServiceError(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "Сервис акторов workforce недоступен.",
            )
        if response.status_code != 200:
            return None
        actor = _parse_actor(response.json())
        if not actor.active or actor.organization_id != organization_id:
            return None
        return actor


def require_hr_or_admin(actor: Actor) -> None:
    """Проверить, что актор имеет роль hr или admin."""
    if not actor.has_any_role(*HR_ADMIN_ROLES):
        raise ServiceError(403, "FORBIDDEN", "Операция доступна только ролям hr и admin.")


def require_position_reader(actor: Actor) -> None:
    """Проверить право чтения справочника должностей в своей организации."""
    if not actor.has_any_role("hr", "admin", "department"):
        raise ServiceError(403, "FORBIDDEN", "Недостаточно прав для чтения должностей.")


def require_draft_reader(actor: Actor) -> None:
    """Проверить право доступа к черновикам и источникам требований."""
    if not actor.has_any_role("hr", "admin", "department"):
        raise ServiceError(403, "FORBIDDEN", "Недостаточно прав для просмотра требований.")
