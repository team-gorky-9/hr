from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Resource:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class Organization(Resource, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(300))


class Actor(Resource, Base):
    __tablename__ = "actors"
    login: Mapped[str] = mapped_column(String(100), unique=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    grants: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str] = mapped_column(String(300))


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Department(Resource, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"))


class Employee(Resource, Base):
    __tablename__ = "employees"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(300))
    account_actor_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), unique=True)


class SourceRef(Base):
    __tablename__ = "source_refs"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    system: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(300), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)


class Assignment(Resource, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("employee_id", "basis_key"),
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="assignment_dates"),
    )
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    position_code: Mapped[str] = mapped_column(String(100))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    manager_employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    basis: Mapped[dict] = mapped_column(JSON)
    basis_key: Mapped[str] = mapped_column(String(64))
    recorded_by: Mapped[str] = mapped_column(ForeignKey("actors.id"))


class Delegation(Resource, Base):
    __tablename__ = "delegations"
    __table_args__ = (CheckConstraint("ends_on >= starts_on", name="delegation_dates"),)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    manager_employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))
    substitute_employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    basis: Mapped[dict] = mapped_column(JSON)


class Intake(Resource, Base):
    __tablename__ = "intakes"
    __table_args__ = (UniqueConstraint("organization_id", "source_case_id"),)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_case_id: Mapped[str] = mapped_column(String(36))
    source_case_revision: Mapped[int] = mapped_column(Integer)
    source_event_id: Mapped[str] = mapped_column(String(36))
    correlation_id: Mapped[str] = mapped_column(String(36))
    source_payload: Mapped[dict] = mapped_column(JSON)
    person_ref: Mapped[dict] = mapped_column(JSON)
    proposed_assignment: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="received")
    issue: Mapped[str | None] = mapped_column(String(300))
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    assignment_id: Mapped[str | None] = mapped_column(ForeignKey("assignments.id"))
    last_review: Mapped[dict | None] = mapped_column(JSON)


class Audit(Resource, Base):
    __tablename__ = "audit"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), index=True)
    resource_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
    action: Mapped[str] = mapped_column(String(100))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    basis: Mapped[dict | str] = mapped_column(JSON)
    effective_on: Mapped[date | None] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Command(Base):
    __tablename__ = "commands"
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON)


class Inbox(Base):
    __tablename__ = "inbox"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(30))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Outbox(Resource, Base):
    __tablename__ = "outbox"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    event_type: Mapped[str] = mapped_column(String(100))
    envelope: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
