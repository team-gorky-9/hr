"""Local mobility storage: transactional resources and immutable audit snapshots."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, Integer, String, UniqueConstraint, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOBILITY_", extra="ignore")
    database_url: str = f"sqlite:///{ROOT / 'data' / 'mobility.db'}"
    actors_path: Path = ROOT / "fixtures" / "actors.json"


class Base(DeclarativeBase):
    pass


class Entry(Base):
    __tablename__ = "mobility_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class Audit(Base):
    __tablename__ = "mobility_history"
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


def require(condition):
    if not condition:
        fail("FORBIDDEN", "Недостаточно прав для действия.", 403)


def visible(condition):
    if not condition:
        fail("NOT_FOUND", "Запись не найдена.", 404)


def check_revision(resource, expected):
    if resource["revision"] != expected:
        fail("STALE_REVISION", "Загрузите актуальную редакцию.")


def in_state(resource, *states):
    if resource["status"] not in states:
        fail("INVALID_STATE", "Операция недоступна в текущем состоянии.")


def has_role(actor, role):
    return role in actor["roles"]


class Store:
    def __init__(self, settings):
        self.settings = settings
        args = {"check_same_thread": False, "timeout": 15} if settings.database_url.startswith("sqlite") else {}
        self.engine = create_engine(settings.database_url, connect_args=args)

    def context(self):
        # A local confirmed fixture is the input source, never a client-supplied claim.
        return json.loads(self.settings.actors_path.read_text(encoding="utf-8-sig"))

    def authenticate(self, authorization):
        login = authorization.removeprefix("Bearer fixture:") if authorization and authorization.startswith("Bearer fixture:") else None
        actor = next((a for a in self.context()["actors"] if a["login"] == login and a["active"]), None)
        if actor is None:
            fail("AUTH_REQUIRED", "Нужен учебный Bearer fixture:<login>.", 401)
        return actor

    def manager_assignment(self, organization_id, employee_id, manager_id, source):
        data = self.context()
        manager = next((a for a in data["actors"] if a["actor_id"] == manager_id
                        and a["organization_id"] == organization_id and a["active"]), None)
        if manager_id == employee_id or manager is None:
            return None
        return next((a for a in data["manager_assignments"]
                     if a["organization_id"] == organization_id and a["employee_actor_id"] == employee_id
                     and a["manager_actor_id"] == manager_id and a["source_reference"] == source
                     and a["active"]), None)

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
        rows = self.session.scalars(select(Entry).where(Entry.kind == kind,
            Entry.organization_id == self.actor["organization_id"]).order_by(Entry.id))
        return [deepcopy(row.payload) for row in rows]

    def get(self, kind, ident):
        row = self.session.get(Entry, str(ident))
        visible(row is not None and row.kind == kind and row.organization_id == self.actor["organization_id"])
        return deepcopy(row.payload)

    def history(self, ident):
        rows = self.session.scalars(select(Audit).where(Audit.resource_id == str(ident),
            Audit.organization_id == self.actor["organization_id"]).order_by(Audit.revision))
        return [{"revision": r.revision, "actor_id": r.actor_id, "action": r.action,
                 "recorded_at": r.recorded_at, "snapshot": deepcopy(r.snapshot)} for r in rows]

    def save(self, kind, data, action):
        data = deepcopy(data)
        ident = data.get("id") or str(uuid4())
        row = self.session.get(Entry, ident)
        stamp = now()
        if row is None:
            data.update(id=ident, organization_id=self.actor["organization_id"], revision=1,
                        created_at=stamp, created_by=self.actor["actor_id"], is_synthetic=True)
            row = Entry(id=ident, kind=kind, organization_id=self.actor["organization_id"], revision=1)
            self.session.add(row)
        else:
            data["revision"] = row.revision + 1
        data.update(updated_at=stamp, updated_by=self.actor["actor_id"])
        row.revision, row.payload = data["revision"], data
        self.session.add(Audit(id=str(uuid4()), resource_id=ident, organization_id=row.organization_id,
            revision=data["revision"], snapshot=deepcopy(data), actor_id=self.actor["actor_id"],
            action=action, recorded_at=stamp))
        self.session.flush()
        return deepcopy(data)


def read_interest(unit, ident):
    row = unit.get("interest", ident)
    opportunity = unit.get("opportunity", row["opportunity_id"])
    visible(unit.actor["actor_id"] in {row["employee_actor_id"], opportunity["owner_actor_id"]})
    return row, opportunity


def has_participation(unit, proposal_id):
    return next((p for p in unit.all("participation") if p["proposal_id"] == proposal_id), None)


def close_proposals(unit, interest_id, reason):
    proposals = [p for p in unit.all("proposal") if p["interest_id"] == interest_id]
    if any(has_participation(unit, p["id"]) for p in proposals):
        fail("PARTICIPATION_EXISTS", "Участие уже начато: используйте его завершение.")
    for proposal in proposals:
        if proposal["status"] != "withdrawn":
            proposal.update(status="withdrawn", reason=reason)
            unit.save("proposal", proposal, "interest_closed")
