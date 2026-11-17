from collections.abc import Callable, Mapping

from fastapi import Query, Request
from pydantic import BaseModel, Field

from app.core.errors import APIError
from app.schemas.common import FieldError


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    sort: str
    descending: bool = False
    filters: dict[str, str] = Field(default_factory=dict)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def order_by(self, columns: Mapping):
        """Callers supply ORM columns; never interpolate user input into SQL."""
        column = columns[self.sort]
        return column.desc() if self.descending else column.asc()


def pagination_for(
    *, sort_fields: set[str], filter_fields: set[str], default_sort: str
) -> Callable:
    if default_sort not in sort_fields:
        raise ValueError("Default sort must be allowlisted")

    async def dependency(
        request: Request,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        sort: str = Query(
            default=default_sort,
            max_length=100,
            description=f"Allowed fields: {', '.join(sorted(sort_fields))}. Prefix '-' for descending.",
        ),
        filter: list[str] | None = Query(
            default=None,
            max_length=10,
            description=f"Repeat filter=field:value. Allowed fields: {', '.join(sorted(filter_fields)) or 'none'}.",
        ),
    ) -> Pagination:
        details = []
        unknown = set(request.query_params) - {"page", "page_size", "sort", "filter"}
        if unknown:
            details.append(
                FieldError(
                    field="query", message="Unknown query parameters", type="unknown_parameter"
                )
            )
        field = sort.removeprefix("-")
        if field not in sort_fields:
            details.append(
                FieldError(
                    field="query.sort", message="Sort field is not allowed", type="invalid_sort"
                )
            )
        filters = {}
        for item in filter or []:
            name, separator, value = item.partition(":")
            if (
                not separator
                or name not in filter_fields
                or not value
                or len(value) > 200
                or name in filters
            ):
                details.append(
                    FieldError(
                        field="query.filter",
                        message="Invalid, duplicate or unsupported filter",
                        type="invalid_filter",
                    )
                )
            else:
                filters[name] = value
        if details:
            raise APIError(422, "validation_error", "Invalid pagination, sort or filters", details)
        return Pagination(
            page=page,
            page_size=page_size,
            sort=field,
            descending=sort.startswith("-"),
            filters=filters,
        )

    return dependency


plot_pagination = pagination_for(
    sort_fields={"code", "survey_date", "area_m2"},
    filter_fields={"zone_id", "status", "code"},
    default_sort="code",
)
public_plot_pagination = pagination_for(
    sort_fields={"code", "survey_date"},
    filter_fields={"zone_id", "code"},
    default_sort="code",
)
tree_pagination = pagination_for(
    sort_fields={"id", "dbh_cm"},
    filter_fields={"species_id", "qa_status"},
    default_sort="id",
)
layer_pagination = pagination_for(sort_fields={"id"}, filter_fields=set(), default_sort="id")
