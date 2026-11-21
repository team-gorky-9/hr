"""annual report releases: registry of annual snapshots built from legacy-hr facts

Контракт wave-4-reporting-stage-1, раздел 4B; задача wave-4b-ilya-annual-source.
Новая таблица, существующие не меняются. Снимок и Excel хранятся каталогом годового модуля
(HR_REPORTS_DIR), здесь — контур, заявленная полнота, основание, итог подготовки пакета и автор.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "annual_report_releases",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("contour", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("observed_until", sa.Date(), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confirmation_basis", sa.Text(), nullable=False),
        sa.Column("preparation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.CheckConstraint("contour IN ('training', 'working')", name="ck_annual_report_releases_contour"),
        sa.CheckConstraint("mode IN ('demo', 'work')", name="ck_annual_report_releases_mode"),
        sa.CheckConstraint("snapshot_id ~ '^[0-9a-f]{64}$'", name="ck_annual_report_releases_id"),
    )


def downgrade() -> None:
    op.drop_table("annual_report_releases")
