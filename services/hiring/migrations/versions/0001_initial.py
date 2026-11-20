"""Initial hiring schema: cases, checklist items, immutable documents, history, idempotent commands.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('cases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('application_system', sa.String(length=40), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('selection', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.Column('source_mode', sa.String(length=20), nullable=False),
    sa.Column('verified_by_actor_id', sa.UUID(), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('checklist_version', sa.String(length=80), nullable=False),
    sa.Column('candidate_actor_id', sa.UUID(), nullable=True),
    sa.Column('identity_basis', sa.Text(), nullable=True),
    sa.Column('withdraw_reason', sa.Text(), nullable=True),
    sa.Column('starts_on', sa.Date(), nullable=True),
    sa.Column('basis', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('confirmation_basis', sa.Text(), nullable=True),
    sa.Column('started_by_actor_id', sa.UUID(), nullable=True),
    sa.Column('start_version', sa.Integer(), nullable=False),
    sa.Column('transfer_mode', sa.String(length=20), nullable=False),
    sa.Column('workforce_status', sa.String(length=40), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=True),
    sa.Column('assignment_id', sa.UUID(), nullable=True),
    sa.Column('workforce_confirmation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('workforce_assignment_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('workforce_resolution', sa.String(length=20), nullable=True),
    sa.Column('workforce_review_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    # Closed value sets of wave-1-hiring; a typo in code fails at the database, not silently.
    sa.CheckConstraint("status IN ('preparing','awaiting_documents','ready','withdrawn','started')",
                       name='ck_cases_status'),
    sa.CheckConstraint("workforce_status IN ('not_sent','pending','registered','registered_with_difference',"
                       "'review_required')", name='ck_cases_workforce_status'),
    sa.CheckConstraint("workforce_resolution IS NULL OR workforce_resolution IN ('corrected','kept_existing')",
                       name='ck_cases_workforce_resolution'),
    sa.CheckConstraint("source_mode IN ('fixture','manual-confirmed','legacy-api')", name='ck_cases_source_mode'),
    sa.CheckConstraint("transfer_mode IN ('manual','broker')", name='ck_cases_transfer_mode'),
    sa.CheckConstraint('revision >= 1', name='ck_cases_revision'),
    )
    op.create_index(op.f('ix_cases_candidate_actor_id'), 'cases', ['candidate_actor_id'], unique=False)
    op.create_index('ix_cases_org_created', 'cases', ['organization_id', 'created_at', 'id'], unique=False)
    op.create_index(op.f('ix_cases_organization_id'), 'cases', ['organization_id'], unique=False)
    op.create_index('uq_cases_active_application', 'cases', ['application_system', 'application_id'], unique=True, postgresql_where=sa.text("status <> 'withdrawn'"))
    op.create_table('idempotent_commands',
    sa.Column('scope', sa.String(length=64), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('scope')
    )
    op.create_table('case_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('case_revision', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=True),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('actor_role', sa.String(length=20), nullable=False),
    sa.Column('visible_to_candidate', sa.Boolean(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('candidate_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'sequence', name='uq_case_events_sequence')
    )
    op.create_index(op.f('ix_case_events_case_id'), 'case_events', ['case_id'], unique=False)
    op.create_table('checklist_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('required', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('document_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('review_reason', sa.Text(), nullable=True),
    sa.Column('reviewed_by_actor_id', sa.UUID(), nullable=True),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'key', name='uq_checklist_items_case_key'),
    sa.CheckConstraint("status IN ('requested','received','accepted','needs_revision')",
                       name='ck_checklist_items_status'),
    sa.CheckConstraint('revision >= 1', name='ck_checklist_items_revision'),
    )
    op.create_index(op.f('ix_checklist_items_case_id'), 'checklist_items', ['case_id'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('original_name', sa.Text(), nullable=False),
    sa.Column('media_type', sa.String(length=80), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('uploaded_by', sa.UUID(), nullable=False),
    sa.Column('uploaded_by_role', sa.String(length=20), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.CheckConstraint("kind IN ('hiring_application','hiring_evidence','employment_basis')",
                       name='ck_documents_kind'),
    sa.CheckConstraint('size_bytes > 0', name='ck_documents_size'),
    )
    op.create_index(op.f('ix_documents_case_id'), 'documents', ['case_id'], unique=False)
    op.create_index(op.f('ix_documents_organization_id'), 'documents', ['organization_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_documents_organization_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_case_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_checklist_items_case_id'), table_name='checklist_items')
    op.drop_table('checklist_items')
    op.drop_index(op.f('ix_case_events_case_id'), table_name='case_events')
    op.drop_table('case_events')
    op.drop_table('idempotent_commands')
    op.drop_index('uq_cases_active_application', table_name='cases', postgresql_where=sa.text("status <> 'withdrawn'"))
    op.drop_index(op.f('ix_cases_organization_id'), table_name='cases')
    op.drop_index('ix_cases_org_created', table_name='cases')
    op.drop_index(op.f('ix_cases_candidate_actor_id'), table_name='cases')
    op.drop_table('cases')
