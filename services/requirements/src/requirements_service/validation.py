"""Валидация профиля требований requirement-draft/1.0, правил params 0.1 и цитат.

Схемы, строгие проверки скалярных типов (bool/int), группировки same_as и
поиска несоседних фрагментов цитаты перенесены из hr/app/requirements/schemas.py
и hr/app/schemas/requirements.py для полностью автономной работы сервиса.
"""
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
import uuid

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator

from .errors import ServiceError

PARAMS_SCHEMA_VERSION = "0.1"


class EducationLevel(StrEnum):
    HIGHER = "высшее"
    INCOMPLETE_HIGHER = "неоконченное высшее"
    VOCATIONAL = "среднее профессиональное"
    SECONDARY = "среднее общее"


class CompetencyRank(StrEnum):
    KEY = "key"
    BASIC = "basic"
    SPECIAL = "special"


class VerificationMethod(StrEnum):
    RESUME = "resume"
    DOCUMENTS = "documents"
    INTERVIEW = "interview"
    TEST = "test"


class CheckStage(StrEnum):
    SCREENING = "screening"
    INTERVIEW = "interview"


class RowOrigin(StrEnum):
    SOURCE = "source"
    TEAM = "team"


class SourceRole(StrEnum):
    JOB_DESCRIPTION = "job_description"
    COMPETENCY_MATRIX = "competency_matrix"
    VACANCY_POSTING = "vacancy_posting"
    REGULATION = "regulation"
    OTHER = "other"


class FormalRequirementKind(StrEnum):
    EDUCATION_LEVEL = "education_level"
    EDUCATION_FIELD = "education_field"
    EXPERIENCE = "experience"
    KNOWLEDGE = "knowledge"
    OTHER = "other"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileSourceIn(_Strict):
    source_document_id: uuid.UUID
    role: SourceRole
    observed_revision: str | None = Field(default=None, max_length=128)
    is_primary: bool = False


class SourceRefIn(_Strict):
    source_document_id: uuid.UUID
    address: str = Field(min_length=1, max_length=256)
    quote: str = Field(min_length=1)


class AcceptanceIn(_Strict):
    met: str | None = None
    not_met: str | None = None
    unknown: str | None = None
    limit: str | None = None


class RowSourceIn(_Strict):
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


RowKey = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\S+$")]


class _Params(_Strict):
    schema_version: Literal["0.1"]


def _unique_keys(alternatives: list) -> None:
    keys = [a.key for a in alternatives]
    repeated = sorted({k for k in keys if keys.count(k) > 1})
    if repeated:
        raise ValueError(f"повторяются ключи альтернатив: {', '.join(repeated)}")


class EducationLevelAlternative(_Strict):
    key: RowKey
    level: EducationLevel | None = None
    field_group: str | None = Field(default=None, min_length=1)
    field_examples: list[str] = Field(default_factory=list)
    field_exclusions: list[str] = Field(default_factory=list)
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
    degree_fields: list[str] | None = Field(default=None, min_length=1)
    retraining_fields: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_one(self) -> Self:
        if (self.degree_fields is None) == (self.retraining_fields is None):
            raise ValueError(f"альтернатива {self.key}: нужен ровно один из degree_fields, retraining_fields")
        return self


class EducationFieldParams(_Params):
    alternatives: list[EducationFieldAlternative] = Field(min_length=1)
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
        if self.minimum_defined != (self.min_months is not None):
            raise ValueError("min_months задаётся тогда и только тогда, когда minimum_defined = true")
        if self.scope == "relevant_role" and self.relevance_hint is None:
            raise ValueError("для relevant_role нужен relevance_hint")
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
    if kind in (FormalRequirementKind.KNOWLEDGE, FormalRequirementKind.OTHER) and not params:
        return NoRuleParams(schema_version=PARAMS_SCHEMA_VERSION)
    if params.get("schema_version") != PARAMS_SCHEMA_VERSION:
        raise ValueError("неподдерживаемая версия schema_version в params")
    return PARAMS_BY_KIND[kind].model_validate(params)


class _StagedRow(RowSourceIn):
    is_mandatory: bool = True
    verification: VerificationMethod
    check_stage: CheckStage | None = None
    acceptance: AcceptanceIn = Field(default_factory=AcceptanceIn)

    @model_validator(mode="after")
    def _check_stage(self) -> Self:
        by_resume = self.verification in (VerificationMethod.RESUME, VerificationMethod.DOCUMENTS)
        if self.check_stage is None:
            self.check_stage = CheckStage.SCREENING if by_resume else CheckStage.INTERVIEW
        elif self.check_stage == CheckStage.SCREENING and not by_resume:
            raise ValueError("verification не проверяется на этапе screening")
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
    same_as: RowKey | None = None

    @model_validator(mode="after")
    def _check_group(self) -> Self:
        if self.same_as is not None and self.excluded_from_scoring:
            raise ValueError("same_as cannot contain excluded indicators")
        return self


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


