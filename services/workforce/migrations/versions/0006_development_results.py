"""Frozen closure and selectively prepared result packages."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("development_plans", sa.Column("closure", sa.JSON()))
    op.create_table(
        "development_result_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("development_plans.id"), nullable=False),
        sa.Column("owner_actor_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
    )
    for field in ("organization_id", "owner_actor_id"):
        op.create_index(f"ix_development_result_packages_{field}", "development_result_packages", [field])


def downgrade():
    op.drop_table("development_result_packages")
    op.drop_column("development_plans", "closure")
