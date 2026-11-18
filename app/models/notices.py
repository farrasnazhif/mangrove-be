"""Durable manager notices emitted alongside calculation runs."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.provenance import Record, Timestamped


class ManagerNotice(Record, Timestamped, Base):
    __tablename__ = "manager_notices"
    __table_args__ = (UniqueConstraint("calculation_run_id", "flag", name="uq_notice_run_flag"),)
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id"), index=True)
    calculation_run_id: Mapped[str] = mapped_column(ForeignKey("calculation_runs.id"))
    plot_code: Mapped[str] = mapped_column(String(50))
    flag: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(String(500))
    suggested_action: Mapped[str] = mapped_column(String(500))
