"""Входные данные для сохранения оценки кандидата по требованиям должности."""
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import CheckResult
from app.schemas.card import Evidence


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FormalCheckIn(_Strict):
    requirement_id: uuid.UUID
    result: CheckResult
    explanation: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class CompetencyScoreIn(_Strict):
    competency_id: uuid.UUID
    level: int | None = Field(default=None, ge=0, le=100)
    explanation: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
