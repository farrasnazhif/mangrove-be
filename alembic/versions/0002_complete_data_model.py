"""Complete Task 02 without rewriting the Task 03 seed-support migration."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0002_complete_data_model"
down_revision = "0001_seed_support"
branch_labels = None
depends_on = None


def identifier():
    return sa.Column("id", pg.UUID(as_uuid=False), primary_key=True)


def timestamp(name="created_at"):
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade():
    # Existing user IDs are UUID strings; a non-UUID legacy ID deliberately fails
    # rather than silently replacing identities referenced by sessions or provenance.
    op.alter_column("users", "id", type_=pg.UUID(as_uuid=False), postgresql_using="id::uuid")
    op.create_table(
        "attachments",
        identifier(),
        timestamp(),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", pg.UUID(as_uuid=False), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(16), server_default="private", nullable=False),
        sa.Column("uploaded_by", pg.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("visibility IN ('private', 'public')", name="ck_attachments_visibility"),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachments_size"),
        sa.CheckConstraint("length(object_key) > 0", name="ck_attachments_key"),
    )
    op.create_index("ix_attachments_entity_id", "attachments", ["entity_id"])
    op.create_table(
        "dbh_import_batches",
        identifier(),
        sa.Column("source_drive_file_id", sa.String(200), nullable=False),
        sa.Column("source_revision", sa.String(200), nullable=False),
        sa.Column("imported_by", pg.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        timestamp("imported_at"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.UniqueConstraint(
            "source_drive_file_id", "source_revision", name="uq_import_source_revision"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'validated', 'imported', 'quarantine', 'failed')",
            name="ck_imports_status",
        ),
    )
    for table in ("plots", "tree_records", "sediment_cores", "sediment_layers"):
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True)))
    for table, name in (
        ("sediment_cores", "ck_cores_version"),
        ("sediment_layers", "ck_layers_version"),
    ):
        op.add_column(
            table, sa.Column("row_version", sa.Integer(), nullable=False, server_default="1")
        )
        op.create_check_constraint(name, table, "row_version > 0")
    for column in (
        sa.Column("display_name", sa.String(200)),
        sa.Column("default_density", sa.Float()),
        sa.Column("density_source", sa.String(500)),
        sa.Column("density_version", sa.String(100)),
    ):
        op.add_column("species", column)
    op.create_check_constraint(
        "ck_species_density", "species", "default_density > 0 AND default_density <= 2"
    )
    for column in (
        sa.Column("photo_id", pg.UUID(as_uuid=False), sa.ForeignKey("attachments.id")),
        sa.Column(
            "source_import_id", pg.UUID(as_uuid=False), sa.ForeignKey("dbh_import_batches.id")
        ),
        sa.Column("source_row_id", sa.String(200)),
        sa.Column("height_m", sa.Float()),
        sa.Column("notes", sa.String(2000)),
        timestamp("recorded_at"),
    ):
        op.add_column("tree_records", column)
    op.create_check_constraint("ck_trees_version", "tree_records", "row_version > 0")
    op.create_check_constraint("ck_trees_height", "tree_records", "height_m > 0")
    op.create_check_constraint(
        "ck_trees_source_pair",
        "tree_records",
        "(source_import_id IS NULL) = (source_row_id IS NULL)",
    )
    op.create_unique_constraint(
        "uq_trees_import_row", "tree_records", ["source_import_id", "source_row_id"]
    )
    op.add_column("method_versions", sa.Column("approved_at", sa.DateTime(timezone=True)))
    op.add_column("method_versions", sa.Column("effective_date", sa.Date()))
    op.add_column(
        "method_versions",
        sa.Column("rounding_rule", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_check_constraint(
        "ck_methods_status",
        "method_versions",
        "approval_status IN ('pending-scientific-approval', 'approved', 'rejected')",
    )
    op.create_check_constraint(
        "ck_methods_approval",
        "method_versions",
        "approval_status <> 'approved' OR (approved_at IS NOT NULL AND effective_date IS NOT NULL)",
    )
    op.create_table(
        "calculation_runs",
        identifier(),
        timestamp(),
        sa.Column("plot_id", pg.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=False),
        sa.Column(
            "method_version_id",
            pg.UUID(as_uuid=False),
            sa.ForeignKey("method_versions.id"),
            nullable=False,
        ),
        sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("qa_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("qa_status", sa.String(32), nullable=False, server_default="draft"),
        sa.UniqueConstraint("id", "plot_id", "qa_status", name="uq_runs_publication_target"),
        sa.CheckConstraint("input_revision > 0", name="ck_runs_revision"),
        sa.CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="ck_runs_hash"),
        sa.CheckConstraint("qa_status IN ('draft', 'approved', 'rejected')", name="ck_runs_status"),
    )
    op.create_index("ix_calculation_runs_plot_id", "calculation_runs", ["plot_id"])
    op.create_index(
        "ix_calculation_runs_method_version_id", "calculation_runs", ["method_version_id"]
    )
    op.create_table(
        "publications",
        sa.Column("plot_id", pg.UUID(as_uuid=False), sa.ForeignKey("plots.id"), primary_key=True),
        sa.Column("published_run_id", pg.UUID(as_uuid=False), nullable=False),
        sa.Column("run_qa_status", sa.String(32), nullable=False, server_default="approved"),
        timestamp("published_at"),
        sa.Column("approved_by", pg.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.ForeignKeyConstraint(
            ["published_run_id", "plot_id", "run_qa_status"],
            ["calculation_runs.id", "calculation_runs.plot_id", "calculation_runs.qa_status"],
            name="fk_publications_approved_plot_run",
        ),
        sa.CheckConstraint("run_qa_status = 'approved'", name="ck_publications_approved"),
    )
    op.create_table(
        "audit_events",
        identifier(),
        timestamp(),
        sa.Column("actor_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", pg.UUID(as_uuid=False), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("change_summary", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.execute("""
        CREATE FUNCTION task02_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable; insert a new record instead', TG_TABLE_NAME
                USING ERRCODE = '23514';
        END $$
    """)
    for table in ("method_versions", "calculation_runs", "audit_events"):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION task02_reject_mutation()
        """)
        op.execute(f"""
            CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION task02_reject_mutation()
        """)
    op.execute("""
        CREATE FUNCTION task02_check_run_method() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.qa_status = 'approved' AND NOT EXISTS (
                SELECT 1 FROM method_versions
                WHERE id = NEW.method_version_id AND approval_status = 'approved'
            ) THEN
                RAISE EXCEPTION 'An approved run requires an approved method'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER calculation_runs_approved_method BEFORE INSERT ON calculation_runs
        FOR EACH ROW EXECUTE FUNCTION task02_check_run_method()
    """)
    op.execute("""
        CREATE FUNCTION task02_check_audit_secrets() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF jsonb_typeof(NEW.change_summary::jsonb) <> 'object'
               OR jsonb_path_exists(NEW.change_summary::jsonb,
                   '$.** ? (@.type() == "object").keyvalue() ? (@.key like_regex
                    "password|token|secret|authorization|cookie" flag "i")') THEN
                RAISE EXCEPTION 'Audit changes must be an object without credential fields'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER audit_events_no_secrets BEFORE INSERT ON audit_events
        FOR EACH ROW EXECUTE FUNCTION task02_check_audit_secrets()
    """)


