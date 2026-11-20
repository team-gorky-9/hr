"""Versioned, context-scoped posting decisions; no DB, model calls or fuzzy matching.

Decisions establish which position a response belongs to, never candidate merit.
Registry snapshots are immutable values and can be serialized into an audit manifest.
"""
import hashlib
import json
import os
from datetime import date
from pathlib import Path
import re
from typing import Annotated, Literal, Self
import unicodedata

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator


Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
DecisionState = Literal['confirmed', 'needs_review', 'no_matching_position']


def normalize_title(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def _canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _version(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', value) or '..' in value:
        raise ValueError('registry version must be a safe, nonempty version identifier')
    return value


class RegistryContext(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    dataset_id: str
    # Digest of the ordered source manifest, not the ZIP container's bytes.
    dataset_sha256: Sha256
    channel: str
    source_folder: str
    is_synthetic: bool

    @field_validator('dataset_id', 'channel', 'source_folder')
    @classmethod
    def nonblank_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('context identifiers must not be blank')
        return value


class PostingRule(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    id: Nonempty
    context: RegistryContext
    match_kind: Literal['posting_title', 'folder']
    posting_title: str | None = None
    decision_state: DecisionState
    position_code: Nonempty | None = None
    decision_author: Nonempty | None = None
    decision_date: date | None = None
    decision_basis: Nonempty | None = None
    evidence_refs: tuple[Nonempty, ...] = ()
    reason: Nonempty = 'awaiting_hr'
    excluded_position_codes: tuple[Nonempty, ...] = ()

    @model_validator(mode='after')
    def consistent_decision(self) -> Self:
        if self.match_kind == 'posting_title' and not normalize_title(self.posting_title or ''):
            raise ValueError('posting_title rules require an original title')
        if self.posting_title is not None and not normalize_title(self.posting_title):
            raise ValueError('use null instead of a blank original title')
        if (self.position_code is not None) != (self.decision_state == 'confirmed'):
            raise ValueError('exactly confirmed decisions must name one target position')
        metadata = (self.decision_author, self.decision_date, self.decision_basis)
        if self.decision_state == 'needs_review':
            if any(value is not None for value in metadata):
                raise ValueError('pending review cannot invent decision metadata')
        elif not all(value is not None for value in metadata) or not self.evidence_refs:
            raise ValueError('a terminal decision requires author, date, basis and evidence')
        if self.position_code in self.excluded_position_codes:
            raise ValueError('the confirmed target cannot also be excluded')
        if len(self.excluded_position_codes) != len(set(self.excluded_position_codes)):
            raise ValueError('duplicate excluded position codes')
        return self


class Registry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: Literal['posting-register/1.0']
    version: str
    rules: tuple[PostingRule, ...]

    @field_validator('version')
    @classmethod
    def safe_version(cls, value: str) -> str:
        return _version(value)

    @model_validator(mode='after')
    def unique_rules(self) -> Self:
        ids = [rule.id for rule in self.rules]
        keys = [(rule.context, rule.match_kind, normalize_title(rule.posting_title or '')) for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate posting decision ID')
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate normalized posting rule in the same context')
        return self

    def digest(self) -> str:
        return _digest(self.model_dump(mode='json'))


class Resolution(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    registry_version: str
    registry_hash: Sha256
    decision_id: str | None = None
    decision_state: DecisionState
    reason: str
    posting_title: str | None
    position_code: str | None = None
    source_kind: Literal['docx_response_footer', 'archive_folder'] | None = None
    decision_author: str | None = None
    decision_date: date | None = None
    decision_basis: str | None = None
    excluded_position_codes: tuple[str, ...] = ()
    input_snapshot: dict
    input_hash: Sha256
    explanation: str


_EXPLANATIONS = {
    'missing_posting': 'Исходная публикация неизвестна. Нужен источник публикации.',
    'missing_context': 'Не установлено происхождение отклика. Нужен подтверждённый контекст набора данных.',
    'ambiguous_context': 'У отклика несколько разных контекстов происхождения. Требуется сверка.',
    'contour_mismatch': 'Контур происхождения не совпадает с контуром кандидата.',
    'unknown_publication': 'Для этой публикации в указанном контексте нет решения. Требуется сверка.',
    'ambiguous_mapping': 'Найдено несколько возможных решений о должности. Требуется сверка.',
    'awaiting_hr': 'Соответствие публикации должности пока не подтверждено.',
    'no_matching_position': 'Владелец подтвердил отсутствие подходящей должности в справочнике.',
}


def resolve_posting(registry: Registry, *, posting_title: str | None,
                    contexts: list[RegistryContext], is_synthetic: bool) -> Resolution:
    """Resolve one original title only within a unique, complete provenance context."""
    unique = sorted(set(contexts), key=lambda context: _canonical(context.model_dump(mode='json')))
    snapshot = {'posting_title': posting_title,
                'contexts': [context.model_dump(mode='json') for context in unique],
                'is_synthetic': is_synthetic}
    base = dict(registry_version=registry.version, registry_hash=registry.digest(),
                posting_title=posting_title, input_snapshot=snapshot, input_hash=_digest(snapshot))

    def unresolved(reason: str) -> Resolution:
        return Resolution(**base, decision_state='needs_review', reason=reason,
                          explanation=_EXPLANATIONS[reason])

    title = normalize_title(posting_title or '')
    if not unique:
        return unresolved('missing_context' if title else 'missing_posting')
    if any(context.is_synthetic != is_synthetic for context in unique):
        return unresolved('contour_mismatch')
    if len(unique) != 1:
        return unresolved('ambiguous_context')
    context = unique[0]
    eligible = [rule for rule in registry.rules if rule.context == context and (
        (bool(title) and normalize_title(rule.posting_title or '') == title)
        or (not title and rule.match_kind == 'folder'))]
    if not eligible:
        return unresolved('unknown_publication' if title else 'missing_posting')
    if len(eligible) != 1:
        return unresolved('ambiguous_mapping')
    rule = eligible[0]
    reason = rule.decision_state if rule.decision_state != 'needs_review' else rule.reason
    if rule.decision_state == 'confirmed':
        explanation = f'Соответствие должности подтверждено. Основание: {rule.decision_basis}.'
    else:
        explanation = _EXPLANATIONS.get(reason, _EXPLANATIONS['awaiting_hr'])
    return Resolution(**base, decision_id=rule.id, decision_state=rule.decision_state,
        reason=reason, position_code=rule.position_code,
        source_kind='archive_folder' if rule.match_kind == 'folder' else 'docx_response_footer',
        decision_author=rule.decision_author, decision_date=rule.decision_date,
        decision_basis=rule.decision_basis, excluded_position_codes=rule.excluded_position_codes,
        explanation=explanation)


class RegistryStore:
    """Load explicit immutable versions; current.json is only a selection pointer."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def load(self, version: str | None = None) -> Registry:
        if version is None:
            current = json.loads((self.root / 'current.json').read_text(encoding='utf-8'))
            if not isinstance(current, dict) or set(current) != {'version'}:
                raise ValueError('current.json must contain exactly one version field')
            version = current['version']
        version = _version(version)
        path = (self.root / 'versions' / f'{version}.json').resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('registry file must remain inside its store')
        registry = Registry.model_validate_json(path.read_text(encoding='utf-8'))
        if registry.version != version:
            raise ValueError('registry payload version differs from its filename')
        return registry


def get_default_registry() -> Registry:
    root = os.environ.get('POSTING_REGISTRY_DIR')
    return RegistryStore(Path(root) if root else Path(__file__).with_name('data')).load()
