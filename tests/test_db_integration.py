"""Opt-in real PostGIS checks. Every change is enclosed in a rolled-back transaction.

Requires TEST_DATABASE_URL; never falls back to the app's DATABASE_URL.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from app.api.deps import get_optional_session
from app.core.config import settings
from app.core.security import verify_password
from app.db.seed import seed_dataset, seed_id
from app.db.session import get_session
from app.main import app
from app.models import MethodVersion, Plot, SedimentCore, SedimentLayer, Species, Tree, User, Zone
from app.services.spatial import (
    BoundingBox,
    inventory_scope_predicate,
    point,
    require_publishable_scope,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="Set TEST_DATABASE_URL for real PostGIS verification",
    ),
]


def test_migration_seed_scope_and_real_login_logout():
    async def check():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                schema = "task03_test_" + uuid4().hex
                try:
                    await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                    await connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

                    def migrate(sync_connection, direction):
                        config = Config("alembic.ini")
                        config.attributes["connection"] = sync_connection
                        config.attributes["version_table_schema"] = schema
                        if direction == "up":
                            command.upgrade(config, "head")
                        else:
                            command.downgrade(config, "base")

                    await connection.run_sync(migrate, "up")
                    async with AsyncSession(
                        bind=connection,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as session:
                        password = "integration-password-123"
                        email = "manager.synthetic@example.test"
                        await seed_dataset(session, email=email, password=password)
                        await session.commit()
                        manager = await session.get(User, seed_id("manager"))
                        original_hash = manager.hashed_password
                        await seed_dataset(session, email=email, password="different-password-123")
                        await session.commit()
                        await session.refresh(manager)
                        assert manager.hashed_password == original_hash
                        assert verify_password(password, original_hash)
                        for model, expected in [
                            (Zone, 1),
                            (User, 1),
                            (Plot, 3),
                            (Species, 1),
                            (Tree, 6),
                            (SedimentCore, 3),
                            (SedimentLayer, 6),
                            (MethodVersion, 1),
                        ]:
                            assert (
                                await session.scalar(select(func.count()).select_from(model))
                                == expected
                            )
                            assert (
                                await session.scalar(
                                    select(func.count())
                                    .select_from(model)
                                    .where(model.data_label != "synthetic")
                                )
                                == 0
                            )
                        plots = (await session.scalars(select(Plot).order_by(Plot.code))).all()
                        assert [plot.status for plot in plots] == ["draft", "draft", "quarantine"]
                        zone = await session.get(Zone, seed_id("zone"))
                        box = BoundingBox.from_settings()
                        for lon, lat, inside in [
                            (
                                (box.lon_min + box.lon_max) / 2,
                                (box.lat_min + box.lat_max) / 2,
                                True,
                            ),
                            (box.lon_min, box.lat_min, True),
                            (box.lon_max, box.lat_max, True),
                            (plots[2].longitude, plots[2].latitude, False),
                        ]:
                            assert (
                                await session.scalar(
                                    select(func.ST_Covers(zone.boundary_geom, point(lon, lat)))
                                )
                                is inside
                            )
                        visible = await session.scalars(
                            select(Plot).join(Zone).where(inventory_scope_predicate())
                        )
                        assert visible.all() == []
                        for plot in plots:
                            with pytest.raises(ValueError):
                                await require_publishable_scope(session, plot, zone)
                        method = await session.get(MethodVersion, seed_id("method"))
                        assert method.approval_status == "pending-scientific-approval"
                        # Actual DB constraint: an overlapping layer must fail.
                        with pytest.raises(IntegrityError):
                            async with session.begin_nested():
                                session.add(
                                    SedimentLayer(
                                        core_id=seed_id("plot-1/core"),
                                        depth_top_cm=5,
                                        depth_bottom_cm=15,
                                        dry_mass_g=10,
                                        volume_cm3=10,
                                        loi_pct=5,
                                        data_label="synthetic",
                                    )
                                )
                                await session.flush()

                        async def override():
                            yield session

                        app.dependency_overrides[get_session] = override
                        app.dependency_overrides[get_optional_session] = override
                        try:
                            async with AsyncClient(
                                transport=ASGITransport(app=app), base_url="http://testserver"
                            ) as client:
                                csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
                                response = await client.post(
                                    "/api/v1/auth/login",
                                    json={"email": email, "password": password},
                                    headers={"X-CSRF-Token": csrf},
                                )
                                assert response.status_code == 200
                                old_token = client.cookies.get(settings.session_cookie_name)
                                csrf = response.json()["csrf_token"]
                                assert (await client.get("/api/v1/me")).status_code == 200
                                assert (await client.post("/api/v1/auth/logout")).status_code == 403
                                assert (
                                    await client.post(
                                        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}
                                    )
                                ).status_code == 200
                                await session.refresh(manager)
                                assert manager.session_version == 1
                                client.cookies.set(settings.session_cookie_name, old_token)
                                assert (await client.get("/api/v1/me")).status_code == 401
                        finally:
                            app.dependency_overrides.clear()
                    await connection.run_sync(migrate, "down")
                    assert (
                        await connection.scalar(
                            text("SELECT to_regclass(:name)"),
                            {"name": f"{schema}.plots"},
                        )
                        is None
                    )
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(check())
