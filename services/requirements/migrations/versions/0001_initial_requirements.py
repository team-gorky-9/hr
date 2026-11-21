"""Начальная схема БД сервиса требований.

Revision ID: 0001_initial_requirements
Revises:
Create Date: 2026-11-21 00:35:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_requirements"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUIDType = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "code", name="uq_positions_org_code"),
    )
    op.create_index("ix_positions_org_created_id", "positions", ["organization_id", "created_at", "id"])

    op.create_table(
        "documents",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=256), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_by", UUIDType, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_documents_org_created_id", "documents", ["organization_id", "created_at", "id"])

    op.create_table(
        "sources",
        sa.Column("id", UUIDType, sa.ForeignKey("documents.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("position_code", sa.String(length=64), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("text_origin", sa.String(length=32), nullable=True),
        sa.Column("transcription_basis", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sources_org_position", "sources", ["organization_id", "position_code"])

    op.create_table(
        "source_text_revisions",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("source_id", UUIDType, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("text_origin", sa.String(length=32), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", UUIDType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "revision", name="uq_source_text_revisions_src_rev"),
    )

    op.create_table(
        "drafts",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("position_code", sa.String(length=64), nullable=False),
        sa.Column("contour", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", JSONType, nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("assigned_reviewer_actor_id", UUIDType, nullable=True),
        sa.Column("accepted_content_revision", sa.Integer(), nullable=True),
        sa.Column("accepted_source_revisions", JSONType, nullable=True),
        sa.Column("accepted_by_actor_id", UUIDType, nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_actor_id", UUIDType, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_drafts_org_created_id", "drafts", ["organization_id", "created_at", "id"])
    op.create_index("ix_drafts_org_status_pos", "drafts", ["organization_id", "status", "position_code"])

    op.create_table(
        "draft_events",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("draft_id", UUIDType, sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("actor_id", UUIDType, nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("content_revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", JSONType, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_draft_events_draft_created", "draft_events", ["draft_id", "created_at", "id"])

    op.create_table(
        "approved_profiles",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("draft_id", UUIDType, sa.ForeignKey("drafts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("position_code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contour", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", JSONType, nullable=False),
        sa.Column("sources_snapshot", JSONType, nullable=False),
        sa.Column("approval_basis", sa.Text(), nullable=False),
        sa.Column("approved_by_actor_id", UUIDType, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("draft_id", name="uq_approved_profiles_draft"),
        sa.UniqueConstraint(
            "organization_id",
            "position_code",
            "contour",
            "version",
            name="uq_approved_profiles_version",
        ),
    )
    op.create_index(
        "uq_approved_profiles_current",
        "approved_profiles",
        ["organization_id", "position_code", "contour"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("actor_id", UUIDType, nullable=False),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=256), nullable=False),
        sa.Column("idempotency_key", UUIDType, nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", JSONType, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "actor_id",
            "organization_id",
            "method",
            "path",
            "idempotency_key",
            name="uq_idempotency_records_scope",
        ),
    )

    op.create_table(
        "outbox_events",
        sa.Column("event_id", UUIDType, primary_key=True),
        sa.Column("organization_id", UUIDType, nullable=False),
        sa.Column("aggregate_id", UUIDType, nullable=False),
        sa.Column("aggregate_revision", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=128), nullable=False),
        sa.Column("routing_key", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", UUIDType, nullable=False),
        sa.Column("envelope", JSONType, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts_since_reset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_outbox_events_org_status_next", "outbox_events", ["organization_id", "status", "next_attempt_at"])
    op.create_index("ix_outbox_events_status_next", "outbox_events", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_status_next", table_name="outbox_events")
    op.drop_index("ix_outbox_events_org_status_next", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_table("idempotency_records")
    op.drop_index("uq_approved_profiles_current", table_name="approved_profiles")
    op.drop_table("approved_profiles")
    op.drop_index("ix_draft_events_draft_created", table_name="draft_events")
    op.drop_table("draft_events")
    op.drop_index("ix_drafts_org_status_pos", table_name="drafts")
    op.drop_index("ix_drafts_org_created_id", table_name="drafts")
    op.drop_table("drafts")
    op.drop_table("source_text_revisions")
    op.drop_index("ix_sources_org_position", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_documents_org_created_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_positions_org_created_id", table_name="positions")
    op.drop_table("positions")
