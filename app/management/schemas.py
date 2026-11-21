"""DTO /api/v1/management, docs/contracts/wave-4-reporting-stage-1.md (раздел 4A)."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas import Contour, FunnelOut


class OverviewPeriod(BaseModel):
    """from включительно, to исключительно, границы суток по Москве."""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    from_: date = Field(alias="from")
    to: date
    timezone: Literal["Europe/Moscow"] = "Europe/Moscow"


class OverviewSource(BaseModel):
    system: Literal["legacy-hr"] = "legacy-hr"
    contour: Contour


class InterviewerRow(BaseModel):
    interviewer_user_id: UUID | None
    login: str | None
    held_count: int
    no_answer_count: int
    # continue / stop — состоявшиеся в периоде разговоры по итогу; pending — открытые встречи
    # этого проводящего (без даты, вне периода).
    outcomes: dict[Literal["continue", "stop", "pending"], int]


class InterviewsBlock(BaseModel):
    status: Literal["available", "unavailable"]
    held_count: int | None = None
    held_applications_count: int | None = None
    no_answer_count: int | None = None
    open_count: int | None = None
    undated_count: int | None = None
    by_interviewer: list[InterviewerRow] = Field(default_factory=list)
    units: dict[str, str]
    coverage_note: str


class SourceStatus(BaseModel):
    key: str
    status: Literal["available", "unavailable"]
    observed_at: datetime | None
    note: str


class OverviewOut(BaseModel):
    generated_at: datetime
    period: OverviewPeriod
    source: OverviewSource
    funnel: FunnelOut
    interviews: InterviewsBlock
    sources: list[SourceStatus]


# --- 4B · годовой выпуск из доступных фактов ------------------------------------------------

class CoverageInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    from_: date = Field(alias="from")
    to: date


class SourceCoverage(BaseModel):
    """Полнота, которую заявляет HR. По умолчанию интервалов нет и полнота не обещается."""
    model_config = ConfigDict(extra="forbid")

    complete_intervals: list[CoverageInterval] = Field(default_factory=list, max_length=50)
    comparable_to_previous_year: bool = False


class ReleaseCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applications: SourceCoverage = Field(default_factory=SourceCoverage)
    phone_interviews: SourceCoverage = Field(default_factory=SourceCoverage)


class AnnualReleaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=2000, le=2100)
    observed_until: date
    contour: Contour
    coverage: ReleaseCoverage = Field(default_factory=ReleaseCoverage)
    confirmation_basis: str = Field(min_length=5, max_length=2000)


class ReleaseSummary(BaseModel):
    snapshot_id: str
    mode: Literal["demo", "work"]
    year: int
    contour: Contour
    generated_at: datetime
    observed_until: date
    coverage_summary: dict
    preparation: dict
    confirmation_basis: str
    created_by: str | None
    report_url: str
    xlsx_url: str


class AnnualReleaseOut(BaseModel):
    release: ReleaseSummary
    report: dict
