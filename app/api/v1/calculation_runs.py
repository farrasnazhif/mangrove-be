"""Manager calculation, review, QA notices and publication endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_manager
from app.api.pagination import Pagination, pagination_for
from app.api.v1.field_data import transaction
from app.models import ManagerNotice, Plot, User
from app.schemas.common import Page
from app.schemas.inventory import (
    CalculationDetail,
    CalculationRequest,
    CalculationResponse,
    ManagerNoticeResponse,
    PublicationResponse,
    PublishRequest,
    RunApprovalRequest,
)
from app.services import calculation_runs as service
from app.services.field_data import active

router = APIRouter(tags=["calculations"])
notice_pagination = pagination_for(
    sort_fields={"created_at", "flag"},
    filter_fields={"flag"},
    default_sort="created_at",
)


@router.post(
    "/plots/{plot_id}/calculation-runs", response_model=CalculationResponse, status_code=201
)
async def calculate(
    plot_id: UUID,
    payload: CalculationRequest,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    run = await service.create_run(session, str(plot_id), payload, user.id)
    return service.response(run)


@router.get("/plots/{plot_id}/calculation-runs/{run_id}", response_model=CalculationDetail)
async def get_calculation(
    plot_id: UUID,
    run_id: UUID,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    await active(session, Plot, str(plot_id))
    return service.response(await service.get_run(session, str(plot_id), str(run_id)), detail=True)


@router.post(
    "/plots/{plot_id}/calculation-runs/{run_id}/approve",
    response_model=CalculationResponse,
    status_code=201,
)
async def approve_calculation(
    plot_id: UUID,
    run_id: UUID,
    payload: RunApprovalRequest,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    run = await service.approve_run(
        session, str(plot_id), str(run_id), payload.row_version, user.id
    )
    return service.response(run)


@router.post("/plots/{plot_id}/publish", response_model=PublicationResponse, tags=["publications"])
async def publish(
    plot_id: UUID,
    payload: PublishRequest,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    return await service.publish_run(
        session,
        str(plot_id),
        str(payload.calculation_run_id),
        payload.row_version,
        user.id,
    )


@router.get("/plots/{plot_id}/notices", response_model=Page[ManagerNoticeResponse])
async def notices(
    plot_id: UUID,
    user: User = Depends(require_manager),
    pagination: Pagination = Depends(notice_pagination),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    await active(session, Plot, str(plot_id))
    conditions = [ManagerNotice.plot_id == str(plot_id)]
    conditions.extend(
        getattr(ManagerNotice, key) == value for key, value in pagination.filters.items()
    )
    total = await session.scalar(select(func.count()).select_from(ManagerNotice).where(*conditions))
    records = (
        await session.scalars(
            select(ManagerNotice)
            .where(*conditions)
            .order_by(
                pagination.order_by(
                    {"created_at": ManagerNotice.created_at, "flag": ManagerNotice.flag}
                ),
                ManagerNotice.id,
            )
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
