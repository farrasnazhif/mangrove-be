"""Executable wire contracts for P0 features scheduled in later backlog tasks.

All routes enforce access and input validation, then return 501. Replace individual
handlers as features land; keep their schemas and update the reviewed OpenAPI snapshot.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import optional_user, require_manager, verify_csrf
from app.api.pagination import (
    Pagination,
    layer_pagination,
    plot_pagination,
    public_plot_pagination,
    tree_pagination,
)
from app.core.errors import APIError
from app.schemas.common import Page
from app.schemas.inventory import (
    CalculationRequest,
    CalculationResponse,
    ChatRequest,
    ChatResponse,
    CoreCreate,
    CoreResponse,
    DBHRecap,
    ExportRequest,
    ExportResponse,
    ImportRequest,
    ImportResponse,
    LayerCreate,
    LayerResponse,
    MapLayer,
    PlotCreate,
    PlotResponse,
    PlotUpdate,
    PublicationResponse,
    PublicMapPlot,
    PublicPlot,
    PublishRequest,
    TreeCreate,
    TreeResponse,
)

router = APIRouter()
PLANNED = {"x-implementation-status": "planned"}
DESCRIPTION = (
    "Contract only. Feature is scheduled in a later backlog task; validated requests return 501."
)


def unavailable() -> None:
    raise APIError(501, "not_implemented", "This feature is not implemented yet")


@router.get(
    "/public/plots",
    response_model=Page[PublicPlot],
    tags=["public"],
    dependencies=[Depends(optional_user)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def public_plots(pagination: Pagination = Depends(public_plot_pagination)):
    unavailable()


@router.get(
    "/public/plots/{plot_id}",
    response_model=PublicPlot,
    tags=["public"],
    dependencies=[Depends(optional_user)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def public_plot(plot_id: UUID):
    unavailable()


@router.get(
    "/plots",
    response_model=Page[PlotResponse],
    tags=["plots"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def plots(pagination: Pagination = Depends(plot_pagination)):
    unavailable()


@router.post(
    "/plots",
    response_model=PlotResponse,
    status_code=201,
    tags=["plots"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def create_plot(payload: PlotCreate):
    unavailable()


@router.patch(
    "/plots/{plot_id}",
    response_model=PlotResponse,
    tags=["plots"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def update_plot(plot_id: UUID, payload: PlotUpdate):
    unavailable()


@router.get(
    "/plots/{plot_id}/trees",
    response_model=Page[TreeResponse],
    tags=["trees"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def trees(plot_id: UUID, pagination: Pagination = Depends(tree_pagination)):
    unavailable()


@router.post(
    "/plots/{plot_id}/trees",
    response_model=TreeResponse,
    status_code=201,
    tags=["trees"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def create_tree(plot_id: UUID, payload: TreeCreate):
    unavailable()


@router.post(
    "/plots/{plot_id}/cores",
    response_model=CoreResponse,
    status_code=201,
    tags=["sediment"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def create_core(plot_id: UUID, payload: CoreCreate):
    unavailable()


@router.post(
    "/cores/{core_id}/layers",
    response_model=LayerResponse,
    status_code=201,
    tags=["sediment"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def create_layer(core_id: UUID, payload: LayerCreate):
    unavailable()


@router.post(
    "/plots/{plot_id}/calculation-runs",
    response_model=CalculationResponse,
    status_code=201,
    tags=["calculations"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def calculate(plot_id: UUID, payload: CalculationRequest):
    unavailable()


@router.post(
    "/plots/{plot_id}/publish",
    response_model=PublicationResponse,
    tags=["publications"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def publish(plot_id: UUID, payload: PublishRequest):
    unavailable()


@router.post(
    "/reports/exports",
    response_model=ExportResponse,
    status_code=202,
    tags=["reports"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def export(payload: ExportRequest):
    unavailable()


@router.get(
    "/reports/exports/{export_id}",
    response_model=ExportResponse,
    tags=["reports"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def export_status(export_id: UUID):
    unavailable()


@router.post(
    "/chat/messages",
    response_model=ChatResponse,
    tags=["chat"],
    dependencies=[Depends(optional_user), Depends(verify_csrf)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def chat(payload: ChatRequest):
    unavailable()


@router.get(
    "/public/map/plots",
    response_model=Page[PublicMapPlot],
    tags=["public"],
    dependencies=[Depends(optional_user)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def map_plots(pagination: Pagination = Depends(public_plot_pagination)):
    unavailable()


@router.get(
    "/map/layers",
    response_model=Page[MapLayer],
    tags=["map"],
    dependencies=[Depends(optional_user)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def map_layers(pagination: Pagination = Depends(layer_pagination)):
    unavailable()


@router.post(
    "/dbh-imports",
    response_model=ImportResponse,
    status_code=202,
    tags=["imports"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def import_dbh(payload: ImportRequest):
    unavailable()


@router.get(
    "/plots/{plot_id}/dbh-recap",
    response_model=DBHRecap,
    tags=["reports"],
    dependencies=[Depends(require_manager)],
    description=DESCRIPTION,
    openapi_extra=PLANNED,
)
async def dbh_recap(plot_id: UUID):
    unavailable()
