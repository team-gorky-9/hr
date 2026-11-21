"""Durable mobility resources and append-only history."""
from alembic import op
import sqlalchemy as sa

revision = "0001_mobility"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("mobility_resources", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("organization_id", sa.String(36), nullable=False),
                    sa.Column("kind", sa.String(32), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
                    sa.Column("payload", sa.JSON(), nullable=False))
    op.create_index("ix_mobility_resources_organization_id", "mobility_resources", ["organization_id"])
    op.create_index("ix_mobility_resources_kind", "mobility_resources", ["kind"])
    op.create_table("mobility_history", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("organization_id", sa.String(36), nullable=False),
                    sa.Column("resource_id", sa.String(36), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
                    sa.Column("snapshot", sa.JSON(), nullable=False), sa.Column("actor_id", sa.String(36), nullable=False),
                    sa.Column("action", sa.String(64), nullable=False), sa.Column("recorded_at", sa.String(40), nullable=False),
                    sa.UniqueConstraint("resource_id", "revision"))
    op.create_index("ix_mobility_history_organization_id", "mobility_history", ["organization_id"])
    op.create_index("ix_mobility_history_resource_id", "mobility_history", ["resource_id"])


def downgrade():
    op.drop_table("mobility_history")
    op.drop_table("mobility_resources")
