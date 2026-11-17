"""P0 wire contracts. These DTOs do not imply that the feature is implemented."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, HttpUrl, ValidationInfo, field_validator, model_validator

from app.schemas.common import ContractModel


class PlotCreate(ContractModel):
    zone_id: UUID
    code: str = Field(pattern=r"^VAK-[0-9]+$", max_length=50)
    area_m2: float = Field(gt=0)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    survey_date: date


class PlotUpdate(ContractModel):
    row_version: int = Field(ge=1)
    code: str | None = Field(default=None, pattern=r"^VAK-[0-9]+$", max_length=50)
    area_m2: float | None = Field(default=None, gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    survey_date: date | None = None

    @model_validator(mode="after")
    def require_changes(self) -> "PlotUpdate":
        changes = self.model_fields_set - {"row_version"}
        if not changes or any(getattr(self, field) is None for field in changes):
            raise ValueError("Provide at least one non-null field to update")
        return self


class PlotResponse(PlotCreate):
    id: UUID
    status: Literal["draft", "quarantine", "reviewed", "published", "archived"]
    scope_reason: str | None
    row_version: int = Field(ge=1)
    data_label: Literal["synthetic", "field"]


class TreeCreate(ContractModel):
    species_id: UUID
    dbh_cm: float = Field(gt=0)
    wood_density_g_cm3: float | None = Field(default=None, gt=0, le=2)
    density_source: str | None = Field(default=None, max_length=200)
    height_m: float | None = Field(default=None, gt=0)
    photo_id: UUID | None = None


class TreeResponse(TreeCreate):
    id: UUID
    plot_id: UUID
    qa_status: str
    row_version: int = Field(ge=1)


class CoreCreate(ContractModel):
    sample_code: str = Field(min_length=1, max_length=100)
    sample_date: date


class CoreResponse(CoreCreate):
    id: UUID
    plot_id: UUID
    row_version: int = Field(ge=1)


class LayerCreate(ContractModel):
    depth_top_cm: float = Field(ge=0)
    depth_bottom_cm: float = Field(gt=0)
    dry_mass_g: float = Field(gt=0)
    volume_cm3: float = Field(gt=0)
    loi_pct: float = Field(ge=0, le=100)

    @field_validator("depth_bottom_cm")
    @classmethod
    def ordered_depths(cls, value: float, info: ValidationInfo) -> float:
        if value <= info.data.get("depth_top_cm", 0):
            raise ValueError("Bottom depth must exceed top depth")
        return value


class LayerResponse(LayerCreate):
    id: UUID
    core_id: UUID
    qa_status: str
    row_version: int = Field(ge=1)


class FieldUpdate(ContractModel):
    row_version: int = Field(ge=1)

    @model_validator(mode="after")
    def require_changes(self) -> "FieldUpdate":
        if not self.model_fields_set - {"row_version"}:
            raise ValueError("Provide at least one field to update")
        return self


class TreeUpdate(FieldUpdate):
    species_id: UUID | None = None
    dbh_cm: float | None = Field(default=None, gt=0)
    wood_density_g_cm3: float | None = Field(default=None, gt=0, le=2)
    density_source: str | None = Field(default=None, max_length=200)
    height_m: float | None = Field(default=None, gt=0)
    photo_id: UUID | None = None


class CoreUpdate(FieldUpdate):
    sample_code: str | None = Field(default=None, min_length=1, max_length=100)
    sample_date: date | None = None


class LayerUpdate(FieldUpdate):
    depth_top_cm: float | None = Field(default=None, ge=0)
    depth_bottom_cm: float | None = Field(default=None, gt=0)
    dry_mass_g: float | None = Field(default=None, gt=0)
    volume_cm3: float | None = Field(default=None, gt=0)
    loi_pct: float | None = Field(default=None, ge=0, le=100)


class ArchiveResponse(ContractModel):
    id: UUID
    archived_at: AwareDatetime
    row_version: int = Field(ge=1)


class CarbonStock(ContractModel):
    """All stock units are Mg C/ha; CO2e uses Mg CO2e/ha. Missing is null."""

    agc_mg_c_ha: float | None
    bgc_mg_c_ha: float | None
    soc_mg_c_ha: float | None
    total_mg_c_ha: float | None
    co2e_mg_ha: float | None


class CalculationRequest(ContractModel):
    method_version_id: UUID
    input_revision: int = Field(ge=1)


class CalculationResponse(ContractModel):
    id: UUID
    plot_id: UUID
    method_version_id: UUID
    input_revision: int = Field(ge=1)
    input_hash: str
    carbon_stock: CarbonStock
    qa_flags: list[str]
    qa_status: Literal["draft", "incomplete", "approved", "rejected"]
    created_at: AwareDatetime


class PublishRequest(ContractModel):
    calculation_run_id: UUID
    row_version: int = Field(ge=1)


class PublicationResponse(ContractModel):
    plot_id: UUID
    published_run_id: UUID
    method_version: str
    published_at: AwareDatetime
    incomplete: bool


class PublicPublication(ContractModel):
    run_id: UUID
    method_version: str
    published_at: AwareDatetime


class PublicPlot(ContractModel):
    """Public allowlist: no researcher identity, QA reviewer or private attachments."""

    plot_id: UUID
    plot_code: str
    scope: str
    latitude: float
    longitude: float
    survey_date: date
    publication: PublicPublication
    carbon_stock: CarbonStock
    quality_status: str


class PublicMapPlot(ContractModel):
    plot_id: UUID
    plot_code: str
    zone_id: UUID
    latitude: float
    longitude: float
    species: list[str]
    dbh_cm: list[float | None]
    photo_url: HttpUrl | None
    last_survey_date: date


class MapLayer(ContractModel):
    id: str
    name: str
    provider: str
    available: bool
    imagery_date: date | None
    attribution: str
    fallback: bool


class ExportFilters(ContractModel):
    zone_id: UUID | None = None
    plot_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    survey_date_from: date | None = None
    survey_date_to: date | None = None

    @model_validator(mode="after")
    def date_order(self) -> "ExportFilters":
        if (
            self.survey_date_from
            and self.survey_date_to
            and self.survey_date_from > self.survey_date_to
        ):
            raise ValueError("Start date must not exceed end date")
        return self


class ExportRequest(ContractModel):
    format: Literal["xlsx"] = "xlsx"
    include_drafts: bool = False
    filters: ExportFilters = Field(default_factory=ExportFilters)


class ExportResponse(ContractModel):
    id: UUID
    status: Literal["queued", "processing", "completed", "failed"]
    created_at: AwareDatetime
    download_url: HttpUrl | None
    expires_at: AwareDatetime | None


class ImportRequest(ContractModel):
    drive_file_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    source_revision: str | None = Field(default=None, max_length=200)


class ImportResponse(ContractModel):
    id: UUID
    status: Literal["pending", "validated", "needs_review", "completed", "quarantined", "failed"]
    source_drive_file_id: str
    source_revision: str | None
    accepted_rows: int = Field(ge=0)
    quarantined_rows: int = Field(ge=0)
    created_at: AwareDatetime


class TreeRecap(ContractModel):
    tree_id: UUID
    dbh_cm: float
    wood_density_g_cm3: float | None
    density_source: str | None
    agb_kg: float | None
    bgb_kg: float | None
    agc_kg: float | None
    bgc_kg: float | None
    qa_flags: list[str]


class DBHRecap(ContractModel):
    plot_id: UUID
    plot_code: str
    method_version: str
    coefficients: dict[str, float]
    trees: list[TreeRecap]
    total_agc_kg: float | None
    total_bgc_kg: float | None
    data_revision: int = Field(ge=1)


class ChatRequest(ContractModel):
    message: str = Field(min_length=1, max_length=4096)
    session_id: UUID | None = None


class ChatResponse(ContractModel):
    session_id: UUID
    answer: str
    intent: Literal[
        "local_inventory", "general_education", "out_of_scope_inventory", "mixed", "ambiguous"
    ]
    source_type: Literal["internal_inventory", "general_reference", "mixed", "none"]
    source_ids: list[str]
    plot_code: str | None
    method_version: str | None
    policy_status: Literal["allowed", "denied", "unavailable", "needs_clarification"]
