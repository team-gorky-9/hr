"""ORM-модели сервиса подготовки и выпуска требований."""
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JSONType, UTCDateTime, UUIDType, utcnow


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_positions_org_code"),
        Index("ix_positions_org_created_id", "organization_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_org_created_id", "organization_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(256), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("ix_sources_org_position", "organization_id", "position_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("documents.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    position_code: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_origin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transcription_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    document: Mapped[Document] = relationship(lazy="joined")


class SourceTextRevision(Base):
    __tablename__ = "source_text_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "revision", name="uq_source_text_revisions_src_rev"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(32), nullable=False)
    text_origin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        Index("ix_drafts_org_created_id", "organization_id", "created_at", "id"),
        Index("ix_drafts_org_status_pos", "organization_id", "status", "position_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    position_code: Mapped[str] = mapped_column(String(64), nullable=False)
    contour: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_reviewer_actor_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    accepted_content_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted_source_revisions: Mapped[dict[str, int] | None] = mapped_column(JSONType, nullable=True)
    accepted_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_by_actor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class DraftEvent(Base):
    __tablename__ = "draft_events"
    __table_args__ = (
        Index("ix_draft_events_draft_created", "draft_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ApprovedProfile(Base):
    __tablename__ = "approved_profiles"
    __table_args__ = (
        UniqueConstraint("draft_id", name="uq_approved_profiles_draft"),
        UniqueConstraint(
            "organization_id",
            "position_code",
            "contour",
            "version",
            name="uq_approved_profiles_version",
        ),
        Index(
            "uq_approved_profiles_current",
            "organization_id",
            "position_code",
            "contour",
            unique=True,
            postgresql_where=text("is_current = true"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("drafts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    position_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    contour: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    sources_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    approval_basis: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_actor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_id",
            "organization_id",
            "method",
            "path",
            "idempotency_key",
            name="uq_idempotency_records_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_org_status_next", "organization_id", "status", "next_attempt_at"),
        Index("ix_outbox_events_status_next", "status", "next_attempt_at"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    aggregate_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(128), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts_since_reset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
