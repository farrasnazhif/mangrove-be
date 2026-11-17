"""Manager field data APIs; photo upload endpoints are in photos.py."""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_manager
from app.api.pagination import Pagination, layer_pagination, plot_pagination, tree_pagination
from app.core.errors import APIError
from app.db.session import get_session
from app.models.inventory import Plot, SedimentCore, SedimentLayer, Tree
from app.models.user import User
from app.schemas.common import FieldError, Page
from app.schemas.inventory import (
    ArchiveResponse,
    CoreCreate,
    CoreResponse,
    CoreUpdate,
    LayerCreate,
    LayerResponse,
    LayerUpdate,
    PlotCreate,
    PlotResponse,
    PlotUpdate,
    TreeCreate,
    TreeResponse,
    TreeUpdate,
)
from app.services import field_data as service

router = APIRouter(tags=["field-data"])


async def transaction(session: AsyncSession = Depends(get_session)) -> AsyncIterator[AsyncSession]:
    try:
        async with session.begin():
            yield session
    except IntegrityError as exc:
        # Do not expose database messages, record IDs or SQL to clients.
        constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
        fields = {
            "plots_code_key": "code",
            "sediment_cores_sample_code_key": "sample_code",
            "ex_layers_overlap": "depth_top_cm",
            "ck_layers_depth": "depth_bottom_cm",
            "ck_layers_mass_volume": "dry_mass_g",
            "ck_trees_density": "wood_density_g_cm3",
        }
        field = fields.get(constraint or "", "record")
        overlap = constraint == "ex_layers_overlap"
        raise APIError(
            422 if overlap else 409,
            "validation_error" if overlap else "data_conflict",
            "Sediment intervals overlap"
            if overlap
            else "Field data conflicts with existing records",
            [FieldError(field=f"body.{field}", message="Conflicting value", type="conflict")],
        ) from exc


@router.get("/plots", response_model=Page[PlotResponse])
async def plots(
    user: User = Depends(require_manager),
    pagination: Pagination = Depends(plot_pagination),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.list_records(session, Plot, pagination)


@router.post("/plots", response_model=PlotResponse, status_code=201)
async def create_plot(
    payload: PlotCreate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.create_plot(session, payload, user.id)


@router.get("/plots/{plot_id}", response_model=PlotResponse)
async def get_plot(
    plot_id: UUID,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.active(session, Plot, str(plot_id))


@router.patch("/plots/{plot_id}", response_model=PlotResponse)
async def update_plot(
    plot_id: UUID,
    payload: PlotUpdate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.update_plot(session, str(plot_id), payload, user.id)


@router.get("/plots/{plot_id}/trees", response_model=Page[TreeResponse])
async def list_trees(
    plot_id: UUID,
    user: User = Depends(require_manager),
    pagination: Pagination = Depends(tree_pagination),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    await service.active(session, Plot, str(plot_id))
    return await service.list_records(session, Tree, pagination, plot_id=str(plot_id))


@router.post("/plots/{plot_id}/trees", response_model=TreeResponse, status_code=201)
async def create_tree(
    plot_id: UUID,
    payload: TreeCreate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.write_child(session, Tree, str(plot_id), payload, user.id)


@router.patch("/plots/{plot_id}/trees/{tree_id}", response_model=TreeResponse)
async def update_tree(
    plot_id: UUID,
    tree_id: UUID,
    payload: TreeUpdate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.write_child(session, Tree, str(plot_id), payload, user.id, str(tree_id))


@router.delete("/plots/{plot_id}/trees/{tree_id}", response_model=ArchiveResponse)
async def archive_tree(
    plot_id: UUID,
    tree_id: UUID,
    row_version: int = Query(ge=1),
    confirm: bool = Query(default=False),
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.archive_child(
        session, Tree, str(plot_id), str(tree_id), row_version, confirm, user.id
    )


@router.get("/plots/{plot_id}/cores", response_model=Page[CoreResponse])
async def list_cores(
    plot_id: UUID,
    user: User = Depends(require_manager),
    pagination: Pagination = Depends(layer_pagination),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    await service.active(session, Plot, str(plot_id))
    return await service.list_records(session, SedimentCore, pagination, plot_id=str(plot_id))


@router.post("/plots/{plot_id}/cores", response_model=CoreResponse, status_code=201)
async def create_core(
    plot_id: UUID,
    payload: CoreCreate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.write_child(session, SedimentCore, str(plot_id), payload, user.id)


@router.patch("/plots/{plot_id}/cores/{core_id}", response_model=CoreResponse)
async def update_core(
    plot_id: UUID,
    core_id: UUID,
    payload: CoreUpdate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.write_child(
        session, SedimentCore, str(plot_id), payload, user.id, str(core_id)
    )


@router.delete("/plots/{plot_id}/cores/{core_id}", response_model=ArchiveResponse)
async def archive_core(
    plot_id: UUID,
    core_id: UUID,
    row_version: int = Query(ge=1),
    confirm: bool = Query(default=False),
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.archive_child(
        session, SedimentCore, str(plot_id), str(core_id), row_version, confirm, user.id
    )


@router.get("/cores/{core_id}/layers", response_model=Page[LayerResponse])
async def list_layers(
    core_id: UUID,
    user: User = Depends(require_manager),
    pagination: Pagination = Depends(layer_pagination),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    core = await service.active(session, SedimentCore, str(core_id))
    await service.active(session, Plot, core.plot_id)
    return await service.list_records(session, SedimentLayer, pagination, core_id=str(core_id))


@router.post("/cores/{core_id}/layers", response_model=LayerResponse, status_code=201)
async def create_layer(
    core_id: UUID,
    payload: LayerCreate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.write_child(session, SedimentLayer, str(core_id), payload, user.id)


@router.patch("/cores/{core_id}/layers/{layer_id}", response_model=LayerResponse)
async def update_layer(
    core_id: UUID,
    layer_id: UUID,
    payload: LayerUpdate,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.write_child(
        session, SedimentLayer, str(core_id), payload, user.id, str(layer_id)
    )


@router.delete("/cores/{core_id}/layers/{layer_id}", response_model=ArchiveResponse)
async def archive_layer(
    core_id: UUID,
    layer_id: UUID,
    row_version: int = Query(ge=1),
    confirm: bool = Query(default=False),
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.archive_child(
        session, SedimentLayer, str(core_id), str(layer_id), row_version, confirm, user.id
    )
