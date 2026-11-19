"""Входные данные профиля требований (вход create_requirement_profile).

Формат один для всех должностей: условия допуска + компетенции с индикаторами.
У каждой строки — обязательность, способ проверки и происхождение. Ранг и эталонный
уровень компетенции заполняются только из матрицы заказчика.
"""
import uuid
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import (
    CompetencyRank,
    FormalRequirementKind,
    RowOrigin,
    SourceRole,
    VerificationMethod,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileSourceIn(_Strict):
    """Документ, из которого собран профиль. Сам документ уже загружен в source_documents."""
    source_document_id: uuid.UUID
    role: SourceRole
    observed_revision: str | None = Field(default=None, max_length=128)
    is_primary: bool = False


class RowSourceIn(_Strict):
    """Происхождение строки: из документа (документ, адрес, цитата) или от команды (обоснование)."""
    origin: RowOrigin
    source_document_id: uuid.UUID | None = None
    source_ref: str | None = Field(default=None, min_length=1, max_length=64)
    source_quote: str | None = Field(default=None, min_length=1)
    note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_origin(self) -> Self:
        if self.origin == RowOrigin.SOURCE:
            missing = [
                name for name in ("source_document_id", "source_ref", "source_quote") if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"строка из документа должна указать {', '.join(missing)}")
        elif self.note is None:
            raise ValueError("строка команды должна иметь обоснование в note")
        return self


class FormalRequirementIn(RowSourceIn):
    kind: FormalRequirementKind
    description: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    is_mandatory: bool = True
    verification: VerificationMethod


class IndicatorIn(RowSourceIn):
    text: str = Field(min_length=1)
    is_mandatory: bool = True
    verification: VerificationMethod


class CompetencyIn(RowSourceIn):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=512)
    rank: CompetencyRank | None = None
    target_level_min: int | None = Field(default=None, ge=0, le=100)
    target_level_max: int | None = Field(default=None, ge=0, le=100)
    indicators: list[IndicatorIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_target(self) -> Self:
        low, high = self.target_level_min, self.target_level_max
        if (low is None) != (high is None):
            raise ValueError("эталонный уровень задаётся двумя числами или не задаётся вовсе")
        if low is not None and low > high:
            raise ValueError("нижняя граница эталона больше верхней")
        return self
