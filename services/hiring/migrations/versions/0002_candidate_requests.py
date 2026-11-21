"""Candidate portal (wave-5 5A): own candidate requests, their history and documents.

- candidate_requests, candidate_request_events — new tables;
- documents.request_id — a document of a candidate request (cases are not touched);
- ck_documents_kind gains candidate_resume and candidate_addendum;
- candidate_request_number_seq — human number assigned on submit.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

OLD_KINDS = "kind IN ('hiring_application','hiring_evidence','employment_basis')"
NEW_KINDS = ("kind IN ('hiring_application','hiring_evidence','employment_basis',"
             "'candidate_resume','candidate_addendum')")


def upgrade():
    op.create_table('candidate_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('author_actor_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('vacancy_ref', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('vacancy', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('target_question', sa.String(length=32), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('contact', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number'),
    sa.CheckConstraint("status IN ('draft','submitted','needs_information','ready','forwarded','closed','withdrawn')",
                       name='ck_candidate_requests_status'),
    sa.CheckConstraint("target_question IS NULL OR target_question IN ('no_target','vacancy_closed','vacancy_unknown')",
                       name='ck_candidate_requests_target_question'),
    sa.CheckConstraint('revision >= 1', name='ck_candidate_requests_revision'),
    sa.CheckConstraint("(status = 'draft') = (submitted_at IS NULL)", name='ck_candidate_requests_submitted'),
    )
    op.create_index(op.f('ix_candidate_requests_organization_id'), 'candidate_requests', ['organization_id'], unique=False)
    op.create_index(op.f('ix_candidate_requests_author_actor_id'), 'candidate_requests', ['author_actor_id'], unique=False)
    op.create_table('candidate_request_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('request_revision', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('actor_role', sa.String(length=20), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['request_id'], ['candidate_requests.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('request_id', 'sequence', name='uq_candidate_request_events_sequence'),
    )
    op.create_index(op.f('ix_candidate_request_events_request_id'), 'candidate_request_events', ['request_id'], unique=False)
    op.add_column('documents', sa.Column('request_id', sa.UUID(), nullable=True))
    op.create_foreign_key('documents_request_id_fkey', 'documents', 'candidate_requests', ['request_id'], ['id'])
    op.create_index(op.f('ix_documents_request_id'), 'documents', ['request_id'], unique=False)
    op.drop_constraint('ck_documents_kind', 'documents', type_='check')
    op.create_check_constraint('ck_documents_kind', 'documents', NEW_KINDS)
    op.execute("CREATE SEQUENCE candidate_request_number_seq START 1")


def downgrade():
    op.execute("DROP SEQUENCE candidate_request_number_seq")
    op.drop_constraint('ck_documents_kind', 'documents', type_='check')
    op.create_check_constraint('ck_documents_kind', 'documents', OLD_KINDS)
    op.drop_index(op.f('ix_documents_request_id'), table_name='documents')
    op.drop_constraint('documents_request_id_fkey', 'documents', type_='foreignkey')
    op.drop_column('documents', 'request_id')
    op.drop_index(op.f('ix_candidate_request_events_request_id'), table_name='candidate_request_events')
    op.drop_table('candidate_request_events')
    op.drop_index(op.f('ix_candidate_requests_author_actor_id'), table_name='candidate_requests')
    op.drop_index(op.f('ix_candidate_requests_organization_id'), table_name='candidate_requests')
    op.drop_table('candidate_requests')
