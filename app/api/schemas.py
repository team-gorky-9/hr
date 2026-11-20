"""Схемы ответов API Этапа 1 (контракт api.md v0.2, раздел 2).

Это внешние DTO: в них нет ни одного поля candidate_pii и нет source_documents.raw_text
(слепой режим). Названия полей совпадают с примерами контракта.
"""
import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.db.enums import (
    Channel,
    CheckResult,
    CheckStage,
    CompetencyRank,
    FormalRequirementKind,
    RequirementStatus,
    VacancyStatus,
    VerificationMethod,
)


class Contour(StrEnum):
    """Какие данные показывать (api.md п. 1, v0.2): рабочие — по умолчанию, учебные — явно."""
    WORKING = "working"
    TRAINING = "training"


class AssessmentStatus(StrEnum):
    READY = "ready"                              # актуальная оценка по текущему тексту и утверждённому профилю
    STALE = "stale"                              # оценка есть, но текст или утверждённый профиль сменились
    NOT_ASSESSED = "not_assessed"                # утверждённый профиль есть, оценки нет
    NO_APPROVED_PROFILE = "no_approved_profile"  # у должности нет утверждённого профиля в этом контуре


class StaleReason(StrEnum):
    TEXT_CHANGED = "text_changed"        # оценка по прежней версии очищенного текста
    PROFILE_CHANGED = "profile_changed"  # оценка по прежней версии профиля требований


# --- Общие --------------------------------------------------------------------

class HealthOut(BaseModel):
    status: str
    db: str


class EvidenceOut(BaseModel):
    """Цитата: границы в кодовых точках (как в базе, для Python) и в UTF-16 (для JavaScript)."""
    candidate_text_id: uuid.UUID
    quote: str
    start: int
    end: int
    utf16_start: int
    utf16_end: int


# --- GET /vacancies -----------------------------------------------------------

class VacancyOut(BaseModel):
    vacancy_id: uuid.UUID
    position_id: uuid.UUID
    position_code: str
    title: str
    employer: str
    is_municipal_service: bool
    channel: Channel
    status: VacancyStatus
    approved_profile_id: uuid.UUID | None
    approved_profile_version: int | None
    approved_profile_is_training: bool | None
    applications_count: int


class VacancyListOut(BaseModel):
    items: list[VacancyOut]


# --- GET /vacancies/{id}/applications -----------------------------------------

class ApplicationListItemOut(BaseModel):
    application_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_code: str
    headline: str | None
    is_training: bool
    current_stage_code: str
    current_stage_title: str
    applied_at: date | None
    assessment_status: AssessmentStatus
    formal_result: CheckResult | None
    formal_preliminary: bool | None
    overall_score: int | None
    missing_count: int | None


class ApplicationListOut(BaseModel):
    vacancy_id: uuid.UUID
    total: int
    items: list[ApplicationListItemOut]


# --- GET /applications/{id} ---------------------------------------------------

class VacancyBriefOut(BaseModel):
    vacancy_id: uuid.UUID
    position_code: str
    title: str
    is_municipal_service: bool


class StageOut(BaseModel):
    code: str
    title: str
    is_final: bool


class CandidateOut(BaseModel):
    candidate_id: uuid.UUID
    code: str
    headline: str | None
    current_text_id: uuid.UUID | None
    is_training: bool
    pii_hidden: bool = True
    # Карточка — документ app.schemas.card.CandidateCard (уже без ПДн) + version и extractor.
    card: dict[str, Any] | None


class AlternativeOut(BaseModel):
    key: str
    result: CheckResult
    evidence: list[EvidenceOut]


class FormalCheckOut(BaseModel):
    requirement_id: uuid.UUID
    key: str
    kind: FormalRequirementKind
    description: str
    is_mandatory: bool
    verification: VerificationMethod
    check_stage: CheckStage
    source_quote: str | None
    result: CheckResult
    basis: VerificationMethod
    is_preliminary: bool
    confirmed_by: str | None
    explanation: str | None
    evidence: list[EvidenceOut]
    alternatives: list[AlternativeOut]


class CompetencyScoreOut(BaseModel):
    competency_id: uuid.UUID
    rank: CompetencyRank | None
    code: str
    name: str
    target_level_min: int | None
    target_level_max: int | None
    level: int | None
    explanation: str | None
    evidence: list[EvidenceOut]


class AssessmentOut(BaseModel):
    assessment_id: uuid.UUID
    version: int
    profile_id: uuid.UUID
    profile_version: int
    profile_status: RequirementStatus
    is_training: bool
    formal_preliminary: bool
    model: str
    created_at: datetime
    is_stale: bool
    stale_reason: StaleReason | None
    formal_result: CheckResult
    overall_score: int | None
    summary: str | None
    formal_checks: list[FormalCheckOut]
    competency_scores: list[CompetencyScoreOut]


class ApplicationDetailOut(BaseModel):
    application_id: uuid.UUID
    # Пусто только у записей «История общения» без вакансии на платформе.
    vacancy: VacancyBriefOut | None
    stage: StageOut
    candidate: CandidateOut
    assessment_status: AssessmentStatus
    assessment: AssessmentOut | None


# --- GET /candidate-texts/{id} ------------------------------------------------

class CandidateTextOut(BaseModel):
    candidate_text_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_code: str
    is_training: bool
    version: int
    is_current: bool
    redaction_method: str
    text: str
    char_length: int
    utf16_length: int
