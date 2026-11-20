"""Versioned competency evidence; counters are derived by code, never by the LLM."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.card import Evidence
from app.schemas.requirements import RowKey

Status = Literal['confirmed', 'contradicted', 'no_info']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IndicatorResult(Strict):
    key: RowKey
    status: Status
    evidence: list[Evidence] = Field(default_factory=list)
    ambiguous_location: bool = False


class Counter(Strict):
    confirmed: int = Field(default=0, ge=0)
    contradicted: int = Field(default=0, ge=0)
    no_info: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class GroupResult(Strict):
    key: RowKey
    members: list[RowKey]
    is_mandatory: bool
    status: Status
    manual_review: bool = False


class CompetencyDetails(Strict):
    schema_version: Literal['1.0'] = '1.0'
    basis: Literal['resume'] = 'resume'
    check_stage: Literal['screening'] = 'screening'
    indicators: list[IndicatorResult] = Field(default_factory=list)
    groups: list[GroupResult] = Field(default_factory=list)
    mandatory: Counter = Field(default_factory=Counter)
    desired: Counter = Field(default_factory=Counter)
    on_interview: int = Field(default=0, ge=0)
    excluded: int = Field(default=0, ge=0)


class ProfileCounters(Strict):
    mandatory: Counter = Field(default_factory=Counter)
    desired: Counter = Field(default_factory=Counter)
    on_interview: int = Field(default=0, ge=0)
    excluded: int = Field(default=0, ge=0)
    manual_review_groups: int = Field(default=0, ge=0)
