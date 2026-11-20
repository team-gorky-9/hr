"""Deterministic application-to-position mapping, independent of candidate merit."""
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


def normalize_title(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


class MappingRule(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, frozen=True)
    posting_title: str = Field(min_length=1)
    status: Literal['confirmed', 'mismatch']
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)
    responsible: str = Field(min_length=1)


class Policy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: str = Field(min_length=1)
    position_code: str = Field(min_length=1)
    rules: list[MappingRule]

    @model_validator(mode='after')
    def unique_titles(self) -> Self:
        titles = [normalize_title(r.posting_title) for r in self.rules]
        if len(titles) != len(set(titles)):
            raise ValueError('ambiguous posting_title mapping')
        return self


class Applicability(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    status: Literal['confirmed', 'mismatch', 'unresolved']
    reason: str
    explanation: str
    policy_version: str
    policy_hash: str
    input_hash: str
    snapshot: dict


DEFAULT_POLICY = Path(__file__).with_name('policies') / 'hr-consultant.json'


def resolve_applicability(position_code: str, posting_title: str | None, *,
                          policy: Policy | None = None) -> Applicability | None:
    # None explicitly means this policy does not cover the position, not "confirmed".
    if policy is None:
        policy = Policy.model_validate_json(DEFAULT_POLICY.read_text(encoding='utf-8'))
    if position_code != policy.position_code:
        return None
    normalized = normalize_title(posting_title or '')
    rule = next((r for r in policy.rules if normalize_title(r.posting_title) == normalized), None)
    status = rule.status if rule else 'unresolved'
    reason = rule.reason if rule else ('unreviewed_mapping' if normalized else 'missing_posting')
    if status == 'confirmed':
        explanation = f'Соответствие целевой должности подтверждено. Основание: {rule.source}.'
    elif status == 'mismatch':
        explanation = 'Отклик на другую должность. Отдельное сравнение с целевым профилем возможно.'
    elif not normalized:
        explanation = 'Исходная публикация неизвестна. Требуется основание для включения в основной отбор.'
    else:
        explanation = 'Соответствие публикации целевому профилю пока не подтверждено.'
    snapshot = {'position_code': position_code, 'posting_title': posting_title,
                'normalized_title': normalized, 'mapping': rule.model_dump() if rule else None}
    return Applicability(status=status, reason=reason, explanation=explanation, policy_version=policy.version,
                         policy_hash=digest(policy.model_dump()), input_hash=digest(snapshot), snapshot=snapshot)
