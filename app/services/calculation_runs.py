"""Immutable input snapshots, manager review and atomic publication.

Serialize against field mutations on the plot lock. The caller owns the transaction.
Approval inserts a reviewed copy, never updates an immutable calculation run.
"""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calc.engine import LayerInput, TreeInput, calculate_plot
from app.core.errors import APIError, HiddenResourceError
from app.models import (
    Attachment,
    AuditEvent,
    CalculationRun,
    ManagerNotice,
    MethodVersion,
    Plot,
    Publication,
    SedimentCore,
    SedimentLayer,
    Species,
    Tree,
    Zone,
)
from app.models.inventory import new_id
from app.schemas.inventory import CalculationRequest
from app.services.field_data import active, check_version, invalid
from app.services.method_registry import method_from_record
from app.services.spatial import require_publishable_scope

STOCK_FIELDS = ("agc_mg_c_ha", "bgc_mg_c_ha", "soc_mg_c_ha", "total_mg_c_ha", "co2e_mg_ha")
BIOMASS_FLAGS = {"missing-sediment", "unknown-profile-depth", "missing-sediment-layer"}
NOTICE_ACTIONS = {
    "missing-density": "Record wood density and its source, then calculate a new run.",
    "outside-approved-scope": "Correct coordinates or obtain an approved study boundary.",
    "synthetic-input": "Use reviewed field data and a field method before publication.",
    "method-not-approved": "Select a scientifically approved, effective method version.",
    "multi-core-policy-required": "Obtain an approved multi-core aggregation policy.",
    "missing-tree-inventory": "Record the tree inventory before publication.",
}


def input_hash(snapshot: dict) -> str:
    data = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def audit(session, actor_id: str, run: CalculationRun, action: str, **details) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            entity_type="calculation_runs",
            entity_id=run.id,
            action=action,
            change_summary={"plot_id": run.plot_id, "input_hash": run.input_hash, **details},
        )
    )


async def zone_for(session: AsyncSession, plot: Plot) -> Zone:
    # Shared zone lock keeps scope approval stable throughout calculation/publication.
    zone = await session.scalar(
        select(Zone).where(Zone.id == plot.zone_id).with_for_update(read=True)
    )
    if zone is None:
        raise HiddenResourceError()
    return zone


def method_approved(method: MethodVersion) -> bool:
    return bool(
        method.approval_status == "approved"
        and method.approved_at
        and method.effective_date
        and method.effective_date <= datetime.now(UTC).date()
    )


async def get_run(session: AsyncSession, plot_id: str, run_id: str) -> CalculationRun:
    run = await session.get(CalculationRun, run_id)
    if run is None or run.plot_id != plot_id:
        raise HiddenResourceError()
    return run


def response(run: CalculationRun, *, detail=False) -> dict:
    result = {
        field: getattr(run, field)
        for field in (
            "id",
            "plot_id",
            "method_version_id",
            "input_revision",
            "input_hash",
            "qa_flags",
            "qa_status",
            "created_at",
        )
    }
    result["carbon_stock"] = {field: run.result_json[field] for field in STOCK_FIELDS}
    if detail:
        result.update(input_snapshot=run.input_snapshot, result_json=run.result_json)
    return result


