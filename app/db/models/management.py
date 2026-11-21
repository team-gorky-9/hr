"""Реестр годовых выпусков, сформированных из фактов legacy-hr (wave-4-reporting-stage-1, раздел 4B).

Сам снимок и его Excel живут в каталоге годового модуля (app.reporting.store), строка здесь
связывает выпуск с контуром, заявленной полнотой, основанием и автором. Через /management
читаются только выпуски из этого реестра."""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnnualReportRelease(Base):
    __tablename__ = "annual_report_releases"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contour: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(8))
    year: Mapped[int] = mapped_column(Integer)
    observed_until: Mapped[date] = mapped_column(Date)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confirmation_basis: Mapped[str] = mapped_column(Text)
    preparation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanSnapshot(Base):
    """Плановый срез потребностей (раздел 4C): неизменяемый ввод HR и рассчитанный результат.

    Строка только добавляется: исправление — новый срез. input_sha256 — отпечаток нормализованного
    ввода, по нему видно, что два среза построены на одном пакете."""
    __tablename__ = "plan_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    target_date: Mapped[date] = mapped_column(Date)
    scope_label: Mapped[str] = mapped_column(Text)
    coverage_note: Mapped[str] = mapped_column(Text)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    input_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
