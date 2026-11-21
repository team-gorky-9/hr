"""Vacancy catalog and immutable revision snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_vacancy_catalog"
down_revision = "0001_initial_requirements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_vacancies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("position_code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("approved_profiles.id"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("close_reason", sa.Text()),
    )
    op.create_index("ix_catalog_vacancies_organization_id", "catalog_vacancies", ["organization_id"])
    op.create_table(
        "catalog_vacancy_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("vacancy_id", sa.Uuid(), sa.ForeignKey("catalog_vacancies.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.UniqueConstraint("vacancy_id", "revision"),
    )


def downgrade():
    op.drop_table("catalog_vacancy_history")
    op.drop_index("ix_catalog_vacancies_organization_id", table_name="catalog_vacancies")
    op.drop_table("catalog_vacancies")
