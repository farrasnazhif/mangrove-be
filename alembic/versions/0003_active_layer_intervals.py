"""Allow archived sediment layers to be replaced while preserving their history."""

from alembic import op

revision = "0003_active_layer_intervals"
down_revision = "0002_complete_data_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sediment_layers DROP CONSTRAINT ex_layers_overlap")
    op.execute("""
        ALTER TABLE sediment_layers ADD CONSTRAINT ex_layers_overlap
        EXCLUDE USING gist (
            core_id WITH =,
            numrange(depth_top_cm::numeric, depth_bottom_cm::numeric, '[)') WITH &&
        ) WHERE (archived_at IS NULL)
    """)


def downgrade() -> None:
    # Historical archived replacements may overlap. Fail transactionally rather
    # than removing history to make the previous constraint fit.
    op.execute("ALTER TABLE sediment_layers DROP CONSTRAINT ex_layers_overlap")
    op.execute("""
        ALTER TABLE sediment_layers ADD CONSTRAINT ex_layers_overlap
        EXCLUDE USING gist (
            core_id WITH =,
            numrange(depth_top_cm::numeric, depth_bottom_cm::numeric, '[)') WITH &&
        )
    """)
