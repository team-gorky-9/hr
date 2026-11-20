"""New drafts use existing DB row schemas; package versions have a separate input."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator

from app.schemas.requirements import CompetencyIn, FormalRequirementIn, ProfileSourceIn
from app.schemas.requirement_groups import validate_groups
from .errors import invalid


class ProfileDraft(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    schema_version: Literal['requirement-draft/1.0']
    position_code: str = Field(min_length=1, max_length=64)
    is_synthetic: StrictBool
    sources: list[ProfileSourceIn] = Field(default_factory=list)
    formal_requirements: list[FormalRequirementIn]
    competencies: list[CompetencyIn]
    note: str | None = None

    @model_validator(mode='after')
    def check_rows(self):
        rows = [*self.formal_requirements, *self.competencies,
                *(r for c in self.competencies for r in c.indicators)]
        if not rows or len({r.key for r in rows}) != len(rows):
            raise ValueError('empty profile or duplicate keys')
        if len({c.code for c in self.competencies}) != len(self.competencies):
            raise ValueError('duplicate competency codes')
        validate_groups(self.competencies)
        return self


BOOL_FIELDS = {'is_synthetic', 'is_mandatory', 'is_primary', 'minimum_defined', 'excluded_from_scoring'}
INT_FIELDS = {'min_months', 'target_level_min', 'target_level_max', 'sort_order'}
SAFE_FIELDS = set(ProfileDraft.model_fields) | BOOL_FIELDS | INT_FIELDS | {
    'params', 'indicators', 'key', 'kind', 'description', 'name', 'text', 'code', 'rank', 'origin',
    'source_refs', 'source_document_id', 'address', 'quote', 'verification', 'check_stage', 'acceptance',
    'met', 'not_met', 'unknown', 'limit', 'alternatives', 'scope', 'requires_requirement', 'role',
    'observed_revision', 'same_as', 'level', 'enrollment_status', 'field_group', 'field_examples',
    'field_exclusions', 'degree_fields', 'retraining_fields', 'relevance_hint',
}


def safe_path(parts):
    return '.'.join(str(p) if isinstance(p, int) or p in SAFE_FIELDS else '*' for p in parts) or 'profile'


def check_scalar_types(value, path=()):
    # Existing DB schemas coerce strings; JSON commands must not turn "false" into a policy flag.
    if isinstance(value, dict):
        for key, item in value.items():
            if key in BOOL_FIELDS and type(item) is not bool:
                raise invalid(safe_path((*path, key)))
            if key in INT_FIELDS and item is not None and type(item) is not int:
                raise invalid(safe_path((*path, key)))
            check_scalar_types(item, (*path, key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            check_scalar_types(item, (*path, i))


def validate_draft(data) -> ProfileDraft:
    if isinstance(data, ProfileDraft):
        data = data.model_dump(mode='json')
    check_scalar_types(data)
    try:
        return ProfileDraft.model_validate(data)
    except ValidationError as error:
        first = error.errors(include_input=False, include_context=False)[0]
        raise invalid(safe_path(first['loc'])) from error
