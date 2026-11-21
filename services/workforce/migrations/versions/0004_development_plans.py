"""Personal goals, preserved revisions and development agreements."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def resource():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def ref(name, target, nullable=False):
    return sa.Column(name, sa.String(36), sa.ForeignKey(target), nullable=nullable)


def upgrade():
    op.create_table(
        "development_goals",
        *resource(),
        ref("organization_id", "organizations.id"),
        ref("owner_actor_id", "actors.id"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        ref("shared_with_actor_id", "actors.id", True),
        sa.Column("share_basis", sa.JSON()),
        sa.CheckConstraint("status IN ('private', 'shared')", name="development_goal_status"),
    )
    op.create_table(
        "development_goal_versions",
        sa.Column("goal_id", sa.String(36), sa.ForeignKey("development_goals.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )
    op.create_table(
        "development_plans",
        *resource(),
        ref("organization_id", "organizations.id"),
        ref("goal_id", "development_goals.id"),
        ref("owner_actor_id", "actors.id"),
        ref("manager_actor_id", "actors.id"),
        ref("reviewer_actor_id", "actors.id"),
        sa.Column("assignment_basis", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("activities", sa.JSON(), nullable=False),
        sa.Column("goal_revision", sa.Integer(), nullable=False),
        sa.Column("goal_snapshot", sa.JSON(), nullable=False),
        sa.Column("agreed_revision", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("decision_note", sa.Text()),
        sa.CheckConstraint(
            "status IN ('proposed', 'returned', 'active', 'closed')", name="development_plan_status"
        ),
        sa.CheckConstraint("reviewer_actor_id <> owner_actor_id", name="development_no_self_review"),
    )
    for table in ("development_goals", "development_plans"):
        for field in ("organization_id", "owner_actor_id"):
            op.create_index(f"ix_{table}_{field}", table, [field])


def downgrade():
    op.drop_table("development_plans")
    op.drop_table("development_goal_versions")
    op.drop_table("development_goals")
