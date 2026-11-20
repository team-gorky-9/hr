"""Public report schema. Dates retain their original canonical strings."""
from typing import Literal

from pydantic import BaseModel, Field

from .loader import Sources


class Version(BaseModel):
    snapshot_id: str
    year: int
    scope_label: str
    mode: Literal["demo", "work"]
    extracted_at: str


class Metric(BaseModel):
    value: int | None
    status: Literal["complete", "partial", "unavailable", "future"]
    reason_codes: list[str]


class Metrics(BaseModel):
    applications_received: Metric
    phone_interviews_held: Metric
    applications_with_phone_interview: Metric


class Vacancy(BaseModel):
    vacancy_key: str
    label: str
    applications_received: Metric
    applications_with_phone_interview: Metric
    phone_interviews_held: Metric


class Month(BaseModel):
    month: str
    metrics: Metrics
    outcomes: dict[Literal["pending", "stop", "continue"], Metric]
    vacancies: list[Vacancy]


class Comparison(BaseModel):
    delta: int | None
    percent: float | None
    reason: str | None


class Quality(BaseModel):
    undated_applications: int
    undated_interviews: int
    duplicates: int


class Snapshot(Version):
    analytics_sha256: str | None = None
    operations: dict | None = None
    scope_id: str
    scope_revision: str
    report_schema_version: Literal[1]
    metric_version: Literal["recruitment-v1"]
    timezone: str
    sources: Sources
    observed_until: str
    period_start: str
    period_end_exclusive: str
    input_sha256: str = Field(min_length=64, max_length=64)
    interim: bool
    quality: Quality
    totals: Metrics
    previous_totals: Metrics
    months: list[Month]
    previous_months: list[Month]
    comparison: dict[str, Comparison]
    vacancies: list[Vacancy]
