"""Versioned facts and semantic computation artifacts.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("processing_artifacts",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(200), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_processing_artifacts_kind", "processing_artifacts", ["kind"])
    op.create_index("ix_processing_artifacts_scope", "processing_artifacts", ["scope"])


def downgrade():
    op.drop_table("processing_artifacts")
