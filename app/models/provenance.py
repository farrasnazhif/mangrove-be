"""Durable provenance, snapshots and current publication pointers."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.inventory import new_id


class Record:
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_id)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Attachment(Record, Timestamped, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("visibility IN ('private', 'public')", name="ck_attachments_visibility"),
        CheckConstraint("size_bytes > 0", name="ck_attachments_size"),
        CheckConstraint("length(object_key) > 0", name="ck_attachments_key"),
    )
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[str] = mapped_column(String(16), default="private", server_default="private")
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class DbhImportBatch(Record, Base):
    __tablename__ = "dbh_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "source_drive_file_id", "source_revision", name="uq_import_source_revision"
        ),
        CheckConstraint(
            "status IN ('pending', 'validated', 'imported', 'quarantine', 'failed')",
            name="ck_imports_status",
        ),
    )
    source_drive_file_id: Mapped[str] = mapped_column(String(200))
    source_revision: Mapped[str] = mapped_column(String(200))
    imported_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")


class AuditEvent(Record, Timestamped, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    action: Mapped[str] = mapped_column(String(100))
    change_summary: Mapped[dict] = mapped_column(JSON)


class CalculationRun(Record, Timestamped, Base):
    __tablename__ = "calculation_runs"
    __table_args__ = (
        UniqueConstraint("id", "plot_id", "qa_status", name="uq_runs_publication_target"),
        CheckConstraint("input_revision > 0", name="ck_runs_revision"),
        CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="ck_runs_hash"),
        CheckConstraint("qa_status IN ('draft', 'approved', 'rejected')", name="ck_runs_status"),
    )
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id"), index=True)
    method_version_id: Mapped[str] = mapped_column(ForeignKey("method_versions.id"), index=True)
    input_revision: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict] = mapped_column(JSON)
    qa_flags: Mapped[list[str]] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    qa_status: Mapped[str] = mapped_column(String(32), default="draft", server_default="draft")


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["published_run_id", "plot_id", "run_qa_status"],
            ["calculation_runs.id", "calculation_runs.plot_id", "calculation_runs.qa_status"],
            name="fk_publications_approved_plot_run",
        ),
        CheckConstraint("run_qa_status = 'approved'", name="ck_publications_approved"),
    )
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id"), primary_key=True)
    published_run_id: Mapped[str] = mapped_column(UUID(as_uuid=False))
    run_qa_status: Mapped[str] = mapped_column(
        String(32), default="approved", server_default="approved"
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
