"""Transactional synthetic seed: python -m app.db.seed. Apply migrations first."""

import asyncio
import getpass
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import (
    MethodVersion,
    Plot,
    SedimentCore,
    SedimentLayer,
    Species,
    Tree,
    User,
    UserRole,
    Zone,
)
from app.services.spatial import BoundingBox, assign_plot_scope


def seed_id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"mangrove/task03/synthetic-v1/{key}"))


async def insert_missing(session: AsyncSession, model, key: str, **values):
    existing = await session.get(model, seed_id(key))
    if existing is not None:
        if existing.data_label != "synthetic":
            raise ValueError(f"Seed ID collision with non-synthetic {model.__tablename__}")
        return existing
    record = model(id=seed_id(key), data_label="synthetic", **values)
    session.add(record)
    await session.flush()
    return record


async def seed_dataset(session: AsyncSession, *, email: str, password: str) -> dict[str, int]:
    """Caller owns the transaction; reruns preserve existing data and passwords."""
    if settings.environment not in {"development", "test"}:
        raise ValueError("Synthetic seeding is allowed only in development/test")
    if not settings.boundary_is_synthetic or settings.boundary_approved:
        raise ValueError("Seed requires an unapproved synthetic boundary")
    if not 12 <= len(password.encode()) <= 72:
        raise ValueError("Seed password must contain 12–72 UTF-8 bytes")
    if "@" not in email or len(email) > 254:
        raise ValueError("Provide a valid seed manager email")
    await session.execute(text("SELECT pg_advisory_xact_lock(3003001)"))
    box = BoundingBox.from_settings()
    manager = await session.get(User, seed_id("manager"))
    if manager is not None and (manager.data_label != "synthetic" or manager.email != email):
        raise ValueError("Existing seed manager differs; refusing to overwrite it")
    await insert_missing(
        session,
        User,
        "manager",
        email=email,
        hashed_password=hash_password(password),
        role=UserRole.manager,
        is_active=True,
        session_version=0,
    )
    zone = await insert_missing(
        session,
        Zone,
        "zone",
        name="SYNTHETIC Task 03 demo (not official inventory)",
        boundary_geom=box.polygon(),
        boundary_source=settings.boundary_source,
        boundary_revision=settings.boundary_revision,
        boundary_is_synthetic=True,
        approved_scope=False,
    )
    matches = await session.scalar(select(func.ST_Equals(zone.boundary_geom, box.polygon())))
    if (
        not matches
        or not zone.boundary_is_synthetic
        or zone.approved_scope
        or zone.boundary_source != settings.boundary_source
        or zone.boundary_revision != settings.boundary_revision
    ):
        raise ValueError("Stored seed zone differs from configuration; refusing to rewrite it")
    species = await insert_missing(
        session,
        Species,
        "species",
        scientific_name="SYNTHETIC demo species (not a taxonomic claim)",
    )
    await insert_missing(
        session,
        MethodVersion,
        "method",
        version="synthetic-demo-v1",
        coefficients_json={
            "source": "PRD section 6; not a scientific validation fixture",
            "agb": {"coefficient": 0.251, "dbh_exponent": 2.46},
            "bgb": {"coefficient": 0.199, "density_exponent": 0.899, "dbh_exponent": 2.22},
            "agc_fraction": 0.47,
            "bgc_fraction": 0.39,
            "loi_to_c_divisor": 1.724,
        },
        references=["PRD.md section 6; synthetic demonstration only"],
        approval_status="pending-scientific-approval",
    )
    middle_lon = (box.lon_min + box.lon_max) / 2
    middle_lat = (box.lat_min + box.lat_max) / 2
    outside_lon = box.lon_max + 0.001 if box.lon_max < 179.999 else box.lon_min - 0.001
    if outside_lon < -180:
        raise ValueError("Synthetic box needs room for an outside demonstration point")
    for index, (longitude, latitude) in enumerate(
        [(middle_lon, middle_lat), (box.lon_min, middle_lat), (outside_lon, middle_lat)],
        start=1,
    ):
        plot = await insert_missing(
            session,
            Plot,
            f"plot-{index}",
            code=f"VAK-900{index}",
            zone_id=zone.id,
            area_m2=100.0,
            longitude=longitude,
            latitude=latitude,
            geom=f"SRID=4326;POINT({longitude} {latitude})",
            survey_date=date(2000, 1, 1),
            status="draft",
            row_version=1,
        )
        if plot.row_version == 1:
            await assign_plot_scope(session, plot, zone)
        for tree_index, dbh in enumerate([11.0, 16.0], start=1):
            await insert_missing(
                session,
                Tree,
                f"plot-{index}/tree-{tree_index}",
                plot_id=plot.id,
                species_id=species.id,
                dbh_cm=dbh,
                wood_density_g_cm3=0.6,
                density_source="SYNTHETIC value, not a measured density",
                qa_status="synthetic-unreviewed",
                row_version=1,
            )
        core = await insert_missing(
            session,
            SedimentCore,
            f"plot-{index}/core",
            plot_id=plot.id,
            sample_code=f"SYNTHETIC-VAK-900{index}-C1",
            sample_date=date(2000, 1, 1),
        )
        for layer_index, (top, bottom) in enumerate([(0, 10), (10, 20)], start=1):
            await insert_missing(
                session,
                SedimentLayer,
                f"plot-{index}/layer-{layer_index}",
                core_id=core.id,
                depth_top_cm=top,
                depth_bottom_cm=bottom,
                dry_mass_g=45.0,
                volume_cm3=50.0,
                loi_pct=8.0,
                qa_status="synthetic-unreviewed",
            )
    await session.flush()
    return {
        "zones": 1,
        "managers": 1,
        "plots": 3,
        "trees": 6,
        "cores": 3,
        "layers": 6,
        "methods": 1,
    }


async def main() -> None:
    email = settings.seed_manager_email
    password = (
        settings.seed_manager_password.get_secret_value()
        if settings.seed_manager_password
        else None
    ) or getpass.getpass("Synthetic manager password (12–72 bytes): ")
    try:
        async with SessionLocal() as session, session.begin():
            counts = await seed_dataset(session, email=email, password=password)
        print(f"Synthetic dataset ready: {counts}")
        print("No scientific approval or publication created. Existing passwords preserved.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