def validate_groups(competencies: list[CompetencyIn]) -> None:
    """Проверить группы same_as: одна компетенция, один этап, без исключённых строк."""
    groups: dict[str, tuple[str, CheckStage | None]] = {}
    for competency in competencies:
        for row in competency.indicators:
            key = getattr(row, "same_as", None)
            if key is None:
                continue
            if not key.strip() or row.excluded_from_scoring:
                raise ValueError("same_as: empty or excluded group")
            identity = (competency.key, row.check_stage)
            if key in groups and groups[key] != identity:
                raise ValueError("same_as members must share competency and check_stage")
            groups[key] = identity


class ProfileDraft(BaseModel):
    """Нормализованный профиль требований формата requirement-draft/1.0."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal["requirement-draft/1.0"]
    position_code: str = Field(min_length=1, max_length=64)
    is_synthetic: StrictBool
    sources: list[ProfileSourceIn] = Field(default_factory=list)
    formal_requirements: list[FormalRequirementIn]
    competencies: list[CompetencyIn]
    note: str | None = None

    @model_validator(mode="after")
    def check_rows(self) -> Self:
        rows = [
            *self.formal_requirements,
            *self.competencies,
            *(r for c in self.competencies for r in c.indicators),
        ]
        if not rows or len({r.key for r in rows}) != len(rows):
            raise ValueError("пустой профиль или дублируются ключи строк")
        if len({c.code for c in self.competencies}) != len(self.competencies):
            raise ValueError("дублируются коды компетенций")
        source_ids = [s.source_document_id for s in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("документ указан в источниках профиля дважды")
        for row in rows:
            for ref in row.source_refs:
                if ref.source_document_id not in source_ids:
                    raise ValueError("source_refs ссылается на документ, отсутствующий в sources")
        level_keys = {
            r.key for r in self.formal_requirements if r.kind == FormalRequirementKind.EDUCATION_LEVEL
        }
        for req in self.formal_requirements:
            required = req.params.get("requires_requirement")
            if required is not None and required not in level_keys:
                raise ValueError("requires_requirement ссылается на отсутствующее требование уровня образования")
        validate_groups(self.competencies)
        return self


BOOL_FIELDS = frozenset(
    {"is_synthetic", "is_mandatory", "is_primary", "minimum_defined", "excluded_from_scoring"}
)
INT_FIELDS = frozenset({"min_months", "target_level_min", "target_level_max", "sort_order"})
SAFE_FIELDS = (
    set(ProfileDraft.model_fields)
    | BOOL_FIELDS
    | INT_FIELDS
    | {
        "params", "indicators", "key", "kind", "description", "name", "text", "code", "rank", "origin",
        "source_refs", "source_document_id", "address", "quote", "verification", "check_stage", "acceptance",
        "met", "not_met", "unknown", "limit", "alternatives", "scope", "requires_requirement", "role",
        "observed_revision", "same_as", "level", "enrollment_status", "field_group", "field_examples",
        "field_exclusions", "degree_fields", "retraining_fields", "relevance_hint",
    }
)


def _safe_path(parts: tuple[Any, ...]) -> str:
    joined = ".".join(str(p) if isinstance(p, int) or p in SAFE_FIELDS else "*" for p in parts)
    return f"content.{joined}" if joined else "content"


def check_scalar_types(value: Any, path: tuple[Any, ...] = ()) -> None:
    """Строгая проверка bool и int до Pydantic coercion."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in BOOL_FIELDS and type(item) is not bool:
                raise ServiceError(
                    422,
                    "VALIDATION_ERROR",
                    "Профиль не соответствует схеме; проверьте булево поле.",
                    field=_safe_path((*path, key)),
                )
            if key in INT_FIELDS and item is not None and type(item) is not int:
                raise ServiceError(
                    422,
                    "VALIDATION_ERROR",
                    "Профиль не соответствует схеме; проверьте целочисленное поле.",
                    field=_safe_path((*path, key)),
                )
            check_scalar_types(item, (*path, key))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            check_scalar_types(item, (*path, idx))


def validate_draft_content(data: dict[str, Any] | ProfileDraft) -> ProfileDraft:
    """Проверить словарь содержимого черновика по формату requirement-draft/1.0."""
    if isinstance(data, ProfileDraft):
        data = data.model_dump(mode="json")
    if not isinstance(data, dict):
        raise ServiceError(
            422,
            "VALIDATION_ERROR",
            "Содержимое профиля должно быть JSON-объектом.",
            field="content",
        )
    check_scalar_types(data)
    try:
        return ProfileDraft.model_validate(data)
    except ValidationError as exc:
        first = exc.errors(include_input=False, include_context=False)[0]
        raise ServiceError(
            422,
            "VALIDATION_ERROR",
            "Профиль не соответствует схеме requirement-draft/1.0.",
            field=_safe_path(tuple(first["loc"])),
        ) from exc


def quote_in_document(quote: str, text: str) -> bool:
    """Проверить наличие фрагментов цитаты в тексте в исходном порядке."""
    if not quote.strip():
        return False
    offset = 0
    for fragment in quote.splitlines():
        start = text.find(fragment, offset)
        if start < 0:
            return False
        offset = start + len(fragment)
    return True


def iter_all_rows(draft: ProfileDraft):
    """Перебрать все строки профиля с source_refs."""
    yield from draft.formal_requirements
    for competency in draft.competencies:
        yield competency
        yield from competency.indicators
