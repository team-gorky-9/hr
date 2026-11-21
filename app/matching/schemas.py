"""DTO /api/v1/matching, docs/contracts/wave-3-matching-stage-1.md (раздел 3A)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.schemas import Contour
from app.search.schemas import SearchFilters, SearchHit, SearchMode, SemanticStatus


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VacancyRef(Strict):
    system: Literal["catalog", "legacy-hr"]
    id: UUID


class ProfileRef(Strict):
    """Точный профиль требований. Сопоставляется только legacy-hr: id и версия сохранённого профиля."""
    system: Literal["catalog", "legacy-hr"]
    id: UUID
    version: int = Field(ge=1)


class VacancySnapshot(Strict):
    ref: VacancyRef
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    # Текст объявления хранится целиком и в запрос поиска не подставляется: запрос выбирает HR.
    description: str = Field(min_length=1, max_length=50_000)
    position_code: str = Field(min_length=1, max_length=80)
    status: Literal["published", "closed"]
    contour: Contour
    observed_at: datetime
    profile_ref: ProfileRef | None = None
    # Нужен для 3A (поиск людей); в списке вакансий 3B может быть пустым.
    search_query: str = Field(default="", max_length=512)

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must include a time zone")
        return value

    @field_validator("search_query")
    @classmethod
    def chosen_query(cls, value: str) -> str:
        """Правила SearchRequest.query: непустой запрос содержит букву или цифру."""
        query = value.strip()
        if query and not any(char.isalnum() for char in query):
            raise ValueError("search_query must contain a letter or a digit")
        return query


class CandidatesForVacancyIn(Strict):
    vacancy: VacancySnapshot
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=10, ge=1, le=50, strict=True)

    @model_validator(mode="after")
    def query_chosen(self):
        if not self.vacancy.search_query:
            raise ValueError("vacancy.search_query is required: HR chooses the description of the work")
        return self


QualificationStatus = Literal["not_evaluated", "met", "unknown", "not_met"]
QualificationReason = Literal[
    "evaluated", "no_profile_ref", "unmapped_profile", "profile_not_found", "profile_mismatch",
    "profile_not_current", "not_assessed", "assessment_stale",
]


class CandidateMatch(SearchHit):
    """Строка действующего search-контракта плюс отдельный статус формальной оценки по точному профилю.
    Поисковое совпадение формальным допуском не является: без оценки — not_evaluated."""
    qualification_status: QualificationStatus
    qualification_reason: QualificationReason
    assessment_id: UUID | None


class CandidatesForVacancyOut(BaseModel):
    vacancy_ref: VacancyRef
    vacancy_revision: int
    observed_at: datetime
    source_mode: Literal["provided", "catalog_api"]
    contour: Contour
    unit: Literal["candidate_record"] = "candidate_record"
    profile_ref: ProfileRef | None
    search_query: str
    mode: SearchMode
    semantic_status: SemanticStatus
    matching_status: Literal["completed"] = "completed"
    items: list[CandidateMatch]


# --- 3B · вакансии по присланному резюме -------------------------------------------------------

class VacanciesForCandidateIn(Strict):
    candidate_id: UUID
    contour: Contour
    vacancies: list[VacancySnapshot] = Field(min_length=1, max_length=50)
    limit: int = Field(default=10, ge=1, le=50, strict=True)

    @model_validator(mode="after")
    def unique_refs(self):
        refs = [(v.ref.system, v.ref.id) for v in self.vacancies]
        if len(refs) != len(set(refs)):
            raise ValueError("vacancies must not repeat the same ref")
        return self


NeedsEvaluationReason = Literal[
    "no_profile_ref", "unmapped_profile", "profile_not_found", "profile_mismatch", "profile_not_current",
    "not_assessed", "assessment_stale",
]


class VacancyMatch(BaseModel):
    vacancy_ref: VacancyRef
    vacancy_revision: int
    title: str
    profile_ref: ProfileRef
    assessment_status: Literal["ready"]
    formal_result: Literal["met", "unknown", "not_met"]
    assessment_id: UUID
    reason: str


class VacancyNeedsEvaluation(BaseModel):
    vacancy_ref: VacancyRef
    title: str
    reason: NeedsEvaluationReason
    stale_reason: str | None = None


class VacancyExcluded(BaseModel):
    vacancy_ref: VacancyRef
    reason: Literal["closed", "other_contour"]


class VacanciesForCandidateOut(BaseModel):
    candidate_id: UUID
    current_text_id: UUID | None
    contour: Contour
    source_mode: Literal["provided", "catalog_api"]
    items: list[VacancyMatch]
    needs_evaluation: list[VacancyNeedsEvaluation]
    excluded: list[VacancyExcluded]


# --- 3C · подборка HR по новой публикации ------------------------------------------------------

class SuggestionUser(BaseModel):
    user_id: UUID
    login: str


class SuggestionEvidence(BaseModel):
    """Ссылка на версию источника. fragment и границы UTF-16 отдаются, только пока источник доступен."""
    candidate_text_id: UUID
    chunk_kind: str
    start_offset: int
    end_offset: int
    fragment: str | None
    utf16_start: int | None
    utf16_end: int | None


class SuggestionItem(BaseModel):
    candidate_id: UUID
    candidate_code: str | None
    score: float | None
    match_kind: str
    evidence: SuggestionEvidence | None
    # available — текущий текст кандидата; superseded — текст заменён новой версией;
    # unavailable — кандидат или текст удалены/отозваны. Во втором и третьем случае фрагмент не отдаётся.
    source_status: Literal["available", "superseded", "unavailable"]
    matched_required_terms: list[str]
    qualification_status: QualificationStatus
    qualification_reason: QualificationReason
    assessment_id: UUID | None


class SuggestionOut(BaseModel):
    id: UUID
    vacancy_ref: VacancyRef
    vacancy_revision: int
    vacancy_title: str
    observed_at: datetime
    created_at: datetime
    created_by: SuggestionUser | None
    contour: Contour
    source_mode: Literal["provided", "catalog_api"]
    search_query: str
    mode: SearchMode
    semantic_status: SemanticStatus
    items: list[SuggestionItem]
    qualification_note: str
