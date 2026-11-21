"""Durable resource envelopes, audit snapshots and fixture authentication."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, Integer, String, UniqueConstraint, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STUDENTS_", extra="ignore")
    database_url: str = f"sqlite:///{ROOT / 'data' / 'students.db'}"
    actors_path: Path = ROOT / "fixtures" / "actors.json"
    mentor_capacity: int = Field(default=1, ge=1)


class Base(DeclarativeBase):
    pass


class Entry(Base):
    __tablename__ = "student_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class Audit(Base):
    __tablename__ = "student_history"
    __table_args__ = (UniqueConstraint("resource_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[str] = mapped_column(String(40))


class Problem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def fail(code, message, status=409):
    raise Problem(status, code, message)


def now():
    return datetime.now(timezone.utc).isoformat()


def roles(actor):
    return {g["role"] for g in actor["grants"]}


def organizer(actor):
    return any(g["role"] in {"hr", "admin"} and g["scope_type"] == "organization"
               and g["scope_id"] == actor["organization_id"] for g in actor["grants"])


def require(condition):
    if not condition:
        fail("FORBIDDEN", "Недостаточно прав для действия.", 403)


def check_revision(resource, expected):
    if resource["revision"] != expected:
        fail("STALE_REVISION", "Загрузите актуальную редакцию.")


class Store:
    def __init__(self, settings):
        self.settings = settings
        args = {"check_same_thread": False, "timeout": 15} if settings.database_url.startswith("sqlite") else {}
        self.engine = create_engine(settings.database_url, connect_args=args)
        self.actors = json.loads(settings.actors_path.read_text(encoding="utf-8-sig"))["actors"]

    def authenticate(self, authorization):
        login = authorization.removeprefix("Bearer fixture:") if authorization and authorization.startswith("Bearer fixture:") else None
        actor = next((a for a in self.actors if a["login"] == login and a.get("active", True)), None)
        if actor is None:
            fail("AUTH_REQUIRED", "Нужен учебный Bearer fixture:<login>.", 401)
        return actor

    def mentor(self, actor, mentor_id):
        mentor = next((a for a in self.actors if a["actor_id"] == str(mentor_id)
                       and a["organization_id"] == actor["organization_id"] and a.get("active", True)), None)
        if mentor is None or not (roles(mentor) & {"department", "employee"}):
            fail("INVALID_MENTOR", "Наставник недоступен в этой организации.", 422)
        return mentor

    @contextmanager
    def transaction(self, actor, write=False):
        with Session(self.engine) as session:
            if write:
                if self.engine.dialect.name == "sqlite":
                    session.execute(text("BEGIN IMMEDIATE"))
                else:
                    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:org))"),
                                    {"org": actor["organization_id"]})
            try:
                yield Unit(session, actor)
                session.commit()
            except Exception:
                session.rollback()
                raise


class Unit:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor

    def all(self, kind):
        rows = self.session.scalars(select(Entry).where(
            Entry.kind == kind, Entry.organization_id == self.actor["organization_id"]).order_by(Entry.id))
        return [deepcopy(row.payload) for row in rows]

    def get(self, kind, ident):
        row = self.session.get(Entry, str(ident))
        if row is None or row.kind != kind or row.organization_id != self.actor["organization_id"]:
            fail("NOT_FOUND", "Запись не найдена.", 404)
        return deepcopy(row.payload)

    def history(self, ident):
        rows = self.session.scalars(select(Audit).where(
            Audit.resource_id == str(ident), Audit.organization_id == self.actor["organization_id"])
            .order_by(Audit.revision))
        return [{"revision": r.revision, "actor_id": r.actor_id, "action": r.action,
                 "recorded_at": r.recorded_at, "snapshot": r.snapshot} for r in rows]

    def save(self, kind, data, action):
        data = deepcopy(data)
        ident = data.get("id") or str(uuid.uuid4())
        row = self.session.get(Entry, ident)
        stamp = now()
        if row is None:
            data.update(id=ident, organization_id=self.actor["organization_id"], revision=1,
                        created_at=stamp, created_by=self.actor["actor_id"])
            row = Entry(id=ident, kind=kind, organization_id=self.actor["organization_id"], revision=1)
            self.session.add(row)
        else:
            data["revision"] = row.revision + 1
        data.update(updated_at=stamp, updated_by=self.actor["actor_id"])
        row.revision, row.payload = data["revision"], data
        self.session.add(Audit(id=str(uuid.uuid4()), resource_id=ident, organization_id=row.organization_id,
                               revision=data["revision"], snapshot=deepcopy(data), actor_id=self.actor["actor_id"],
                               action=action, recorded_at=stamp))
        self.session.flush()
        return deepcopy(data)


def placement_visible(actor, placement):
    return organizer(actor) or actor["actor_id"] in {placement["student_actor_id"], placement["mentor_actor_id"]}


def read_placement(unit, ident):
    placement = unit.get("placement", ident)
    if not placement_visible(unit.actor, placement):
        fail("NOT_FOUND", "Участие не найдено.", 404)
    return placement


def active(placement):
    if placement["status"] != "active":
        fail("INVALID_STATE", "Участие уже завершено.")


def mentor_available(unit, mentor_id, starts_on, ends_on, limit, excluding=None):
    overlaps = [p for p in unit.all("placement") if p["id"] != excluding and p["status"] == "active"
                and p["mentor_actor_id"] == mentor_id
                and p["starts_on"] <= ends_on and p["ends_on"] >= starts_on]
    # Count maximum simultaneous load, not the total number of non-overlapping placements.
    events = [(starts_on, 1), (ends_on, -1)]
    for p in overlaps:
        events += [(max(starts_on, p["starts_on"]), 1), (min(ends_on, p["ends_on"]), -1)]
    load = 0
    for _day, delta in sorted(events, key=lambda event: (event[0], -event[1])):
        load += delta
        if load > limit:
            fail("MENTOR_CAPACITY_UNAVAILABLE", "Учебный лимит наставника на этот период исчерпан.")
