"""DTO /api/v1/management, docs/contracts/wave-4-reporting-stage-1.md (раздел 4A)."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


# --- 4C · плановый снимок потребностей ----------------------------------------------------

PlanKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
PlanText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Readiness = Literal["confirmed", "expected", "similarity", "unknown"]


class PlanRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: PlanKey
    id: PlanKey


class PlanNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: PlanKey
    department_key: PlanKey
    position_code: PlanKey
    quantity: int = Field(ge=1, le=1000, strict=True)
    source_reference: PlanText


class PlanPerson(BaseModel):
    """Запись о человеке. person_ref — подтверждённая идентичность; без него запись не склеивается
    с другими и не считается подтверждённым уникальным человеком."""
    model_config = ConfigDict(extra="forbid")
    person_ref: PlanRef | None
    record_ref: PlanRef
    label: PlanText
    contact_available: bool


class PlanMatch(BaseModel):
    """Заключение HR о готовности записи к потребности; система его не выводит сама."""
    model_config = ConfigDict(extra="forbid")
    need_key: PlanKey
    record_ref: PlanRef
    readiness: Readiness
    basis: PlanText


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_date: date
    scope_label: PlanText
    needs: list[PlanNeed] = Field(min_length=1, max_length=200)
    people: list[PlanPerson] = Field(default_factory=list, max_length=2000)
    matches: list[PlanMatch] = Field(default_factory=list, max_length=10000)
    coverage_note: PlanText

    @model_validator(mode="after")
    def references(self):
        needs = [n.key for n in self.needs]
        if len(needs) != len(set(needs)):
            raise ValueError("needs: keys must be unique")
        records = [(p.record_ref.system, p.record_ref.id) for p in self.people]
        if len(records) != len(set(records)):
            raise ValueError("people: record_ref must be unique")
        known_needs, known_records, seen = set(needs), set(records), set()
        for index, match in enumerate(self.matches):
            record = (match.record_ref.system, match.record_ref.id)
            if match.need_key not in known_needs:
                raise ValueError(f"matches[{index}].need_key does not refer to an input need")
            if record not in known_records:
                raise ValueError(f"matches[{index}].record_ref does not refer to an input person record")
            if (match.need_key, record) in seen:
                raise ValueError(f"matches[{index}] repeats the same need and record")
            seen.add((match.need_key, record))
        return self


class PlanOut(BaseModel):
    id: UUID
    target_date: date
    scope_label: str
    coverage_note: str
    created_at: datetime
    created_by: str | None
    input_sha256: str
    input: dict
    result: dict


class PlanSummaryOut(BaseModel):
    """Управленческая проекция: без имён, record_ref и первичных оснований."""
    id: UUID
    target_date: date
    scope_label: str
    coverage_note: str
    created_at: datetime
    totals: dict
    needs: list[dict]
    warnings: list[dict]
