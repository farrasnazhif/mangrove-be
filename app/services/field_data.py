"""Field mutations serialize on the plot and preserve immutable calculation runs.

Every child mutation increments the plot revision. A run with a different
input_revision is stale; neither old runs nor publication pointers are rewritten.
The caller owns the transaction, including the audit rows.
"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import Pagination
from app.core.errors import APIError, HiddenResourceError
from app.models.inventory import Plot, SedimentCore, SedimentLayer, Species, Tree, Zone, new_id
from app.models.provenance import Attachment
from app.schemas.common import FieldError
from app.schemas.inventory import CoreCreate, LayerCreate, TreeCreate
from app.services.audit import record_change, snapshot
from app.services.spatial import assign_plot_scope


def invalid(field: str, message: str, *, location: str = "body") -> APIError:
    return APIError(
        422,
        "validation_error",
        "Invalid field data",
        [FieldError(field=f"{location}.{field}", message=message, type="invalid_value")],
    )


def values(payload, *, changes=False) -> dict:
    return {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in payload.model_dump(exclude_unset=changes).items()
        if key != "row_version"
    }


async def active(session: AsyncSession, model, record_id: str, *, lock=False):
    query = select(model).where(model.id == record_id)
    if hasattr(model, "archived_at"):
        query = query.where(model.archived_at.is_(None))
    if lock:
        query = query.with_for_update()
    record = await session.scalar(query)
    if record is None:
        raise HiddenResourceError()
    return record


def check_version(record, version: int) -> None:
    if record.row_version != version:
        raise APIError(
            409,
            "version_conflict",
            "Record changed; reload before editing",
            [FieldError(field="row_version", message="Stale version", type="version_conflict")],
        )


async def validate_tree(session: AsyncSession, data: dict, plot: Plot) -> None:
    if await session.get(Species, data["species_id"]) is None:
        raise invalid("species_id", "Species does not exist")
    source = str(data.get("density_source") or "").strip()
    if data.get("wood_density_g_cm3") is not None and source in {"", "not-recorded"}:
        raise invalid("density_source", "Density measurements require a source")
    if data.get("photo_id"):
        attachment = await session.get(Attachment, data["photo_id"])
        # Only an existing photo belonging to this plot
        # may be attached; arbitrary private object IDs cannot be reused.
        if (
            attachment is None
            or attachment.entity_type != "plots"
            or attachment.entity_id != plot.id
            or attachment.mime_type not in {"image/jpeg", "image/png", "image/webp"}
        ):
            raise invalid("photo_id", "Photo does not belong to the selected plot")


def validate_merged(schema, data: dict) -> dict:
    try:
        return values(schema.model_validate(data))
    except ValidationError as exc:
        raise APIError(
            422,
            "validation_error",
            "Invalid field data",
            [
                FieldError(
                    field="body." + ".".join(map(str, error["loc"])),
                    message="Invalid value",
                    type=error["type"],
                )
                for error in exc.errors()
            ],
        ) from exc


async def create_plot(session: AsyncSession, payload, actor_id: str):
    data = values(payload)
    zone = await session.get(Zone, data["zone_id"])
    if zone is None:
        raise invalid("zone_id", "Zone does not exist")
    record = Plot(**data, id=new_id(), data_label="field", row_version=1)
    await assign_plot_scope(session, record, zone)
    session.add(record)
    record_change(session, actor_id=actor_id, record=record, action="create", before={})
    await session.flush()
    return record


async def update_plot(session: AsyncSession, plot_id: str, payload, actor_id: str):
    record = await active(session, Plot, plot_id, lock=True)
    check_version(record, payload.row_version)
    before = snapshot(record)
    # Load before changing coordinates: session.get can autoflush, and the DB
    # requires geom and latitude/longitude to agree in every persisted revision.
    zone = await session.get(Zone, record.zone_id)
    if zone is None:
        raise invalid("zone_id", "Zone does not exist")
    for key, value in values(payload, changes=True).items():
        setattr(record, key, value)
    await assign_plot_scope(session, record, zone)
    record.row_version += 1
    record_change(session, actor_id=actor_id, record=record, action="update", before=before)
    await session.flush()
    return record


async def child_context(session: AsyncSession, model, parent_id: str, child_id: str | None):
    # Lock order is always plot -> core -> child, across every mutation.
    if model is SedimentLayer:
        core = await active(session, SedimentCore, parent_id)
        plot = await active(session, Plot, core.plot_id, lock=True)
        core = await active(session, SedimentCore, parent_id, lock=True)
        if core.plot_id != plot.id:
            raise HiddenResourceError()
        parent_field = "core_id"
    else:
        plot = await active(session, Plot, parent_id, lock=True)
        parent_field = "plot_id"
    child = None
    if child_id:
        child = await active(session, model, child_id, lock=True)
        if getattr(child, parent_field) != parent_id:
            raise HiddenResourceError()
    return plot, child, parent_field


async def touch_plot(session: AsyncSession, plot: Plot, actor_id: str):
    before = snapshot(plot)
    plot.row_version += 1
    record_change(
        session, actor_id=actor_id, record=plot, action="invalidate-calculations", before=before
    )


async def write_child(
    session: AsyncSession,
    model,
    parent_id: str,
    payload,
    actor_id: str,
    child_id: str | None = None,
):
    plot, record, parent_field = await child_context(session, model, parent_id, child_id)
    schemas: dict[type, type[BaseModel]] = {
        Tree: TreeCreate,
        SedimentCore: CoreCreate,
        SedimentLayer: LayerCreate,
    }
    schema = schemas[model]
    before = snapshot(record) if record is not None else {}
    if record is not None:
        check_version(record, payload.row_version)
        data = {field: getattr(record, field) for field in schema.model_fields}
        data.update(values(payload, changes=True))
        data = validate_merged(schema, data)
    else:
        data = values(payload)
    if model is Tree:
        await validate_tree(session, data, plot)
        # DB requires a non-null source; unknown density is explicitly labelled.
        data["density_source"] = data.get("density_source") or "not-recorded"
    if record is None:
        record = model(
            **data,
            **{parent_field: parent_id},
            id=new_id(),
            data_label=plot.data_label,
            row_version=1,
        )
        if model in {Tree, SedimentLayer}:
            record.qa_status = "unreviewed"
        session.add(record)
    else:
        for key, value in data.items():
            setattr(record, key, value)
        record.row_version += 1
        if model in {Tree, SedimentLayer}:
            record.qa_status = "unreviewed"
    await touch_plot(session, plot, actor_id)
    record_change(
        session,
        actor_id=actor_id,
        record=record,
        action="update" if child_id else "create",
        before=before,
    )
    await session.flush()
    return record


async def archive_child(
    session: AsyncSession,
    model,
    parent_id: str,
    child_id: str,
    version: int,
    confirm: bool,
    actor_id: str,
):
    if not confirm:
        raise invalid("confirm", "Explicit confirmation is required", location="query")
    plot, record, _ = await child_context(session, model, parent_id, child_id)
    check_version(record, version)
    before = snapshot(record)
    record.archived_at = datetime.now(UTC)
    record.row_version += 1
    record_change(session, actor_id=actor_id, record=record, action="archive", before=before)
    await touch_plot(session, plot, actor_id)
    await session.flush()
    return record


async def list_records(session: AsyncSession, model, pagination: Pagination, **parents):
    conditions = [model.archived_at.is_(None)]
    for key, value in {**parents, **pagination.filters}.items():
        if key.endswith("_id"):
            try:
                value = str(UUID(value))
            except ValueError as exc:
                raise invalid("filter", "Invalid UUID filter", location="query") from exc
        conditions.append(getattr(model, key) == value)
    total = await session.scalar(select(func.count()).select_from(model).where(*conditions))
    columns = {field: getattr(model, field) for field in {pagination.sort, "id"}}
    records = (
        await session.scalars(
            select(model)
            .where(*conditions)
            .order_by(pagination.order_by(columns), model.id)
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).all()
    return {
        "items": records,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total": total,
    }
