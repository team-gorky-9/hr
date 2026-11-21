"""Feedback review acknowledgements and explicit handoff access revocation."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("handoff_attempts", sa.Column("assignment_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("handoff_attempts", sa.Column("access_revoked_at", sa.DateTime(timezone=True)))
    op.add_column("handoff_attempts", sa.Column("access_revoked_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.add_column("handoff_attempts", sa.Column("access_revocation_reason", sa.Text()))
    op.add_column("handoff_attempts", sa.Column("revoke_request_id", pg.UUID(as_uuid=True)))
    op.add_column("handoff_attempts", sa.Column("revoke_request_payload", pg.JSONB()))
    op.create_unique_constraint("uq_handoff_attempts_revoke_request_id", "handoff_attempts", ["revoke_request_id"])
    op.create_table("feedback_reviews",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("application_id", pg.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("basis", sa.Text()),
        sa.Column("request_id", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("request_payload", pg.JSONB(), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("checked_seq", sa.Integer(), nullable=False),
        sa.Column("stage_event_id", pg.UUID(as_uuid=True), sa.ForeignKey("stage_events.id", ondelete="RESTRICT")),
    )
    op.create_index("ix_feedback_reviews_application_id", "feedback_reviews", ["application_id"])
    op.create_table("feedback_review_items",
        sa.Column("review_id", pg.UUID(as_uuid=True), sa.ForeignKey("feedback_reviews.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("feedback_id", pg.UUID(as_uuid=True), sa.ForeignKey("department_feedback.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("attempt_id", pg.UUID(as_uuid=True), sa.ForeignKey("handoff_attempts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("feedback_review_items")
    op.drop_table("feedback_reviews")
    op.drop_constraint("uq_handoff_attempts_revoke_request_id", "handoff_attempts", type_="unique")
    for name in ("revoke_request_payload", "revoke_request_id", "access_revocation_reason", "access_revoked_by_user_id", "access_revoked_at", "assignment_revision"):
        op.drop_column("handoff_attempts", name)
