"""Persist calculation QA notices in the run transaction."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0004_manager_notices"
down_revision = "0003_active_layer_intervals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manager_notices",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("plot_id", UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=False),
        sa.Column(
            "calculation_run_id",
            UUID(as_uuid=False),
            sa.ForeignKey("calculation_runs.id"),
            nullable=False,
        ),
        sa.Column("plot_code", sa.String(50), nullable=False),
        sa.Column("flag", sa.String(100), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("suggested_action", sa.String(500), nullable=False),
        sa.UniqueConstraint("calculation_run_id", "flag", name="uq_notice_run_flag"),
    )
    op.create_index("ix_manager_notices_plot_id", "manager_notices", ["plot_id"])


def downgrade() -> None:
    op.drop_table("manager_notices")
