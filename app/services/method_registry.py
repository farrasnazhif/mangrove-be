"""Database adapter for immutable method versions; caller owns the transaction."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calc.methods import Method
from app.models import MethodVersion


def method_from_record(record: MethodVersion) -> Method:
    return Method.from_dict(
        {
            "version": record.version,
            "references": record.references,
            "coefficients_json": record.coefficients_json,
            "approval_status": record.approval_status,
            "effective_date": record.effective_date.isoformat() if record.effective_date else None,
            "rounding_rule": record.rounding_rule,
        }
    )


async def load_method(session: AsyncSession, method_version_id: str) -> Method:
    record = await session.get(MethodVersion, method_version_id)
    if record is None:
        raise ValueError("Unknown method version")
    return method_from_record(record)


async def register_method(
    session: AsyncSession, method: Method, *, data_label: str
) -> MethodVersion:
    """Insert only; coefficient/approval changes require a new version and row.

    Approval authorization belongs to the calling service. The existing DB trigger
    protects rows against updates/deletes; UNIQUE(version) also handles racing inserts.
    """
    if data_label not in {"synthetic", "field"}:
        raise ValueError("Invalid method data label")
    existing = await session.scalar(
        select(MethodVersion.id).where(MethodVersion.version == method.version)
    )
    if existing is not None:
        raise ValueError("Method version already exists; create a new version")
    snapshot = method.to_dict()
    record = MethodVersion(
        version=method.version,
        coefficients_json=snapshot["coefficients_json"],
        references=snapshot["references"],
        approval_status=method.approval_status,
        effective_date=method.effective_date,
        approved_at=datetime.now(UTC) if method.approval_status == "approved" else None,
        rounding_rule=snapshot["rounding_rule"],
        data_label=data_label,
    )
    session.add(record)
    await session.flush()
    return record