def downgrade():
    for table in ("audit_events", "publications", "calculation_runs"):
        op.drop_table(table)
    for function in ("task02_check_audit_secrets", "task02_check_run_method"):
        op.execute(f"DROP FUNCTION {function}()")
    op.execute("DROP TRIGGER method_versions_immutable ON method_versions")
    op.execute("DROP TRIGGER method_versions_no_truncate ON method_versions")
    op.execute("DROP FUNCTION task02_reject_mutation()")
    for name in ("ck_methods_status", "ck_methods_approval"):
        op.drop_constraint(name, "method_versions", type_="check")
    for column in ("rounding_rule", "effective_date", "approved_at"):
        op.drop_column("method_versions", column)
    for name in ("ck_trees_version", "ck_trees_height", "ck_trees_source_pair"):
        op.drop_constraint(name, "tree_records", type_="check")
    op.drop_constraint("uq_trees_import_row", "tree_records", type_="unique")
    for column in (
        "photo_id",
        "source_import_id",
        "source_row_id",
        "height_m",
        "notes",
        "recorded_at",
    ):
        op.drop_column("tree_records", column)
    for table, name in (
        ("sediment_cores", "ck_cores_version"),
        ("sediment_layers", "ck_layers_version"),
    ):
        op.drop_constraint(name, table, type_="check")
        op.drop_column(table, "row_version")
    for table in ("plots", "tree_records", "sediment_cores", "sediment_layers"):
        op.drop_column(table, "archived_at")
    op.drop_constraint("ck_species_density", "species", type_="check")
    for column in ("display_name", "default_density", "density_source", "density_version"):
        op.drop_column("species", column)
    op.drop_table("dbh_import_batches")
    op.drop_table("attachments")
    op.alter_column("users", "id", type_=sa.String(), postgresql_using="id::text")
