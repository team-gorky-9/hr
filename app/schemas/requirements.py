"""Входные данные профиля требований (вход create_requirement_profile).

Формат один для всех должностей: условия допуска + компетенции с индикаторами.
У каждой строки — обязательность, способ проверки, этап проверки и происхождение.
Ранг и эталонный уровень компетенции заполняются только из матрицы заказчика.

Правило формального требования (`params`) — формат 0.1 из пакета профилей stage-0b-01,
принятый за основу (решение Родиона 20.11, контракт БД п. 3.5). Он проверяется при
создании профиля: неизвестная версия или ключ отклоняются при загрузке, а не всплывают
молчаливым unknown при оценке.
"""
import uuid
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db.enums import (
    CheckStage,
    CompetencyRank,
    FormalRequirementKind,
    RowOrigin,
    SourceRole,
    VerificationMethod,
)
from app.schemas.card import EducationLevel

PARAMS_SCHEMA_VERSION = "0.1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileSourceIn(_Strict):
    """Документ, из которого собран профиль. Сам документ уже загружен в source_documents."""
    source_document_id: uuid.UUID
    role: SourceRole
    observed_revision: str | None = Field(default=None, max_length=128)
    is_primary: bool = False


class SourceRefIn(_Strict):
    """Ссылка строки на документ: адрес в документе и дословная цитата."""
    source_document_id: uuid.UUID
    # «п. 2.2.1», «разд. 7, второй критерий; OOXML P201», «ИТК, инд. 2».
    address: str = Field(min_length=1, max_length=256)
    quote: str = Field(min_length=1)


class AcceptanceIn(_Strict):
    """Что считать выполнением, явным невыполнением и нехваткой сведений."""
    met: str | None = None
    not_met: str | None = None
    unknown: str | None = None
    limit: str | None = None  # ограничение вывода: «без численного балла до согласования рубрики»


class RowSourceIn(_Strict):
    """Ключ и происхождение строки: из документов (ссылки) или от команды (обоснование)."""
    key: str = Field(min_length=1, max_length=64, pattern=r"^\S+$")
    origin: RowOrigin
    source_refs: list[SourceRefIn] = Field(default_factory=list)
    note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_origin(self) -> Self:
        if self.origin == RowOrigin.SOURCE and not self.source_refs:
            raise ValueError("строка из документа должна иметь хотя бы одну ссылку source_refs")
        if self.origin == RowOrigin.TEAM and self.note is None:
            raise ValueError("строка команды должна иметь обоснование в note")
        return self


# --- params 0.1 ------------------------------------------------------------------

RowKey = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\S+$")]


class _Params(_Strict):
    schema_version: Literal["0.1"]


def _unique_keys(alternatives: list) -> None:
    keys = [a.key for a in alternatives]
    repeated = sorted({k for k in keys if keys.count(k) > 1})
    if repeated:
        raise ValueError(f"повторяются ключи альтернатив: {', '.join(repeated)}")


class EducationLevelAlternative(_Strict):
    """Внутри альтернативы условия соединяются AND, между альтернативами — OR."""
    key: RowKey
    level: EducationLevel | None = None  # словарь карточки v1.4
    # Направление, заданное одной фразой с уровнем: «высшее техническое».
    field_group: str | None = Field(default=None, min_length=1)
    field_examples: list[str] = Field(default_factory=list)
    field_exclusions: list[str] = Field(default_factory=list)
    # «Студент старших курсов»: граница курса ещё не согласована (Q-STUDENT).
    enrollment_status: Literal["senior_student"] | None = None

    @model_validator(mode="after")
    def _check_condition(self) -> Self:
        if self.level is None and self.enrollment_status is None:
            raise ValueError(f"альтернатива {self.key}: нужен level или enrollment_status")
        return self


class EducationLevelParams(_Params):
    alternatives: list[EducationLevelAlternative] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_keys(self) -> Self:
        _unique_keys(self.alternatives)
        return self


