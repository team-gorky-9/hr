"""Keep the last decision on a corrected employment readiness version."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("intakes", sa.Column("last_review", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("intakes", "last_review")
