"""Task 03 supporting schema; not the complete Task 02 data model."""

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_seed_support"
down_revision = None
branch_labels = None
depends_on = None


def synthetic_columns():
    return [
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("data_label", sa.String(32), nullable=False),
    ]


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public")
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=True),
        sa.Column("role", sa.Enum("manager", "visitor", name="user_role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_label", sa.String(32), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "zones",
        *synthetic_columns(),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("boundary_geom", Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column("boundary_source", sa.String(500), nullable=False),
        sa.Column("boundary_revision", sa.String(100), nullable=False),
        sa.Column("boundary_is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("approved_scope", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "NOT boundary_is_synthetic OR NOT approved_scope", name="ck_zones_approval"
        ),
        sa.CheckConstraint("ST_IsValid(boundary_geom)", name="ck_zones_valid_boundary"),
    )
    op.create_table(
        "plots",
        *synthetic_columns(),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "zone_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("zones.id"), nullable=False
        ),
        sa.Column("area_m2", sa.Float(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326), nullable=False),
        sa.Column("survey_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scope_reason", sa.String(100)),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("code ~ '^VAK-[0-9]+$'", name="ck_plots_code"),
        sa.CheckConstraint("area_m2 > 0", name="ck_plots_area"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_plots_latitude"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_plots_longitude"),
        sa.CheckConstraint("status IN ('draft', 'quarantine')", name="ck_plots_status"),
        sa.CheckConstraint("row_version > 0", name="ck_plots_version"),
        sa.CheckConstraint(
            "ST_X(geom) = longitude AND ST_Y(geom) = latitude", name="ck_plots_coordinates_match"
        ),
    )
    op.create_index("ix_plots_zone_id", "plots", ["zone_id"])
    op.create_table(
        "species",
        *synthetic_columns(),
        sa.Column("scientific_name", sa.String(200), nullable=False, unique=True),
    )
    op.create_table(
        "tree_records",
        *synthetic_columns(),
        sa.Column(
            "plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=False
        ),
        sa.Column(
            "species_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("species.id"),
            nullable=False,
        ),
        sa.Column("dbh_cm", sa.Float(), nullable=False),
        sa.Column("wood_density_g_cm3", sa.Float()),
        sa.Column("density_source", sa.String(200), nullable=False),
        sa.Column("qa_status", sa.String(32), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("dbh_cm > 0", name="ck_trees_dbh"),
        sa.CheckConstraint(
            "wood_density_g_cm3 > 0 AND wood_density_g_cm3 <= 2", name="ck_trees_density"
        ),
    )
    op.create_index("ix_tree_records_plot_id", "tree_records", ["plot_id"])
    op.create_table(
        "sediment_cores",
        *synthetic_columns(),
        sa.Column(
            "plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=False
        ),
        sa.Column("sample_code", sa.String(100), nullable=False, unique=True),
        sa.Column("sample_date", sa.Date(), nullable=False),
    )
    op.create_index("ix_sediment_cores_plot_id", "sediment_cores", ["plot_id"])
    op.create_table(
        "sediment_layers",
        *synthetic_columns(),
        sa.Column(
            "core_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sediment_cores.id"),
            nullable=False,
        ),
        sa.Column("depth_top_cm", sa.Float(), nullable=False),
        sa.Column("depth_bottom_cm", sa.Float(), nullable=False),
        sa.Column("dry_mass_g", sa.Float(), nullable=False),
        sa.Column("volume_cm3", sa.Float(), nullable=False),
        sa.Column("loi_pct", sa.Float(), nullable=False),
        sa.Column("qa_status", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "depth_bottom_cm > depth_top_cm AND depth_top_cm >= 0", name="ck_layers_depth"
        ),
        sa.CheckConstraint("dry_mass_g > 0 AND volume_cm3 > 0", name="ck_layers_mass_volume"),
        sa.CheckConstraint("loi_pct BETWEEN 0 AND 100", name="ck_layers_loi"),
        postgresql.ExcludeConstraint(
            ("core_id", "="),
            (sa.text("numrange(depth_top_cm::numeric, depth_bottom_cm::numeric, '[)')"), "&&"),
            name="ex_layers_overlap",
            using="gist",
        ),
    )
    op.create_index("ix_sediment_layers_core_id", "sediment_layers", ["core_id"])
    op.create_table(
        "method_versions",
        *synthetic_columns(),
        sa.Column("version", sa.String(100), nullable=False, unique=True),
        sa.Column("coefficients_json", sa.JSON(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(100), nullable=False),
    )


def downgrade():
    for table in (
        "method_versions",
        "sediment_layers",
        "sediment_cores",
        "tree_records",
        "species",
        "plots",
        "zones",
        "users",
    ):
        op.drop_table(table)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
    # Shared extensions may be used by other schemas; intentionally retain them.
