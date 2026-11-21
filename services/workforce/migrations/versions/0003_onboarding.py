"""Fixed introductory templates and assigned programme snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "onboarding_templates",
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
    )
    op.create_table(
        "onboarding_programs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("workforce_assignment_id", sa.String(36), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("template_code", sa.String(100), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("assigned_by_actor_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("cancel_reason", sa.String(300)),
        sa.UniqueConstraint("workforce_assignment_id", "template_code", "template_version"),
        sa.ForeignKeyConstraint(
            ["template_code", "template_version"],
            ["onboarding_templates.code", "onboarding_templates.version"],
        ),
        sa.CheckConstraint("status IN ('active', 'intro_completed', 'cancelled')", name="onboarding_status"),
    )
    op.create_index("ix_onboarding_programs_organization_id", "onboarding_programs", ["organization_id"])
    op.create_index("ix_onboarding_programs_employee_id", "onboarding_programs", ["employee_id"])


def downgrade():
    op.drop_table("onboarding_programs")
    op.drop_table("onboarding_templates")
