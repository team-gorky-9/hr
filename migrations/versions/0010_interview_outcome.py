"""interview outcome: revision, attempt time and server time of the recorded result

Контракт wave-2-stage-1 (раздел «Илья»), задача wave-2-ilya-interview-outcome:
- interviews.revision — ревизия встречи; у существующих строк 1 (server_default), новая
  запись итога увеличивает её, а expected_revision защищает от устаревшей формы;
- interviews.attempt_at — когда была попытка разговора (для no_answer held_at остаётся пустым);
- interviews.outcome_recorded_at — когда сервер записал итог явным действием HR.
  Старые строки получают NULL: итог по ним явно не записывался, и ограничение ниже их не трогает.

История записи — строка audit_log (action = other, entity_type = interview): журнал уже
только дополняется, новая таблица не нужна.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTCOME_SHAPE = (
    "outcome_recorded_at IS NULL OR (result <> 'pending' AND attempt_at IS NOT NULL "
    "AND (result = 'no_answer') = (held_at IS NULL))"
)


def upgrade() -> None:
    op.add_column("interviews", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column("interviews", sa.Column("attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("interviews", sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_interviews_revision", "interviews", "revision >= 1")
    # Записанный итог согласован: попытка есть всегда, дата проведения — только у состоявшегося разговора.
    op.create_check_constraint("ck_interviews_outcome_shape", "interviews", OUTCOME_SHAPE)


def downgrade() -> None:
    op.drop_constraint("ck_interviews_outcome_shape", "interviews", type_="check")
    op.drop_constraint("ck_interviews_revision", "interviews", type_="check")
    op.drop_column("interviews", "outcome_recorded_at")
    op.drop_column("interviews", "attempt_at")
    op.drop_column("interviews", "revision")
