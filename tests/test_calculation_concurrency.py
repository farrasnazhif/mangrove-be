"""A run and a field edit must serialize on the same plot revision."""

import asyncio
import os
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from app.core.errors import APIError
from app.db.seed import seed_dataset, seed_id
from app.models import CalculationRun, Plot
from app.schemas.inventory import CalculationRequest, PlotUpdate
from app.services.calculation_runs import create_run
from app.services.field_data import update_plot

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL"),
]


@pytest.mark.parametrize("calculate_first", [True, False])
def test_calculation_and_input_edit_serialize(calculate_first):
    async def check():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        schema = "task06_concurrency_" + uuid4().hex

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
            first_done = asyncio.Event()
            second_attempted = asyncio.Event()

            async def mutate(is_calculation):
                first = is_calculation == calculate_first
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    try:
                        async with session.begin():
                            await session.execute(
                                text(f'SET LOCAL search_path TO "{schema}", public')
                            )
                            if not first:
                                await first_done.wait()
                                second_attempted.set()
                            if is_calculation:
                                await create_run(
                                    session,
                                    seed_id("plot-1"),
                                    CalculationRequest(
                                        method_version_id=seed_id("method"),
                                        input_revision=1,
                                        expected_bottom_cm=20,
                                    ),
                                    seed_id("manager"),
                                )
                            else:
                                await update_plot(
                                    session,
                                    seed_id("plot-1"),
                                    PlotUpdate(
                                        row_version=1,
                                        area_m2=120,
                                    ),
                                    seed_id("manager"),
                                )
                            if first:
                                first_done.set()
                                await second_attempted.wait()
                                await asyncio.sleep(0.05)
                        return 200
                    except APIError as exc:
                        return exc.status_code

            statuses = await asyncio.wait_for(
                asyncio.gather(mutate(True), mutate(False)), timeout=15
            )
            assert statuses == ([200, 200] if calculate_first else [409, 200])
            async with engine.begin() as connection:
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
                assert (
                    await connection.scalar(
                        select(Plot.row_version).where(Plot.id == seed_id("plot-1"))
                    )
                    == 2
                )
                snapshot = await connection.scalar(select(CalculationRun.input_snapshot))
                if calculate_first:
                    assert snapshot["plot"]["row_version"] == 1
                    assert snapshot["plot"]["area_m2"] == 100
                else:
                    assert snapshot is None
        finally:
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await engine.dispose()

    asyncio.run(check())
