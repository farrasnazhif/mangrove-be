"""Append audit rows in the caller's transaction; never commit independently."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import AuditEvent

AUDITED_FIELDS = frozenset(
    {
        "code",
        "zone_id",
        "area_m2",
        "latitude",
        "longitude",
        "survey_date",
        "status",
        "scope_reason",
        "row_version",
        "data_label",
        "plot_id",
        "species_id",
        "dbh_cm",
        "wood_density_g_cm3",
        "density_source",
        "height_m",
        "photo_id",
        "qa_status",
        "sample_code",
        "sample_date",
        "core_id",
        "depth_top_cm",
        "depth_bottom_cm",
        "dry_mass_g",
        "volume_cm3",
        "loi_pct",
        "archived_at",
        "entity_type",
        "entity_id",
        "mime_type",
        "size_bytes",
        "visibility",
    }
)


def snapshot(record) -> dict:
    result = {}
    for field in AUDITED_FIELDS:
        if hasattr(record, field):
            value = getattr(record, field)
            if isinstance(value, (date, datetime)):
                value = value.isoformat()
            elif isinstance(value, UUID):
                value = str(value)
            result[field] = value
    return result


def record_change(
    session: AsyncSession, *, actor_id: str, record, action: str, before: dict
) -> None:
    after = snapshot(record)
    changes = {
        field: {"before": before.get(field), "after": value}
        for field, value in after.items()
        if field not in before or before[field] != value
    }
    session.add(
        AuditEvent(
            actor_id=actor_id,
            entity_type=record.__tablename__,
            entity_id=record.id,
            action=action,
            change_summary={"fields": changes},
        )
    )
