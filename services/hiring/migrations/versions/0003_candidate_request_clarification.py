"""Candidate portal 5B: information request, addenda, readiness and manual consideration record.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('candidate_requests', sa.Column('information_request', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('candidate_requests', sa.Column('addenda', postgresql.JSONB(astext_type=sa.Text()),
                                                  server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.alter_column('candidate_requests', 'addenda', server_default=None)
    op.add_column('candidate_requests', sa.Column('review', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('candidate_requests', sa.Column('consideration', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # Переданное в подбор обращение всегда несёт ручное подтверждение регистрации.
    op.create_check_constraint('ck_candidate_requests_forwarded', 'candidate_requests',
                               "status <> 'forwarded' OR consideration IS NOT NULL")


def downgrade():
    op.drop_constraint('ck_candidate_requests_forwarded', 'candidate_requests', type_='check')
    op.drop_column('candidate_requests', 'consideration')
    op.drop_column('candidate_requests', 'review')
    op.drop_column('candidate_requests', 'addenda')
    op.drop_column('candidate_requests', 'information_request')
