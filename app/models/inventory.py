"""Schema needed by Task 03's synthetic dataset; later tasks extend these entities."""

import uuid
from datetime import date

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement, WKTElement
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def new_id() -> str:
    return str(uuid.uuid4())


class SyntheticRecord:
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_id)
    data_label: Mapped[str] = mapped_column(String(32), nullable=False, default="synthetic")


class Zone(SyntheticRecord, Base):
    __tablename__ = "zones"
    __table_args__ = (
        CheckConstraint(
            "NOT boundary_is_synthetic OR NOT approved_scope", name="ck_zones_approval"
        ),
        CheckConstraint("ST_IsValid(boundary_geom)", name="ck_zones_valid_boundary"),
    )

    name: Mapped[str] = mapped_column(String(200), unique=True)
    boundary_geom: Mapped[WKBElement | WKTElement] = mapped_column(Geometry("POLYGON", srid=4326))
    boundary_source: Mapped[str] = mapped_column(String(500))
    boundary_revision: Mapped[str] = mapped_column(String(100))
    boundary_is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_scope: Mapped[bool] = mapped_column(Boolean, default=False)


class Plot(SyntheticRecord, Base):
    __tablename__ = "plots"
    __table_args__ = (
        CheckConstraint("code ~ '^VAK-[0-9]+$'", name="ck_plots_code"),
        CheckConstraint("area_m2 > 0", name="ck_plots_area"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_plots_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_plots_longitude"),
        CheckConstraint("status IN ('draft', 'quarantine')", name="ck_plots_status"),
        CheckConstraint("row_version > 0", name="ck_plots_version"),
        CheckConstraint(
            "ST_X(geom) = longitude AND ST_Y(geom) = latitude", name="ck_plots_coordinates_match"
        ),
    )

    code: Mapped[str] = mapped_column(String(50), unique=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    area_m2: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    geom: Mapped[WKBElement | WKTElement] = mapped_column(Geometry("POINT", srid=4326))
    survey_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    scope_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)


class Species(SyntheticRecord, Base):
    __tablename__ = "species"
    scientific_name: Mapped[str] = mapped_column(String(200), unique=True)


class Tree(SyntheticRecord, Base):
    __tablename__ = "tree_records"
    __table_args__ = (
        CheckConstraint("dbh_cm > 0", name="ck_trees_dbh"),
        CheckConstraint(
            "wood_density_g_cm3 > 0 AND wood_density_g_cm3 <= 2", name="ck_trees_density"
        ),
    )

    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id"), index=True)
    species_id: Mapped[str] = mapped_column(ForeignKey("species.id"))
    dbh_cm: Mapped[float] = mapped_column(Float)
    wood_density_g_cm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    density_source: Mapped[str] = mapped_column(String(200))
    qa_status: Mapped[str] = mapped_column(String(32), default="synthetic-unreviewed")
    row_version: Mapped[int] = mapped_column(Integer, default=1)


class SedimentCore(SyntheticRecord, Base):
    __tablename__ = "sediment_cores"
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id"), index=True)
    sample_code: Mapped[str] = mapped_column(String(100), unique=True)
    sample_date: Mapped[date] = mapped_column(Date)


class SedimentLayer(SyntheticRecord, Base):
    __tablename__ = "sediment_layers"
    __table_args__ = (
        CheckConstraint(
            "depth_bottom_cm > depth_top_cm AND depth_top_cm >= 0", name="ck_layers_depth"
        ),
        CheckConstraint("dry_mass_g > 0 AND volume_cm3 > 0", name="ck_layers_mass_volume"),
        CheckConstraint("loi_pct BETWEEN 0 AND 100", name="ck_layers_loi"),
        ExcludeConstraint(
            ("core_id", "="),
            (text("numrange(depth_top_cm::numeric, depth_bottom_cm::numeric, '[)')"), "&&"),
            name="ex_layers_overlap",
            using="gist",
        ),
    )

    core_id: Mapped[str] = mapped_column(ForeignKey("sediment_cores.id"), index=True)
    depth_top_cm: Mapped[float] = mapped_column(Float)
    depth_bottom_cm: Mapped[float] = mapped_column(Float)
    dry_mass_g: Mapped[float] = mapped_column(Float)
    volume_cm3: Mapped[float] = mapped_column(Float)
    loi_pct: Mapped[float] = mapped_column(Float)
    qa_status: Mapped[str] = mapped_column(String(32), default="synthetic-unreviewed")


class MethodVersion(SyntheticRecord, Base):
    __tablename__ = "method_versions"
    version: Mapped[str] = mapped_column(String(100), unique=True)
    coefficients_json: Mapped[dict] = mapped_column(JSON)
    references: Mapped[list[str]] = mapped_column(JSON)
    approval_status: Mapped[str] = mapped_column(String(100), default="pending-scientific-approval")
