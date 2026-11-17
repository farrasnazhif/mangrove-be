"""Task 02 acceptance checks on real PostGIS, isolated in a rollback-only schema."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from app.db.seed import seed_dataset, seed_id
from app.db.session import Base
from app.models import (
    Attachment,
    AuditEvent,
    CalculationRun,
    DbhImportBatch,
    MethodVersion,
    Plot,
    Publication,
    SedimentLayer,
    Tree,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL for PostGIS tests"
    ),
]


@pytest.fixture(scope="module")
def database():
    @asynccontextmanager
    async def isolated():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        try:
            async with engine.connect() as connection, connection.begin():
                schema = "task02_test_" + uuid4().hex
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

                def migrate(sync_connection, target):
                    config = Config("alembic.ini")
                    config.attributes["connection"] = sync_connection
                    config.attributes["version_table_schema"] = schema
                    if target == "base":
                        command.downgrade(config, target)
                    else:
                        command.upgrade(config, target)

                # Check a real upgrade from existing Task 03 data, not just an empty DB.
                await connection.run_sync(migrate, "0001_seed_support")
                await connection.execute(
                    text("""
                    INSERT INTO users
                        (id, email, role, is_active, created_at, data_label)
                    VALUES (:id, 'legacy@example.test', 'manager', true, now(), 'synthetic')
                """),
                    {"id": str(uuid4())},
                )
                await connection.run_sync(migrate, "head")
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    await seed_dataset(
                        session,
                        email="manager.synthetic@example.test",
                        password="test-password-123",
                    )
                    await session.flush()
                    yield session, connection
                await connection.run_sync(migrate, "base")
                assert (
                    await connection.scalar(
                        text("SELECT to_regclass(:name)"), {"name": f"{schema}.plots"}
                    )
                    is None
                )
                # Exercise clean upgrade too, then roll back all schema/data changes.
                await connection.run_sync(migrate, "head")
                await connection.rollback()
        finally:
            await engine.dispose()

    with asyncio.Runner() as runner:

        async def wait(awaitable):
            return await awaitable

        def run(awaitable):
            return runner.run(wait(awaitable))

        context = isolated()
        session, connection = run(context.__aenter__())
        try:
            yield run, session, connection
        finally:
            run(context.__aexit__(None, None, None))


@pytest.fixture
def db(database):
    run, session, connection = database
    savepoint = run(connection.begin_nested())
    try:
        yield run, session
    finally:
        run(savepoint.rollback())
        session.expunge_all()


async def rejected(session, statement, constraint=None):
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            await session.execute(statement)
    if constraint:
        assert constraint in str(error.value)


def tree(**overrides):
    return {
        "id": str(uuid4()),
        "plot_id": seed_id("plot-1"),
        "species_id": seed_id("species"),
        "dbh_cm": 12,
        "density_source": "synthetic",
        "data_label": "synthetic",
        **overrides,
    }


def method(**overrides):
    return {
        "id": str(uuid4()),
        "version": str(uuid4()),
        "coefficients_json": {},
        "references": [],
        "approval_status": "approved",
        "approved_at": datetime.now(UTC),
        "effective_date": date(2026, 1, 1),
        "data_label": "synthetic",
        **overrides,
    }


def calculation(method_id, **overrides):
    return {
        "id": str(uuid4()),
        "plot_id": seed_id("plot-1"),
        "method_version_id": method_id,
        "input_revision": 1,
        "input_hash": "a" * 64,
        "input_snapshot": {"tree": {"dbh_cm": 11}},
        "result_json": {"agc": 1.23456789012345},
        "qa_status": "approved",
        **overrides,
    }


def test_inventory_constraints_and_nullable_photo(db):
    async def check(session):
        for values, constraint in [
            ({"dbh_cm": 0}, "ck_trees_dbh"),
            ({"wood_density_g_cm3": 2.1}, "ck_trees_density"),
            ({"height_m": -1}, "ck_trees_height"),
            ({"row_version": 0}, "ck_trees_version"),
            ({"plot_id": str(uuid4())}, None),
            ({"species_id": str(uuid4())}, None),
            ({"photo_id": str(uuid4())}, None),
            ({"source_row_id": "row-1"}, "ck_trees_source_pair"),
        ]:
            await rejected(session, insert(Tree).values(**tree(**values)), constraint)
        record = tree(photo_id=None, wood_density_g_cm3=None)
        await session.execute(insert(Tree).values(**record))
        assert (await session.get(Tree, record["id"])).photo_id is None
        for values, constraint in [
            ({"code": "bad"}, "ck_plots_code"),
            ({"code": "VAK-9002"}, None),
            ({"area_m2": 0}, "ck_plots_area"),
            ({"latitude": 91}, None),
            ({"longitude": 181}, None),
            ({"zone_id": str(uuid4())}, None),
            ({"row_version": 0}, "ck_plots_version"),
        ]:
            await rejected(
                session,
                update(Plot).where(Plot.id == seed_id("plot-1")).values(**values),
                constraint,
            )

    run, session = db
    run(check(session))


def test_sediment_overlap_and_measurements(db):
    async def check(session):
        base = {
            "core_id": seed_id("plot-1/core"),
            "depth_top_cm": 20,
            "depth_bottom_cm": 30,
            "dry_mass_g": 45,
            "volume_cm3": 50,
            "loi_pct": 8,
            "data_label": "synthetic",
        }
        for values, constraint in [
            ({"depth_top_cm": 5}, "ex_layers_overlap"),
            ({"depth_top_cm": -1}, "ck_layers_depth"),
            ({"depth_bottom_cm": 20}, "ck_layers_depth"),
            ({"dry_mass_g": 0}, "ck_layers_mass_volume"),
            ({"volume_cm3": -1}, "ck_layers_mass_volume"),
            ({"loi_pct": 101}, "ck_layers_loi"),
            ({"core_id": str(uuid4())}, None),
        ]:
            await rejected(session, insert(SedimentLayer).values(**(base | values)), constraint)
        await session.execute(insert(SedimentLayer).values(**base))  # Adjacent [20,30) is valid.
        await session.execute(
            insert(SedimentLayer).values(**(base | {"core_id": seed_id("plot-2/core")}))
        )  # Independent core is valid.

    run, session = db
    run(check(session))


def test_import_provenance_and_private_attachment(db):
    async def check(session):
        batch = {
            "id": str(uuid4()),
            "source_drive_file_id": "synthetic-file",
            "source_revision": "rev-1",
            "imported_by": seed_id("manager"),
        }
        await session.execute(insert(DbhImportBatch).values(**batch))
        await rejected(
            session,
            insert(DbhImportBatch).values(**(batch | {"id": str(uuid4())})),
            "uq_import_source_revision",
        )
        photo = {
            "id": str(uuid4()),
            "entity_type": "tree",
            "entity_id": str(uuid4()),
            "object_key": "synthetic/photo.jpg",
            "mime_type": "image/jpeg",
            "size_bytes": 100,
            "uploaded_by": seed_id("manager"),
        }
        await session.execute(insert(Attachment).values(**photo))
        assert (await session.get(Attachment, photo["id"])).visibility == "private"
        values = tree(
            id=photo["entity_id"],
            photo_id=photo["id"],
            source_import_id=batch["id"],
            source_row_id="1",
        )
        await session.execute(insert(Tree).values(**values))
        await rejected(
            session, insert(Tree).values(**(values | {"id": str(uuid4())})), "uq_trees_import_row"
        )
        for table, identity in [("attachments", photo["id"]), ("dbh_import_batches", batch["id"])]:
            await rejected(
                session,
                text(f"DELETE FROM {table} WHERE id = CAST(:id AS uuid)").bindparams(id=identity),
            )

    run, session = db
    run(check(session))


def test_immutable_runs_methods_and_publication_ownership(db):
    async def check(session):
        approved_method = method()
        await session.execute(insert(MethodVersion).values(**approved_method))
        first = calculation(approved_method["id"])
        draft = calculation(approved_method["id"], qa_status="draft")
        other = calculation(approved_method["id"], plot_id=seed_id("plot-2"))
        for record in (first, draft, other):
            await session.execute(insert(CalculationRun).values(**record))
        await rejected(session, insert(CalculationRun).values(**calculation(seed_id("method"))))
        for table, identity in [
            ("method_versions", approved_method["id"]),
            ("calculation_runs", first["id"]),
        ]:
            for statement in (
                f"UPDATE {table} SET id = id WHERE id = CAST(:id AS uuid)",
                f"DELETE FROM {table} WHERE id = CAST(:id AS uuid)",
            ):
                await rejected(session, text(statement).bindparams(id=identity))
            await rejected(session, text(f"TRUNCATE {table} CASCADE"))
        publication = {
            "plot_id": first["plot_id"],
            "published_run_id": first["id"],
            "approved_by": seed_id("manager"),
        }
        await session.execute(insert(Publication).values(**publication))
        await rejected(session, insert(Publication).values(**publication))  # One pointer per plot.
        for values in (
            {"published_run_id": other["id"]},
            {"published_run_id": draft["id"]},
            {"published_run_id": draft["id"], "run_qa_status": "draft"},
        ):
            await rejected(session, update(Publication).values(**values))
        await session.execute(
            update(Tree).where(Tree.id == seed_id("plot-1/tree-1")).values(dbh_cm=99, row_version=2)
        )
        stored = await session.get(CalculationRun, first["id"])
        assert stored.input_snapshot == first["input_snapshot"]
        assert stored.result_json == first["result_json"]
        assert (await session.get(Publication, first["plot_id"])).published_run_id == first["id"]
        replacement = calculation(approved_method["id"], input_revision=2)
        await session.execute(insert(CalculationRun).values(**replacement))
        await session.execute(update(Publication).values(published_run_id=replacement["id"]))
        assert await session.scalar(
            select(CalculationRun.id).where(CalculationRun.id == first["id"])
        )

    run, session = db
    run(check(session))


def test_audit_append_only_and_secret_keys(db):
    async def check(session):
        event = {
            "id": str(uuid4()),
            "actor_id": seed_id("manager"),
            "entity_type": "tree",
            "entity_id": seed_id("plot-1/tree-1"),
            "action": "update",
            "change_summary": {"dbh_cm": {"before": 11, "after": 12}},
        }
        await session.execute(insert(AuditEvent).values(**event))
        for changes in (
            {"password": "redacted"},
            {"nested": [{"access_token": "redacted"}]},
            {"nested": {"hashed_password": "redacted"}},
            {"Cookie": "redacted"},
        ):
            await rejected(
                session,
                insert(AuditEvent).values(
                    **(event | {"id": str(uuid4()), "change_summary": changes})
                ),
            )
        for statement in (
            "UPDATE audit_events SET action = 'tampered'",
            "DELETE FROM audit_events",
            "TRUNCATE audit_events",
        ):
            await rejected(session, text(statement))

    run, session = db
    run(check(session))


def test_audit_app_role_cannot_rewrite_history(db):
    async def check(session):
        role = "task02_app_" + uuid4().hex
        await session.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
        schema = await session.scalar(text("SELECT current_schema()"))
        await session.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
        await session.execute(
            text(f'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON audit_events TO "{role}"')
        )
        await session.execute(
            insert(AuditEvent).values(
                actor_id=seed_id("manager"),
                entity_type="tree",
                entity_id=seed_id("plot-1/tree-1"),
                action="update",
                change_summary={"dbh_cm": {"before": 11, "after": 12}},
            )
        )
        await session.execute(text(f'SET LOCAL ROLE "{role}"'))
        try:
            for statement in (
                "UPDATE audit_events SET action = 'tampered'",
                "DELETE FROM audit_events",
                "TRUNCATE audit_events",
            ):
                await rejected(session, text(statement))
        finally:
            await session.execute(text("RESET ROLE"))

    run, session = db
    run(check(session))


def test_migration_matches_orm_metadata(database):
    run, _, connection = database

    def check(sync_connection):
        context = MigrationContext.configure(
            sync_connection,
            opts={
                "compare_type": True,
                "include_object": lambda obj, name, kind, reflected, target: (
                    name not in {"alembic_version", "spatial_ref_sys"}
                ),
            },
        )
        assert compare_metadata(context, Base.metadata) == []

    run(connection.run_sync(check))
