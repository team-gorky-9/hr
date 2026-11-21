"""Immutable attempts and one review per attempt."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def resource():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "development_submissions",
        *resource(),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("development_plans.id"), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("activity_key", sa.String(100), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("criterion_keys", sa.JSON(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("artifact", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.UniqueConstraint("plan_id", "activity_key", "attempt_no"),
        sa.UniqueConstraint("plan_id", "sequence_no"),
    )
    op.create_index("ix_development_submissions_plan_id", "development_submissions", ["plan_id"])
    op.create_table(
        "development_reviews",
        *resource(),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("development_submissions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("reviewer_actor_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("development_reviews")
    op.drop_table("development_submissions")
