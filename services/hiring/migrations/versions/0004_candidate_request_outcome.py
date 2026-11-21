"""Candidate portal 5C: public outcomes, withdrawal and in-cabinet messages.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('candidate_requests', sa.Column('outcomes', postgresql.JSONB(astext_type=sa.Text()),
                                                  server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.alter_column('candidate_requests', 'outcomes', server_default=None)
    op.add_column('candidate_requests', sa.Column('withdrawal', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_check_constraint('ck_candidate_requests_withdrawn', 'candidate_requests',
                               "status <> 'withdrawn' OR withdrawal IS NOT NULL")
    op.create_table('candidate_request_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('next_action', sa.Text(), nullable=True),
    sa.Column('created_by_actor_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['request_id'], ['candidate_requests.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.CheckConstraint("kind IN ('information_request','outcome')", name='ck_candidate_request_messages_kind'),
    )
    op.create_index(op.f('ix_candidate_request_messages_request_id'), 'candidate_request_messages', ['request_id'],
                    unique=False)


def downgrade():
    op.drop_index(op.f('ix_candidate_request_messages_request_id'), table_name='candidate_request_messages')
    op.drop_table('candidate_request_messages')
    op.drop_constraint('ck_candidate_requests_withdrawn', 'candidate_requests', type_='check')
    op.drop_column('candidate_requests', 'withdrawal')
    op.drop_column('candidate_requests', 'outcomes')
