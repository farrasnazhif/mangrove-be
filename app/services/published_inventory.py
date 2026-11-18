"""Public allowlist over the published snapshot, shared by Task 07 consumers.

No HTTP routes are added here. Public plot/map/dashboard handlers must use this
boundary rather than joining live tree measurements or exposing private snapshots.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import HiddenResourceError
from app.models import Attachment, CalculationRun, Plot, Publication, Zone
from app.schemas.common import ContractModel
from app.schemas.inventory import CarbonStock, PublicPlot, PublicPublication
from app.services.calculation_runs import STOCK_FIELDS
from app.services.spatial import inventory_scope_predicate, point


class PublishedTree(ContractModel):
    tree_id: UUID
    species: str
    dbh_cm: float | None
    photo_id: UUID | None


class PublishedInventory(ContractModel):
    plot: PublicPlot
    zone_id: UUID
    trees: list[PublishedTree]


def published_candidates():
    """Base query for public list/legend/count; apply the same filters to all three."""
    return (
        select(CalculationRun, Publication, Zone)
        .join(Publication, Publication.published_run_id == CalculationRun.id)
        .join(Plot, Plot.id == Publication.plot_id)
        .join(Zone, Zone.id == Plot.zone_id)
        .where(
            inventory_scope_predicate(),
            CalculationRun.plot_id == Plot.id,
            CalculationRun.qa_status == "approved",
            CalculationRun.input_snapshot["schema_version"].as_integer() == 1,
            CalculationRun.input_snapshot["plot"]["data_label"].as_string() == "field",
            func.ST_Covers(
                Zone.boundary_geom,
                func.ST_SetSRID(
                    func.ST_MakePoint(
                        CalculationRun.input_snapshot["plot"]["longitude"].as_float(),
                        CalculationRun.input_snapshot["plot"]["latitude"].as_float(),
                    ),
                    4326,
                ),
            ),
        )
    )


async def published_inventory(session: AsyncSession, plot_id: str) -> PublishedInventory:
    row = (await session.execute(published_candidates().where(Plot.id == plot_id))).one_or_none()
    if row is None:
        raise HiddenResourceError()
    run, publication, zone = row
    snapshot = run.input_snapshot
    # Legacy/schema-only runs are not valid public records. No fallback to live draft data.
    if snapshot.get("schema_version") != 1 or snapshot.get("plot", {}).get("data_label") != "field":
        raise HiddenResourceError()
    plot = snapshot["plot"]
    # Re-check the published coordinates as well as current plot scope; a changed
    # study boundary must never expose an old snapshot that is now out of scope.
    if not await session.scalar(
        select(func.ST_Covers(zone.boundary_geom, point(plot["longitude"], plot["latitude"])))
    ):
        raise HiddenResourceError()
    species = {item["id"]: item["scientific_name"] for item in snapshot["species"]}
    photo_ids = {
        item["id"] for item in snapshot.get("photos", []) if item["visibility"] == "public"
    }
    # Both the captured and current visibility must allow public delivery. A private
    # object cannot become public just because a future map handler sees its ID.
    public_photos = set(
        (
            await session.scalars(
                select(Attachment.id).where(
                    Attachment.id.in_(photo_ids),
                    Attachment.visibility == "public",
                    Attachment.entity_type == "plots",
                    Attachment.entity_id == plot_id,
                    Attachment.mime_type == "image/png",
                )
            )
        ).all()
    )
    stock = CarbonStock.model_validate({key: run.result_json[key] for key in STOCK_FIELDS})
    incomplete = bool(run.qa_flags)
    detail = PublicPlot(
        plot_id=run.plot_id,
        plot_code=plot["code"],
        scope=snapshot["zone"]["name"],
        latitude=plot["latitude"],
        longitude=plot["longitude"],
        survey_date=snapshot["survey_date"],
        publication=PublicPublication(
            run_id=run.id,
            method_version=snapshot["method"]["version"],
            published_at=publication.published_at,
        ),
        carbon_stock=stock,
        quality_status="incomplete" if incomplete else "complete",
    )
    return PublishedInventory(
        plot=detail,
        zone_id=plot["zone_id"],
        trees=[
            PublishedTree(
                tree_id=tree["id"],
                species=species[tree["species_id"]],
                dbh_cm=tree["dbh_cm"],
                photo_id=tree["photo_id"] if tree["photo_id"] in public_photos else None,
            )
            for tree in snapshot["trees"]
        ],
    )
