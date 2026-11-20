"""Persist duplicate groups, typed competency evidence, evaluator version.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('competency_indicators', sa.Column('same_as', sa.String(64), nullable=True))
    op.create_check_constraint(op.f('ck_competency_indicators_same_as_member'), 'competency_indicators',
        'same_as IS NULL OR (length(trim(same_as)) > 0 AND NOT excluded_from_scoring)')
    op.add_column('competency_scores', sa.Column('details', postgresql.JSONB(), nullable=True))
    op.add_column('assessments', sa.Column('algorithm_version', sa.String(64), nullable=True))
    op.add_column('assessments', sa.Column('calculation_as_of', sa.String(7), nullable=True))


def downgrade():
    op.drop_column('assessments', 'calculation_as_of')
    op.drop_column('assessments', 'algorithm_version')
    op.drop_column('competency_scores', 'details')
    op.drop_constraint(op.f('ck_competency_indicators_same_as_member'), 'competency_indicators', type_='check')
    op.drop_column('competency_indicators', 'same_as')
