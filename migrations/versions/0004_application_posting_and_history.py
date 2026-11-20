"""posting title of a response, no duplicate history applications

Контракт БД v1.6 (раздел 17), задача ingest-02:
- applications.posting_title — название публикации hh, на которую пришёл отклик
  (подвал резюме «Отклик на вакансию: «…»»). В папке консультанта архива «Кадры»
  лежат отклики на 7 разных публикаций, и это сведение иначе теряется;
- внешний отклик из «Истории общения с кандидатом» (source = history) не повторяется:
  один кандидат, одно название, одна дата. NULLS NOT DISTINCT (PostgreSQL 15+) —
  чтобы и запись без даты не сохранилась дважды.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('posting_title', sa.String(length=512), nullable=True))
    op.create_index(
        'uq_applications_history',
        'applications',
        ['candidate_id', 'external_position_title', 'applied_at'],
        unique=True,
        postgresql_where=sa.text("source = 'history'"),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index(
        'uq_applications_history',
        table_name='applications',
        postgresql_where=sa.text("source = 'history'"),
    )
    op.drop_column('applications', 'posting_title')
