"""Per-application package provenance (requirements-03).

Revision ID: 0007_posting_sources
Revises: 0006
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_posting_sources"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_posting_sources",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("dataset_sha256", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_folder", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", "dataset_id", "dataset_sha256", "channel", "source_path", "source_sha256",
            name="uq_application_posting_sources_origin",
        ),
        sa.CheckConstraint("btrim(dataset_id) <> ''", name="dataset_id_nonempty"),
        sa.CheckConstraint("dataset_sha256 ~ '^[0-9a-f]{64}$'", name="dataset_sha256_format"),
        sa.CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="source_sha256_format"),
    )
    op.execute("""
        CREATE FUNCTION reject_posting_source_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'application posting source evidence is immutable';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER application_posting_sources_immutable
        BEFORE UPDATE ON application_posting_sources
        FOR EACH ROW EXECUTE FUNCTION reject_posting_source_update();
    """)


def downgrade() -> None:
    op.drop_table("application_posting_sources")
    op.execute("DROP FUNCTION reject_posting_source_update()")