class EducationFieldAlternative(_Strict):
    key: RowKey
    degree_fields: list[str] | None = Field(default=None, min_length=1)      # направление диплома
    retraining_fields: list[str] | None = Field(default=None, min_length=1)  # направление переподготовки

    @model_validator(mode="after")
    def _check_one(self) -> Self:
        if (self.degree_fields is None) == (self.retraining_fields is None):
            raise ValueError(f"альтернатива {self.key}: нужен ровно один из degree_fields, retraining_fields")
        return self


class EducationFieldParams(_Params):
    alternatives: list[EducationFieldAlternative] = Field(min_length=1)
    # Ключ требования уровня: направление проверяется по записям с подтверждённым уровнем.
    requires_requirement: RowKey | None = None

    @model_validator(mode="after")
    def _check_keys(self) -> Self:
        _unique_keys(self.alternatives)
        return self


class ExperienceParams(_Params):
    scope: Literal["total_commercial", "relevant_role"]
    minimum_defined: bool
    min_months: int | None = Field(default=None, gt=0)
    relevance_hint: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_minimum(self) -> Self:
        # Порог есть только там, где он есть в источнике: «нет числа» не превращается в 0 или 12.
        if self.minimum_defined != (self.min_months is not None):
            raise ValueError("min_months задаётся тогда и только тогда, когда minimum_defined = true")
        if self.scope == "relevant_role" and self.relevance_hint is None:
            raise ValueError("для relevant_role нужен relevance_hint: что считать соответствующим опытом")
        return self


class NoRuleParams(_Params):
    """knowledge и other: правила нет, строка проверяется человеком (интервью)."""


PARAMS_BY_KIND: dict[FormalRequirementKind, type[_Params]] = {
    FormalRequirementKind.EDUCATION_LEVEL: EducationLevelParams,
    FormalRequirementKind.EDUCATION_FIELD: EducationFieldParams,
    FormalRequirementKind.EXPERIENCE: ExperienceParams,
    FormalRequirementKind.KNOWLEDGE: NoRuleParams,
    FormalRequirementKind.OTHER: NoRuleParams,
}


def parse_params(kind: FormalRequirementKind, params: dict[str, Any]) -> _Params:
    """Разобрать params по виду требования. Неизвестная версия или ключ → ValueError."""
    if kind in (FormalRequirementKind.KNOWLEDGE, FormalRequirementKind.OTHER) and not params:
        return NoRuleParams(schema_version=PARAMS_SCHEMA_VERSION)
    if params.get("schema_version") != PARAMS_SCHEMA_VERSION:
        raise ValueError(
            f"params.schema_version = {params.get('schema_version')!r}: поддерживается только {PARAMS_SCHEMA_VERSION}"
        )
    try:
        return PARAMS_BY_KIND[kind].model_validate(params)
    except ValidationError as error:
        raise ValueError(f"params для {kind.value} не по формату {PARAMS_SCHEMA_VERSION}: {error}") from error


def alternative_keys(params: dict[str, Any]) -> list[str]:
    """Ключи альтернатив правила в порядке профиля (пусто, если альтернатив нет)."""
    return [a["key"] for a in params.get("alternatives", [])]


class _StagedRow(RowSourceIn):
    """Строка, которую проверяют: где подтверждается (verification) и на каком этапе (check_stage)."""
    is_mandatory: bool = True
    verification: VerificationMethod
    # Без явного значения: интервью и тест → interview, резюме и документы → screening.
    check_stage: CheckStage | None = None
    acceptance: AcceptanceIn = Field(default_factory=AcceptanceIn)

    @model_validator(mode="after")
    def _check_stage(self) -> Self:
        by_resume = self.verification in (VerificationMethod.RESUME, VerificationMethod.DOCUMENTS)
        if self.check_stage is None:
            self.check_stage = CheckStage.SCREENING if by_resume else CheckStage.INTERVIEW
        elif self.check_stage == CheckStage.SCREENING and not by_resume:
            raise ValueError(
                f"строка {self.key}: verification = {self.verification.value} не проверяется на этапе screening"
            )
        return self


class FormalRequirementIn(_StagedRow):
    kind: FormalRequirementKind
    description: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self) -> Self:
        parse_params(self.kind, self.params)
        return self


class IndicatorIn(_StagedRow):
    text: str = Field(min_length=1)
    excluded_from_scoring: bool = False


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
