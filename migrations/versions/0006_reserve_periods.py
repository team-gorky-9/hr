"""reserve periods: contact basis, end of period, one active entry per target

Контракт БД v1.8 (раздел 19), задача backend-02:
- reserve_entries.contact_basis — основание повторного контакта (reason остаётся
  обоснованием профессиональной пригодности);
- ended_at, end_reason, ended_by_user_id — как закончился период резерва;
- статус expired — срок истёк, период закрыт при новом включении на ту же цель;
- частичные уникальные индексы: одна активная запись на кандидата и цель
  (должность, иначе направление), в том числе при двух одновременных запросах.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "'active', 'withdrawn', 'hired'"
NEW_STATUSES = "'active', 'withdrawn', 'hired', 'expired'"


def upgrade() -> None:
    op.add_column('reserve_entries', sa.Column('contact_basis', sa.Text(), nullable=True))
    op.add_column('reserve_entries', sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('reserve_entries', sa.Column('end_reason', sa.Text(), nullable=True))
    op.add_column('reserve_entries', sa.Column('ended_by_user_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f('fk_reserve_entries_ended_by_user_id_users'), 'reserve_entries', 'users',
        ['ended_by_user_id'], ['id'], ondelete='SET NULL',
    )
    op.drop_constraint(op.f('ck_reserve_entries_status'), 'reserve_entries', type_='check')
    op.create_check_constraint(op.f('ck_reserve_entries_status'), 'reserve_entries', f"status IN ({NEW_STATUSES})")
    op.create_index(
        'uq_reserve_active_position', 'reserve_entries', ['candidate_id', 'position_id'], unique=True,
        postgresql_where=sa.text("status = 'active' AND position_id IS NOT NULL"),
    )
    op.create_index(
        'uq_reserve_active_area', 'reserve_entries', ['candidate_id', 'competency_area'], unique=True,
        postgresql_where=sa.text("status = 'active' AND position_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index('uq_reserve_active_area', table_name='reserve_entries',
                  postgresql_where=sa.text("status = 'active' AND position_id IS NULL"))
    op.drop_index('uq_reserve_active_position', table_name='reserve_entries',
                  postgresql_where=sa.text("status = 'active' AND position_id IS NOT NULL"))
    op.execute("UPDATE reserve_entries SET status = 'withdrawn' WHERE status = 'expired'")
    op.drop_constraint(op.f('ck_reserve_entries_status'), 'reserve_entries', type_='check')
    op.create_check_constraint(op.f('ck_reserve_entries_status'), 'reserve_entries', f"status IN ({OLD_STATUSES})")
    op.drop_constraint(op.f('fk_reserve_entries_ended_by_user_id_users'), 'reserve_entries', type_='foreignkey')
    op.drop_column('reserve_entries', 'ended_by_user_id')
    op.drop_column('reserve_entries', 'end_reason')
    op.drop_column('reserve_entries', 'ended_at')
    op.drop_column('reserve_entries', 'contact_basis')