async def create_run(
    session: AsyncSession,
    plot_id: str,
    payload: CalculationRequest,
    actor_id: str,
) -> CalculationRun:
    plot = await active(session, Plot, plot_id, lock=True)
    check_version(plot, payload.input_revision)
    zone = await zone_for(session, plot)
    method = await session.get(MethodVersion, str(payload.method_version_id))
    if method is None:
        raise invalid("method_version_id", "Method version does not exist")
    trees = (
        await session.scalars(
            select(Tree)
            .where(
                Tree.plot_id == plot_id,
                Tree.archived_at.is_(None),
            )
            .order_by(Tree.id)
        )
    ).all()
    species = (
        await session.scalars(
            select(Species)
            .where(Species.id.in_([tree.species_id for tree in trees]))
            .order_by(Species.id)
            .with_for_update(read=True)
        )
    ).all()
    cores = (
        await session.scalars(
            select(SedimentCore)
            .where(
                SedimentCore.plot_id == plot_id,
                SedimentCore.archived_at.is_(None),
            )
            .order_by(SedimentCore.id)
        )
    ).all()
    layers = (
        await session.scalars(
            select(SedimentLayer)
            .where(
                SedimentLayer.core_id.in_([core.id for core in cores]),
                SedimentLayer.archived_at.is_(None),
            )
            .order_by(SedimentLayer.core_id, SedimentLayer.depth_top_cm, SedimentLayer.id)
        )
    ).all()
    photos = (
        await session.scalars(
            select(Attachment)
            .where(
                Attachment.id.in_([tree.photo_id for tree in trees if tree.photo_id]),
                Attachment.entity_type == "plots",
                Attachment.entity_id == plot.id,
                Attachment.mime_type == "image/png",
            )
            .order_by(Attachment.id)
            .with_for_update(read=True)
        )
    ).all()
    try:
        method_value = method_from_record(method)
    except ValueError as exc:
        raise invalid(
            "method_version_id", "Method version is not supported by the calculation engine"
        ) from exc
    snapshot = {
        "schema_version": 1,
        "plot": {
            key: getattr(plot, key)
            for key in (
                "id",
                "code",
                "zone_id",
                "area_m2",
                "latitude",
                "longitude",
                "row_version",
                "data_label",
            )
        },
        "survey_date": plot.survey_date.isoformat(),
        "zone": {
            key: getattr(zone, key)
            for key in (
                "id",
                "name",
                "boundary_source",
                "boundary_revision",
                "boundary_is_synthetic",
                "approved_scope",
                "data_label",
            )
        },
        "boundary_ewkt": await session.scalar(select(func.ST_AsEWKT(zone.boundary_geom))),
        "method_version_id": method.id,
        "method": method_value.to_dict(),
        "method_data_label": method.data_label,
        "photos": [
            {"id": photo.id, "visibility": photo.visibility, "mime_type": photo.mime_type}
            for photo in photos
        ],
        "species": [
            {
                key: getattr(record, key)
                for key in (
                    "id",
                    "scientific_name",
                    "display_name",
                    "default_density",
                    "density_source",
                    "density_version",
                    "data_label",
                )
            }
            for record in species
        ],
        "expected_bottom_cm": payload.expected_bottom_cm,
        "trees": [
            {
                key: getattr(tree, key)
                for key in (
                    "id",
                    "row_version",
                    "species_id",
                    "dbh_cm",
                    "wood_density_g_cm3",
                    "density_source",
                    "qa_status",
                    "data_label",
                    "height_m",
                    "photo_id",
                    "source_import_id",
                    "source_row_id",
                )
            }
            for tree in trees
        ],
        "cores": [
            {
                "id": core.id,
                "row_version": core.row_version,
                "sample_code": core.sample_code,
                "sample_date": core.sample_date.isoformat(),
                "data_label": core.data_label,
            }
            for core in cores
        ],
        "layers": [
            {
                key: getattr(layer, key)
                for key in (
                    "id",
                    "core_id",
                    "row_version",
                    "depth_top_cm",
                    "depth_bottom_cm",
                    "dry_mass_g",
                    "volume_cm3",
                    "loi_pct",
                    "qa_status",
                    "data_label",
                )
            }
            for layer in layers
        ],
    }
    try:
        calculated = calculate_plot(
            [TreeInput(t.dbh_cm, t.wood_density_g_cm3, t.species_id) for t in trees],
            [
                LayerInput(l.depth_top_cm, l.depth_bottom_cm, l.dry_mass_g, l.volume_cm3, l.loi_pct)
                for l in layers
            ]
            if len(cores) <= 1
            else [],
            plot.area_m2,
            method_value,
            expected_bottom_cm=payload.expected_bottom_cm,
        )
    except ValueError as exc:
        raise invalid("input", str(exc)) from exc
    flags = set(calculated.flags)
    if len(cores) > 1:
        flags.difference_update(BIOMASS_FLAGS)
        flags.add("multi-core-policy-required")
    if any(
        record.data_label != "field"
        for record in [plot, zone, method, *species, *trees, *cores, *layers]
    ):
        flags.add("synthetic-input")
    if not method_approved(method):
        flags.add("method-not-approved")
    try:
        await require_publishable_scope(session, plot, zone)
    except ValueError:
        flags.add("outside-approved-scope")
    result = asdict(calculated)
    result["flags"] = sorted(flags)
    # JSON round-trip normalizes tuples so replay compares with persisted JSON exactly.
    result = json.loads(json.dumps(result, allow_nan=False))
    run = CalculationRun(
        id=new_id(),
        plot_id=plot_id,
        method_version_id=method.id,
        input_revision=plot.row_version,
        input_hash=input_hash(snapshot),
        input_snapshot=snapshot,
        result_json=result,
        qa_flags=sorted(flags),
        qa_status="draft",
    )
    session.add(run)
    await session.flush()
    audit(session, actor_id, run, "calculate")
    for flag in sorted(flags):
        session.add(
            ManagerNotice(
                plot_id=plot_id,
                calculation_run_id=run.id,
                plot_code=plot.code,
                flag=flag,
                message=f"{plot.code}: {flag}",
                suggested_action=NOTICE_ACTIONS.get(
                    flag, "Review sediment completeness and sampling depth; calculate a new run."
                ),
            )
        )
    await session.flush()
    return run


