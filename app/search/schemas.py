"""DTO HTTP-поиска, docs/contracts/search.md."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.schemas import Contour
from app.db.enums import ApplicationSource, ChunkKind
from app.db.repository import normalize_skill
from app.schemas.card import EducationLevel
from app.search.text import exact_tokens


FilterValue = Annotated[str, Field(min_length=1, max_length=80)]


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skills: list[FilterValue] = Field(default_factory=list, max_length=20)
    skill_match: Literal["all", "any"] = "all"
    education_levels: list[EducationLevel] = Field(default_factory=list, max_length=4)
    in_reserve: bool | None = Field(default=None, strict=True)
    required_terms: list[FilterValue] = Field(default_factory=list, max_length=12)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, values: list[str]) -> list[str]:
        if any(not normalize_skill(value) for value in values):
            raise ValueError("Укажите непустой навык")
        return [value.strip() for value in values]

    @field_validator("required_terms")
    @classmethod
    def validate_terms(cls, values: list[str]) -> list[str]:
        seen = set()
        terms = []
        for value in values:
            key = exact_tokens(value)
            if not key:
                raise ValueError("Обязательный термин должен содержать букву или цифру")
            if key not in seen:
                terms.append(value.strip())
                seen.add(key)
        return terms


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=512)
    contour: Contour = Contour.WORKING
    limit: int = Field(default=10, ge=1, le=50, strict=True)
    filters: SearchFilters = Field(default_factory=SearchFilters)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if query and not any(char.isalnum() for char in query):
            raise ValueError("Запрос должен содержать букву или цифру")
        return query

    @model_validator(mode="after")
    def require_condition(self):
        filters = self.filters
        if not (self.query or filters.skills or filters.education_levels
                or filters.in_reserve is not None or filters.required_terms):
            raise ValueError("Введите запрос или задайте хотя бы один фильтр")
        return self


class SearchEvidence(BaseModel):
    candidate_text_id: UUID
    chunk_kind: ChunkKind
    fragment: str
    start_offset: int
    end_offset: int
    utf16_start: int
    utf16_end: int


class SearchFilterMatch(BaseModel):
    kind: Literal["skills", "education", "reserve"]
    source: Literal["candidate_skills", "candidate_cards.education_level", "reserve_entries"]
    values: list[str | bool]


class SearchApplication(BaseModel):
    application_id: UUID
    source: ApplicationSource
    vacancy_id: UUID | None
    position_id: UUID | None
    position_title: str | None
    posting_title: str | None
    external_position_title: str | None
    applied_at: date | None
    stage_code: str
    is_active: bool


MatchKind = Literal["lexical", "semantic", "hybrid", "exact", "filters"]
SearchMode = Literal["hybrid", "lexical", "filters"]
SemanticStatus = Literal["ready", "partial", "unavailable", "not_requested"]


class SearchHit(BaseModel):
    candidate_id: UUID
    candidate_code: str
    score: float | None
    match_kind: MatchKind
    evidence: SearchEvidence | None
    matched_required_terms: list[str]
    filter_matches: list[SearchFilterMatch]
    in_reserve: bool
    applications: list[SearchApplication]


class SearchResponse(BaseModel):
    contour: Contour
    mode: SearchMode
    semantic_status: SemanticStatus
    items: list[SearchHit]


class SearchError(BaseModel):
    code: str
    message: str
    details: dict


class SearchErrorResponse(BaseModel):
    error: SearchError
