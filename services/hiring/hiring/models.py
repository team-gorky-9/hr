"""Hiring's own tables. The service never reads other services' tables (wave-1-common)."""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class Case(Timestamps, Base):
    """One hiring case per positive selection. Status = the subject (documents, start);
    workforce_status = the separate question «is the HR record confirmed by its owner»."""

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False, index=True)
    application_system: Mapped[str] = mapped_column(String(40), nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    # Snapshot of the PositiveSelection exactly as accepted, plus server-side provenance.
    selection: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    verified_by_actor_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    checklist_version: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID, index=True)
    identity_basis: Mapped[str | None] = mapped_column(Text)
    withdraw_reason: Mapped[str | None] = mapped_column(Text)

    # Confirmed start (status=started). start_version grows with every /correct-start.
    starts_on: Mapped[date | None] = mapped_column(Date)
    basis: Mapped[dict | None] = mapped_column(JSONB)
    confirmation_basis: Mapped[str | None] = mapped_column(Text)
    started_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    start_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Workforce side, stage 1: filled by HR through /record-assignment (manual-confirmed).
    transfer_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    workforce_status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_sent")
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    workforce_confirmation: Mapped[dict | None] = mapped_column(JSONB)
    workforce_assignment_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    workforce_resolution: Mapped[str | None] = mapped_column(String(20))
    workforce_review_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # «Один активный case на application_ref»: a withdrawn case frees the reference.
        Index(
            "uq_cases_active_application",
            "application_system",
            "application_id",
            unique=True,
            postgresql_where=text("status <> 'withdrawn'"),
        ),
        Index("ix_cases_org_created", "organization_id", "created_at", "id"),
    )


class ChecklistItem(Timestamps, Base):
    __tablename__ = "checklist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    # All submitted versions, oldest first. The last one is the version under review.
    document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (UniqueConstraint("case_id", "key", name="uq_checklist_items_case_key"),)


class Document(Timestamps, Base):
    """Immutable uploaded original. A corrected file is a new document with a new id."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False, index=True)
    # Bound on first use (submit or start); a document never moves to another case.
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), index=True)
    # Документ собственного обращения кандидата (candidate-portal, wave-5); с делом не связан.
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_requests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    uploaded_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Relative to FILE_ROOT, built from ids only; original_name is never a path.
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)


class CaseEvent(Base):
    """Append-only history of decisions: every version of files and decisions stays here."""

    __tablename__ = "case_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    case_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    visible_to_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Full data for HR. candidate_data is the reduced explanation shown to the candidate.
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    candidate_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

    __table_args__ = (UniqueConstraint("case_id", "sequence", name="uq_case_events_sequence"),)


class IdempotentCommand(Base):
    """Result of a command sent with Idempotency-Key, scoped by actor, organization, method, path."""

    __tablename__ = "idempotent_commands"

    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class CandidateRequest(Timestamps, Base):
    """Собственное обращение кандидата (candidate-portal, wave-5-candidate-portal-stage-1).

    Автор — актор входа, а не поле тела запроса. Контакт — то, что сообщил сам кандидат
    (source=candidate_reported), внешне не проверен. Вакансия — ссылка на точную редакцию публикации;
    если она закрыта или не найдена, обращение принимается с вопросом цели (target_question),
    откликом оно автоматически не становится."""

    __tablename__ = "candidate_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False, index=True)
    author_actor_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False, index=True)
    number: Mapped[str | None] = mapped_column(String(32), unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    vacancy_ref: Mapped[dict | None] = mapped_column(JSONB)
    vacancy: Mapped[dict | None] = mapped_column(JSONB)  # title/status из источника на момент выбора
    target_question: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[dict] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    # 5B: последний запрос сведений HR (публичная часть видна кандидату), дополнения кандидата,
    # основание готовности (только HR) и ручная регистрация рассмотрения в подборе.
    information_request: Mapped[dict | None] = mapped_column(JSONB)
    addenda: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    review: Mapped[dict | None] = mapped_column(JSONB)
    consideration: Mapped[dict | None] = mapped_column(JSONB)
    # 5C: опубликованные HR исходы (continue может смениться итоговым) и отзыв обращения автором.
    outcomes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    withdrawal: Mapped[dict | None] = mapped_column(JSONB)


class CandidateRequestEvent(Base):
    """История обращения: только добавляется."""

    __tablename__ = "candidate_request_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_requests.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    request_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

    __table_args__ = (UniqueConstraint("request_id", "sequence", name="uq_candidate_request_events_sequence"),)


class CandidateRequestMessage(Base):
    """Сообщение в кабинете кандидата о запросе сведений или опубликованном исходе (5C).
    Доставка только внутри кабинета; email, СЭД и брокер не используются."""

    __tablename__ = "candidate_request_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_requests.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    next_action: Mapped[str | None] = mapped_column(Text)
    created_by_actor_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
