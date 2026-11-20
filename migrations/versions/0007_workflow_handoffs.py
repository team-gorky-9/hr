"""workflow handoffs: attempts, frozen summary snapshots, versioned department feedback

Контракт БД (workflow-01):
- таблица handoff_attempts: попытка передачи конкретному адресату, канал, время факта,
  замороженный снимок сводки, статус ожидания, идемпотентность по request_id;
- расширение department_feedback: привязка к attempt_id, цепочка исправлений supersedes_id + revision
  с частичным уникальным индексом против гонок, факты contact_status/interview_status,
  происхождение внешнего ответа (response_channel, reported_by_*, reported_at) и request_id.

Примечание: при влитии interview-01 с миграцией 0007 раньше этой ветки перенумеровать в 0008 (Revises: 0007).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    op.create_table(
        'handoff_attempts',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('application_id', sa.UUID(), nullable=False),
        sa.Column('stage_event_id', sa.UUID(), nullable=True),
        sa.Column('recipient_user_id', sa.UUID(), nullable=True),
        sa.Column('recipient_name', sa.String(length=256), nullable=False),
        sa.Column('recipient_department', sa.String(length=512), nullable=False),
        sa.Column('channel', _enum('cabinet', 'phone', 'sed', 'email', 'in_person', 'other', name='channel'), nullable=False),
        sa.Column('handed_off_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('summary_revision', sa.String(length=64), nullable=False),
        sa.Column('summary_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'status',
            _enum('awaiting_response', 'responded', 'closed_without_response', name='status'),
            server_default='awaiting_response',
            nullable=False,
        ),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('close_reason', sa.String(length=128), nullable=True),
        sa.Column('closed_by_stage_event_id', sa.UUID(), nullable=True),
        sa.Column('request_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], name=op.f('fk_handoff_attempts_application_id_applications'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['closed_by_stage_event_id'], ['stage_events.id'], name=op.f('fk_handoff_attempts_closed_by_stage_event_id_stage_events'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_handoff_attempts_created_by_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], name=op.f('fk_handoff_attempts_recipient_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['stage_event_id'], ['stage_events.id'], name=op.f('fk_handoff_attempts_stage_event_id_stage_events'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_handoff_attempts')),
    )
    op.create_index(op.f('ix_handoff_attempts_application_id'), 'handoff_attempts', ['application_id'], unique=False)
    op.create_index(op.f('ix_handoff_attempts_recipient_user_id'), 'handoff_attempts', ['recipient_user_id'], unique=False)
    op.create_index(
        'ix_handoff_attempts_open_status',
        'handoff_attempts',
        ['status', 'recipient_department'],
        unique=False,
        postgresql_where=sa.text("status = 'awaiting_response'"),
    )
    op.create_index(
        'uq_handoff_attempts_request_id',
        'handoff_attempts',
        ['request_id'],
        unique=True,
        postgresql_where=sa.text('request_id IS NOT NULL'),
    )

    op.add_column('department_feedback', sa.Column('attempt_id', sa.UUID(), nullable=True))
    op.add_column('department_feedback', sa.Column('supersedes_id', sa.UUID(), nullable=True))
    op.add_column('department_feedback', sa.Column('revision', sa.SmallInteger(), server_default='1', nullable=False))
    op.add_column(
        'department_feedback',
        sa.Column(
            'contact_status',
            _enum('yes', 'no', 'not_reported', name='contact_status'),
            server_default='not_reported',
            nullable=False,
        ),
    )
    op.add_column(
        'department_feedback',
        sa.Column(
            'interview_status',
            _enum('yes', 'no', 'not_reported', name='interview_status'),
            server_default='not_reported',
            nullable=False,
        ),
    )
    op.add_column(
        'department_feedback',
        sa.Column(
            'response_channel',
            _enum('cabinet', 'phone', 'sed', 'email', 'in_person', 'other', name='response_channel'),
            nullable=True,
        ),
    )
    op.add_column('department_feedback', sa.Column('reported_by_user_id', sa.UUID(), nullable=True))
    op.add_column('department_feedback', sa.Column('reported_by_name', sa.String(length=256), nullable=True))
    op.add_column('department_feedback', sa.Column('reported_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('department_feedback', sa.Column('request_id', sa.UUID(), nullable=True))

    op.execute(
        "UPDATE department_feedback SET interview_status = CASE "
        "WHEN interview_held IS TRUE THEN 'yes' "
        "WHEN interview_held IS FALSE THEN 'no' "
        "ELSE 'not_reported' END"
    )

    op.create_foreign_key(
        op.f('fk_department_feedback_attempt_id_handoff_attempts'),
        'department_feedback',
        'handoff_attempts',
        ['attempt_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        op.f('fk_department_feedback_supersedes_id_department_feedback'),
        'department_feedback',
        'department_feedback',
        ['supersedes_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        op.f('fk_department_feedback_reported_by_user_id_users'),
        'department_feedback',
        'users',
        ['reported_by_user_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_check_constraint(op.f('ck_department_feedback_revision_positive'), 'department_feedback', 'revision >= 1')
    op.create_index(op.f('ix_department_feedback_attempt_id'), 'department_feedback', ['attempt_id'], unique=False)
    op.create_index(
        'uq_department_feedback_supersedes_id',
        'department_feedback',
        ['supersedes_id'],
        unique=True,
        postgresql_where=sa.text('supersedes_id IS NOT NULL'),
    )
    op.create_index(
        'uq_department_feedback_attempt_revision',
        'department_feedback',
        ['attempt_id', 'revision'],
        unique=True,
        postgresql_where=sa.text('attempt_id IS NOT NULL'),
    )
    op.create_index(
        'uq_department_feedback_request_id',
        'department_feedback',
        ['request_id'],
        unique=True,
        postgresql_where=sa.text('request_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_department_feedback_request_id', table_name='department_feedback', postgresql_where=sa.text('request_id IS NOT NULL'))
    op.drop_index('uq_department_feedback_attempt_revision', table_name='department_feedback', postgresql_where=sa.text('attempt_id IS NOT NULL'))
    op.drop_index('uq_department_feedback_supersedes_id', table_name='department_feedback', postgresql_where=sa.text('supersedes_id IS NOT NULL'))
    op.drop_index(op.f('ix_department_feedback_attempt_id'), table_name='department_feedback')
    op.drop_constraint(op.f('ck_department_feedback_revision_positive'), 'department_feedback', type_='check')
    op.drop_constraint(op.f('fk_department_feedback_reported_by_user_id_users'), 'department_feedback', type_='foreignkey')
    op.drop_constraint(op.f('fk_department_feedback_supersedes_id_department_feedback'), 'department_feedback', type_='foreignkey')
    op.drop_constraint(op.f('fk_department_feedback_attempt_id_handoff_attempts'), 'department_feedback', type_='foreignkey')
    op.drop_column('department_feedback', 'request_id')
    op.drop_column('department_feedback', 'reported_at')
    op.drop_column('department_feedback', 'reported_by_name')
    op.drop_column('department_feedback', 'reported_by_user_id')
    op.drop_constraint(op.f('ck_department_feedback_response_channel'), 'department_feedback', type_='check')
    op.drop_column('department_feedback', 'response_channel')
    op.drop_constraint(op.f('ck_department_feedback_interview_status'), 'department_feedback', type_='check')
    op.drop_column('department_feedback', 'interview_status')
    op.drop_constraint(op.f('ck_department_feedback_contact_status'), 'department_feedback', type_='check')
    op.drop_column('department_feedback', 'contact_status')
    op.drop_column('department_feedback', 'revision')
    op.drop_column('department_feedback', 'supersedes_id')
    op.drop_column('department_feedback', 'attempt_id')

    op.drop_index('uq_handoff_attempts_request_id', table_name='handoff_attempts', postgresql_where=sa.text('request_id IS NOT NULL'))
    op.drop_index('ix_handoff_attempts_open_status', table_name='handoff_attempts', postgresql_where=sa.text("status = 'awaiting_response'"))
    op.drop_index(op.f('ix_handoff_attempts_recipient_user_id'), table_name='handoff_attempts')
    op.drop_index(op.f('ix_handoff_attempts_application_id'), table_name='handoff_attempts')
    op.drop_table('handoff_attempts')
