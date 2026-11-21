"""Who is calling. AUTH_MODE=fixture: `Bearer fixture:<login>` from fixtures/wave-1/actors.json.
AUTH_MODE=workforce: the same Bearer is checked by Workforce GET /api/v1/session; if Workforce
is unreachable the request fails with 503 and never gets a privilege by default."""
import json
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

from hiring.errors import Problem

HR_ROLES = ("hr", "admin")


@dataclass(frozen=True)
class Grant:
    role: str
    scope_type: str
    scope_id: uuid.UUID


@dataclass(frozen=True)
class Actor:
    actor_id: uuid.UUID
    login: str
    organization_id: uuid.UUID
    grants: tuple[Grant, ...]

    def is_hr(self) -> bool:
        """hr/admin over the actor's own organization."""
        return any(
            g.role in HR_ROLES and g.scope_type == "organization" and g.scope_id == self.organization_id
            for g in self.grants
        )

    def is_candidate(self) -> bool:
        return any(g.role == "candidate" and g.scope_type == "self" and g.scope_id == self.actor_id
                   for g in self.grants)

    @property
    def role(self) -> str:
        """Role written to history: the strongest grant used by Hiring."""
        for name in ("admin", "hr", "candidate"):
            if any(g.role == name for g in self.grants):
                return name
        return self.grants[0].role if self.grants else "none"


def actor_from_json(data: dict) -> Actor:
    return Actor(
        actor_id=uuid.UUID(str(data["actor_id"])),
        login=data["login"],
        organization_id=uuid.UUID(str(data["organization_id"])),
        grants=tuple(Grant(g["role"], g["scope_type"], uuid.UUID(str(g["scope_id"]))) for g in data["grants"]),
    )


@lru_cache(maxsize=8)
def _actors_file(path: Path) -> dict[str, Actor]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["login"]: actor_from_json(item) for item in data["actors"] if item.get("active", True)}


def fixture_actors(settings) -> dict[str, Actor]:
    """Общие учебные акторы fixtures/wave-1/actors.json плюс учебные акторы сервиса
    (второй кандидат для проверки объектных прав candidate-portal). Логины не пересекаются."""
    actors = dict(_actors_file(settings.fixture_dir / "actors.json"))
    extra = settings.extra_actors_file
    if extra is not None and extra.exists():
        for login, actor in _actors_file(extra).items():
            if login in actors:
                raise ValueError(f"extra actor login {login} duplicates a shared fixture actor")
            actors[login] = actor
    return actors


def bearer(header: str | None) -> str:
    scheme, _, token = (header or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Problem(401, "AUTH_REQUIRED", "Bearer token required")
    return token.strip()


def authenticate(settings, header: str | None) -> Actor:
    token = bearer(header)
    if settings.auth_mode == "fixture":
        if not token.startswith("fixture:"):
            raise Problem(401, "INVALID_SESSION", "Fixture mode accepts only fixture:<login>")
        actor = fixture_actors(settings).get(token.removeprefix("fixture:"))
        if actor is None:
            raise Problem(401, "INVALID_SESSION", "Unknown fixture actor")
        return actor
    try:
        response = httpx.get(
            f"{settings.workforce_url.rstrip('/')}/api/v1/session",
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.auth_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise Problem(503, "DEPENDENCY_UNAVAILABLE", "Workforce session service is unavailable") from exc
    if response.status_code == 401:
        raise Problem(401, "INVALID_SESSION", "Session expired or revoked")
    if response.status_code != 200:
        raise Problem(503, "DEPENDENCY_UNAVAILABLE", "Workforce session service returned an error")
    body = response.json()
    return actor_from_json(body.get("actor", body))


def known_candidate(settings, actor_id: uuid.UUID, organization_id: uuid.UUID) -> bool | None:
    """True/False when the server can check the candidate account; None when it cannot (workforce mode)."""
    if settings.auth_mode != "fixture":
        return None
    for actor in fixture_actors(settings).values():
        if actor.actor_id == actor_id:
            return actor.is_candidate() and actor.organization_id == organization_id
    return False
