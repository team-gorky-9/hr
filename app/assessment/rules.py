"""Разбор formal_requirements.params пакета 0.2 (params версии 0.1).

Неизвестная версия, ключ или вид требования → RuleUnsupportedError ещё до вызова модели:
оценка по профилю не создаётся, чтобы не получить молчаливое «неизвестно».
"""
from dataclasses import dataclass, field
from typing import Any, Literal

from app.assessment.errors import RuleUnsupportedError

SUPPORTED_VERSIONS = {"0.1"}

_ALTERNATIVE_KEYS = {
    "key", "level", "field_group", "field_examples", "field_exclusions",
    "enrollment_status", "degree_fields", "retraining_fields",
}


@dataclass(frozen=True)
class EducationRule:
    key: str
    alternatives: list[dict[str, Any]]
    requires: str | None = None


@dataclass(frozen=True)
class ExperienceRule:
    key: str
    scope: Literal["total_commercial", "relevant_role"]
    min_months: int | None
    relevance_hint: str | None = None


@dataclass(frozen=True)
class InterviewOnlyRule:
    """Требование, которое по резюме не проверяется (знания законов и т. п.)."""
    key: str


Rule = EducationRule | ExperienceRule | InterviewOnlyRule


@dataclass
class ParsedProfile:
    rules: dict[str, Rule] = field(default_factory=dict)


def _check_keys(where: str, given: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(given) - allowed
    if unknown:
        raise RuleUnsupportedError(f"{where}: неизвестные ключи params {sorted(unknown)}")


def parse_rule(key: str, kind: str, params: dict[str, Any], verification: str) -> Rule:
    if kind in ("knowledge", "other"):
        return InterviewOnlyRule(key=key)
    version = params.get("schema_version")
    if version not in SUPPORTED_VERSIONS:
        raise RuleUnsupportedError(f"{key}: версия правила {version!r} не поддерживается")

    if kind in ("education_level", "education_field"):
        _check_keys(key, params, {"schema_version", "alternatives", "requires_requirement"})
        alternatives = params.get("alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            raise RuleUnsupportedError(f"{key}: нет списка alternatives")
        for alternative in alternatives:
            if not isinstance(alternative, dict) or "key" not in alternative:
                raise RuleUnsupportedError(f"{key}: у альтернативы нет ключа")
            _check_keys(f"{key}/{alternative['key']}", alternative, _ALTERNATIVE_KEYS)
        return EducationRule(key=key, alternatives=alternatives, requires=params.get("requires_requirement"))

    if kind == "experience":
        _check_keys(key, params, {"schema_version", "scope", "minimum_defined", "min_months", "relevance_hint"})
        scope = params.get("scope")
        if scope not in ("total_commercial", "relevant_role"):
            raise RuleUnsupportedError(f"{key}: scope {scope!r} не поддерживается")
        if params.get("minimum_defined"):
            min_months = params.get("min_months")
            if not isinstance(min_months, int) or min_months < 1:
                raise RuleUnsupportedError(f"{key}: при minimum_defined нужен min_months > 0")
        else:
            min_months = None
        if scope == "total_commercial" and min_months is None:
            raise RuleUnsupportedError(f"{key}: общий коммерческий стаж без порога не проверяется")
        return ExperienceRule(key=key, scope=scope, min_months=min_months, relevance_hint=params.get("relevance_hint"))

    raise RuleUnsupportedError(f"{key}: вид требования {kind!r} не поддерживается")
