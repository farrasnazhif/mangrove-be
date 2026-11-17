"""Real concurrent transactions must reject the second edit of the same revision."""

import asyncio
import os
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from app.core.errors import APIError
from app.db.seed import seed_dataset, seed_id
from app.models import AuditEvent, Plot
from app.schemas.inventory import PlotUpdate
from app.services.field_data import update_plot

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL"),
]


def test_simultaneous_plot_edits_reject_stale_writer():
    async def check():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        schema = "task05_concurrency_" + uuid4().hex

        def migrate(connection):
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            config.attributes["version_table_schema"] = schema
            command.upgrade(config, "head")

        try:
            async with engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
                await connection.run_sync(migrate)
                async with AsyncSession(bind=connection) as session:
                    await seed_dataset(
                        session,
                        email="manager.synthetic@example.test",
                        password="test-password-123",
                    )
                    await session.flush()

            locked = asyncio.Event()
            attempted = asyncio.Event()

            async def edit(first):
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    try:
                        async with session.begin():
                            await session.execute(
                                text(f'SET LOCAL search_path TO "{schema}", public')
                            )
                            if first:
                                await session.scalar(
                                    select(Plot)
                                    .where(Plot.id == seed_id("plot-1"))
                                    .with_for_update()
                                )
                                locked.set()
                                await attempted.wait()
                                await asyncio.sleep(0.05)
                            else:
                                await locked.wait()
                                attempted.set()
                            await update_plot(
                                session,
                                seed_id("plot-1"),
                                PlotUpdate(row_version=1, area_m2=120 if first else 999),
                                seed_id("manager"),
                            )
                        return 200
                    except APIError as exc:
                        return exc.status_code

            assert await asyncio.wait_for(asyncio.gather(edit(True), edit(False)), timeout=15) == [
                200,
                409,
            ]
            async with engine.begin() as connection:
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
                assert (
                    await connection.scalar(
                        select(Plot.area_m2).where(Plot.id == seed_id("plot-1"))
                    )
                    == 120
                )
                assert (
                    await connection.scalar(
                        select(Plot.row_version).where(Plot.id == seed_id("plot-1"))
                    )
                    == 2
                )
                assert await connection.scalar(select(func.count()).select_from(AuditEvent)) == 1
        finally:
            # Only this test's UUID-named schema is removed; other data is untouched.
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await engine.dispose()

    asyncio.run(check())
