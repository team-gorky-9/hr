"""matching suggestions: dated HR selection of archive records for a vacancy revision

Контракт wave-3-matching-stage-1, раздел 3C; задача wave-3c-ilya-vacancy-suggestions.
Новая таблица, существующие не меняются. Строка — один расчёт поиска; повторный расчёт по той же
или новой редакции вакансии — новая строка. items хранит ссылки на версии источников без текста
фрагмента: текст читается из действующего источника при каждом GET.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matching_suggestions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("vacancy_system", sa.String(length=16), nullable=False),
        sa.Column("vacancy_id", sa.UUID(), nullable=False),
        sa.Column("vacancy_revision", sa.Integer(), nullable=False),
        sa.Column("vacancy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("contour", sa.String(length=16), nullable=False),
        sa.Column("source_mode", sa.String(length=16), nullable=False),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_limit", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("semantic_status", sa.String(length=16), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("vacancy_system IN ('catalog', 'legacy-hr')", name="ck_matching_suggestions_system"),
        sa.CheckConstraint("contour IN ('training', 'working')", name="ck_matching_suggestions_contour"),
        sa.CheckConstraint("vacancy_revision >= 1", name="ck_matching_suggestions_revision"),
    )
    op.create_index("ix_matching_suggestions_vacancy", "matching_suggestions",
                    ["vacancy_system", "vacancy_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_matching_suggestions_vacancy", table_name="matching_suggestions")
    op.drop_table("matching_suggestions")
