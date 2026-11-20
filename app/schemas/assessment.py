"""Входные данные для сохранения оценки кандидата по требованиям должности."""
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import CheckResult
from app.schemas.card import Evidence
from app.schemas.requirements import RowKey


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AlternativeResultIn(_Strict):
    """Результат одной альтернативы требования (ключ из params.alternatives) со своими цитатами."""
    key: RowKey
    result: CheckResult
    evidence: list[Evidence] = Field(default_factory=list)


class FormalCheckIn(_Strict):
    """Вывод модели по резюме. Основание всегда resume: модель видит только очищенный текст.
    Результат по документу, интервью или тесту вносит человек — repository.confirm_formal_check."""
    requirement_id: uuid.UUID
    result: CheckResult
    explanation: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    # Либо пусто, либо все альтернативы требования; итог строки должен следовать из них.
    alternatives: list[AlternativeResultIn] = Field(default_factory=list)


class CompetencyScoreIn(_Strict):
    competency_id: uuid.UUID
    level: int | None = Field(default=None, ge=0, le=100)
    explanation: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