def publication_kind(run: CalculationRun) -> str:
    flags = set(run.qa_flags)
    if not flags and run.result_json["total_mg_c_ha"] is not None:
        return "complete"
    # D5 permits no-sediment biomass, not partially measured or ambiguous multi-core SOC.
    if (
        flags
        and flags <= BIOMASS_FLAGS
        and not run.input_snapshot["cores"]
        and run.result_json["agc_mg_c_ha"] is not None
        and run.result_json["bgc_mg_c_ha"] is not None
        and all(
            run.result_json[key] is None for key in ("soc_mg_c_ha", "total_mg_c_ha", "co2e_mg_ha")
        )
    ):
        return "biomass-only"
    raise APIError(
        409, "run_not_publishable", "Resolve calculation quality flags before approval/publication"
    )


async def validate_review(session: AsyncSession, plot: Plot, run: CalculationRun) -> MethodVersion:
    check_version(plot, run.input_revision)
    zone = await zone_for(session, plot)
    try:
        await require_publishable_scope(session, plot, zone)
    except ValueError as exc:
        raise APIError(409, "scope_not_publishable", str(exc)) from exc
    if (
        any(getattr(zone, key) != value for key, value in run.input_snapshot["zone"].items())
        or await session.scalar(select(func.ST_AsEWKT(zone.boundary_geom)))
        != run.input_snapshot["boundary_ewkt"]
    ):
        raise APIError(409, "scope_revision_changed", "Study boundary changed; calculate a new run")
    method = await session.get(MethodVersion, run.method_version_id)
    if method is None or not method_approved(method) or method.data_label != "field":
        raise APIError(
            409, "method_not_approved", "Publication requires an approved, effective field method"
        )
    if input_hash(run.input_snapshot) != run.input_hash:
        raise APIError(409, "snapshot_mismatch", "Calculation input integrity check failed")
    publication_kind(run)
    return method


async def approve_run(
    session: AsyncSession, plot_id: str, run_id: str, version: int, actor_id: str
):
    plot = await active(session, Plot, plot_id, lock=True)
    check_version(plot, version)
    source = await get_run(session, plot_id, run_id)
    if source.qa_status != "draft":
        raise APIError(409, "run_not_draft", "Only draft runs can be reviewed")
    await validate_review(session, plot, source)
    approved = CalculationRun(
        id=new_id(),
        plot_id=plot_id,
        method_version_id=source.method_version_id,
        input_revision=source.input_revision,
        input_hash=source.input_hash,
        input_snapshot=deepcopy(source.input_snapshot),
        result_json=deepcopy(source.result_json),
        qa_flags=list(source.qa_flags),
        qa_status="approved",
    )
    session.add(approved)
    await session.flush()
    audit(session, actor_id, approved, "approve", source_run_id=source.id)
    await session.flush()
    return approved


async def publish_run(
    session: AsyncSession, plot_id: str, run_id: str, version: int, actor_id: str
):
    plot = await active(session, Plot, plot_id, lock=True)
    check_version(plot, version)
    run = await get_run(session, plot_id, run_id)
    if run.qa_status != "approved":
        raise APIError(409, "run_not_approved", "Review and approve the calculation run first")
    method = await validate_review(session, plot, run)
    publication = await session.get(Publication, plot_id)
    previous = publication.published_run_id if publication else None
    now = datetime.now(UTC)
    if publication is None:
        publication = Publication(
            plot_id=plot_id, published_run_id=run.id, approved_by=actor_id, published_at=now
        )
        session.add(publication)
    else:
        publication.published_run_id = run.id
        publication.approved_by = actor_id
        publication.published_at = now
    # Publication changes also participate in optimistic concurrency.
    plot.row_version += 1
    audit(session, actor_id, run, "publish", previous_run_id=previous, row_version=plot.row_version)
    await session.flush()
    return {
        "plot_id": plot_id,
        "published_run_id": run.id,
        "method_version": method.version,
        "published_at": publication.published_at,
        "incomplete": publication_kind(run) != "complete",
    }


async def published_run(session: AsyncSession, plot_id: str) -> CalculationRun:
    """Shared pointer resolution for future dashboard/map/export/chatbot consumers.

    Access and public scope checks belong to each consumer. Never fall back to latest draft.
    """
    publication = await session.get(Publication, plot_id)
    if publication is None:
        raise HiddenResourceError()
    return await get_run(session, plot_id, publication.published_run_id)
