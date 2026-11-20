"""Схемы запросов и ответов API (контракт api.md v0.3: раздел 2 — чтение, раздел 3 — действия кадровика, резерв, воронка).

Это внешние DTO: в них нет ни одного поля candidate_pii и нет source_documents.raw_text
(слепой режим). Названия полей совпадают с примерами контракта.
"""
import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from app.assessment.applicability import Applicability
from app.postings.service import ApplicationResolution
# Статусы оценки — общие с моделью чтения кросс-оценок (app.assessment.state).
from app.assessment.state import AssessmentStatus, StaleReason  # noqa: F401
from app.schemas.competency_details import CompetencyDetails, IndicatorResult, ProfileCounters

from pydantic import BaseModel, Field

from app.db.enums import (
    ApplicationSource,
    Channel,
    CheckResult,
    CheckStage,
    CompetencyRank,
    DeadlineExtensionReason,
    FeedbackOutcome,
    FormalRequirementKind,
    HandoffChannel,
    HandoffStatus,
    ProcessFactStatus,
    RejectionSide,
    RequirementStatus,
    ReserveStatus,
    VacancyStatus,
    VerificationMethod,
)


class Contour(StrEnum):
    """Какие данные показывать (api.md п. 1, v0.2): рабочие — по умолчанию, учебные — явно."""
    WORKING = "working"
    TRAINING = "training"


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
    posting_resolution: ApplicationResolution | None = None
    posting_title: str | None = None
    target_position_code: str | None = None
    applicability: Applicability | None = None
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
    rank_group: Literal["ready", "clarify", "not_met", "needs_action"]
    rank_position: int | None = None
    rank_reason: str


class ApplicationListOut(BaseModel):
    imported_count: int = 0
    confirmed_count: int = 0
    mismatch_count: int = 0
    unresolved_count: int = 0
    not_covered_count: int = 0
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


class IndicatorResultOut(IndicatorResult):
    evidence: list[EvidenceOut]


class CompetencyDetailsOut(CompetencyDetails):
    indicators: list[IndicatorResultOut]


class CompetencyScoreOut(BaseModel):
    details: CompetencyDetailsOut | None = None
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
    competency_summary: ProfileCounters | None = None
    algorithm_version: str | None = None
    calculation_as_of: str | None = None
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
    posting_resolution: ApplicationResolution | None = None
    posting_title: str | None = None
    target_position_code: str | None = None
    applicability: Applicability | None = None
    application_id: uuid.UUID
    # Пусто только у записей «История общения» без вакансии на платформе.
    vacancy: VacancyBriefOut | None
    stage: StageOut
    candidate: CandidateOut
    assessment_status: AssessmentStatus
    assessment: AssessmentOut | None


class PostingSnapshotIn(BaseModel):
    application_ids: list[uuid.UUID] = Field(min_length=1, max_length=5000)


class ComparisonOut(BaseModel):
    posting_resolution: ApplicationResolution | None = None
    purpose: Literal['comparison'] = 'comparison'
    application_id: uuid.UUID
    candidate_id: uuid.UUID
    posting_title: str | None
    target_position_code: str
    profile_id: uuid.UUID
    applicability: Applicability | None
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


# =============================================================================
# Этап 2: действия кадровика, резерв, кросс-оценки, воронка (api.md v0.3, раздел 3)
# =============================================================================

class UserBriefOut(BaseModel):
    """Кто действовал: логин и роль учётки (не ПДн кандидата)."""
    login: str
    role: str


# --- Справочники ----------------------------------------------------------------

class StageRefOut(BaseModel):
    code: str
    title: str
    sort_order: int
    is_final: bool


class StageRefListOut(BaseModel):
    items: list[StageRefOut]


class RejectionReasonOut(BaseModel):
    code: str
    title: str
    side: RejectionSide


class RejectionReasonListOut(BaseModel):
    items: list[RejectionReasonOut]


# --- Этапы и история --------------------------------------------------------------

class HandoffIn(BaseModel):
    recipient_user_id: uuid.UUID | None = None
    recipient_name: str | None = None
    recipient_department: str | None = None
    channel: HandoffChannel
    handed_off_at: datetime | None = None
    summary_revision: str = Field(min_length=1)
    request_id: uuid.UUID


class StageMoveIn(BaseModel):
    to_stage_code: str = Field(min_length=1)
    # Последний seq истории, который видел кадровик (GET /history → last_seq). Если отклик
    # с тех пор изменили в другом окне — 409 STALE_STAGE_FORM.
    expected_seq: int
    comment: str | None = None
    # Обязательна для перехода в rejected / withdrawn, запрещена для остальных этапов.
    rejection_reason_code: str | None = None
    # Перескок вперёд или возврат назад: кадровик подтверждает и пишет причину в comment.
    confirm_skip: bool = False
    # Обязателен при переводе в sent_to_department, запрещён для остальных этапов (workflow-01).
    handoff: HandoffIn | None = None


class StageEventOut(BaseModel):
    seq: int
    from_stage: StageOut | None
    to_stage: StageOut
    rejection_reason: RejectionReasonOut | None
    actor: UserBriefOut | None
    comment: str | None
    created_at: datetime


class StageMoveOut(BaseModel):
    application_id: uuid.UUID
    stage: StageOut
    event: StageEventOut  # event.seq — новый expected_seq для следующего перевода
    handoff: "HandoffAttemptOut | None" = None


class StageHistoryOut(BaseModel):
    application_id: uuid.UUID
    source: ApplicationSource
    stage: StageOut
    last_seq: int | None
    items: list[StageEventOut]


# --- Кросс-оценки -----------------------------------------------------------------
# Данные собирает app.assessment.cross.cross_assessments (ai-02, Илья); API только
# проверяет права и переводит результат в эти DTO.

class CrossEvidenceOut(BaseModel):
    candidate_text_id: uuid.UUID
    quote: str
    start: int
    end: int
    utf16_start: int  # по тексту, на который ссылается цитата (в том числе прежней версии)
    utf16_end: int


class CrossFormalCheckOut(BaseModel):
    requirement_key: str
    description: str
    is_mandatory: bool
    check_stage: CheckStage
    result: CheckResult
    basis: VerificationMethod
    is_preliminary: bool
    evidence: list[CrossEvidenceOut]


class CrossCompetencyOut(BaseModel):
    competency_id: uuid.UUID
    code: str
    name: str
    rank: CompetencyRank | None
    target_level_min: int | None
    target_level_max: int | None
    level: int | None
    explanation: str | None
    mandatory: dict[str, Any] | None  # счётчики confirmed/contradicted/no_info/total из details
    desired: dict[str, Any] | None
    evidence: list[CrossEvidenceOut]


class CrossAssessmentOut(BaseModel):
    assessment_id: uuid.UUID
    version: int
    profile_id: uuid.UUID       # профиль самой оценки (при profile_changed — прежняя версия)
    profile_version: int
    formal_result: CheckResult
    formal_preliminary: bool
    overall_score: int | None
    summary: str | None
    gaps: list[str]  # требования этапа screening с результатом unknown
    formal_checks: list[CrossFormalCheckOut]
    competencies: list[CrossCompetencyOut]


class CrossApplicationOut(BaseModel):
    application_id: uuid.UUID
    vacancy_id: uuid.UUID | None
    position_code: str | None
    source: ApplicationSource
    posting_title: str | None
    current_stage_code: str


class CrossVacancyOut(BaseModel):
    """Вакансия должности и отклик кандидата на неё, если есть."""
    vacancy_id: uuid.UUID
    title: str
    channel: Channel
    status: VacancyStatus
    application_id: uuid.UUID | None
    application_source: ApplicationSource | None
    application_stage_code: str | None


class CrossAssessmentItemOut(BaseModel):
    position_id: uuid.UUID
    position_code: str
    position_title: str
    is_municipal_service: bool
    profile_id: uuid.UUID       # утверждённый сейчас профиль должности
    profile_version: int
    is_training: bool
    # Есть ли у кандидата прямой отклик (source = response) на вакансию этой должности.
    is_source_position: bool
    vacancies: list[CrossVacancyOut]
    assessment_status: AssessmentStatus
    stale_reason: StaleReason | None
    assessment: CrossAssessmentOut | None


class CrossAssessmentListOut(BaseModel):
    candidate_id: uuid.UUID
    candidate_code: str
    is_training: bool
    current_text_id: uuid.UUID | None
    applications: list[CrossApplicationOut]
    items: list[CrossAssessmentItemOut]
    empty_reason: str | None  # no_approved_profiles — пустой список не ошибка


# --- Кадровый резерв --------------------------------------------------------------

class ReserveIn(BaseModel):
    candidate_id: uuid.UUID
    position_id: uuid.UUID | None = None
    competency_area: str | None = None
    source_application_id: uuid.UUID | None = None
    # Обоснование профессиональной пригодности и основание повторного контакта — обязательны
    # (проверяет сервис: 422 RESERVE_BASIS_REQUIRED в общем формате).
    reason: str | None = None
    contact_basis: str | None = None
    valid_until: date | None = None


class ReserveWithdrawIn(BaseModel):
    reason: str | None = None


class ReserveEntryOut(BaseModel):
    reserve_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_code: str
    headline: str | None
    is_training: bool
    position_id: uuid.UUID | None
    competency_area: str | None
    source_application_id: uuid.UUID | None
    reason: str | None
    contact_basis: str | None
    status: ReserveStatus
    added_by: UserBriefOut | None
    added_at: datetime
    valid_until: date | None
    ended_at: datetime | None
    end_reason: str | None
    ended_by: UserBriefOut | None


class ReserveCreatedOut(BaseModel):
    created: bool  # false — у кандидата уже есть действующая запись на эту цель, вернули её
    entry: ReserveEntryOut


class ReserveListOut(BaseModel):
    position_id: uuid.UUID
    position_code: str
    total: int
    items: list[ReserveEntryOut]


# --- Воронка ----------------------------------------------------------------------

class FunnelStageOut(BaseModel):
    code: str
    title: str
    sort_order: int
    is_final: bool
    current_count: int  # уникальные отклики, которые сейчас на этом этапе
    reached_count: int  # отклики, у которых есть переход на этот этап (stage_events)


class FunnelClosureOut(BaseModel):
    """Решения о закрытии за период: переход в hired / rejected / withdrawn с причиной."""
    stage_code: str
    stage_title: str
    reason_code: str | None  # null — причина не указана (исторические записи) или найм
    reason_title: str
    side: RejectionSide | None
    count: int


class OpenWaitsByDepartmentOut(BaseModel):
    department: str
    total: int
    unique_applications: int
    due_soon_total: int = 0
    overdue_total: int = 0
    extended_total: int = 0
    max_wait_hours: float
    median_wait_hours: float


class OpenWaitsOut(BaseModel):
    total: int
    unique_applications: int
    due_soon_total: int = 0
    overdue_total: int = 0
    extended_total: int = 0
    max_wait_hours: float | None = None
    median_wait_hours: float | None = None
    by_department: list[OpenWaitsByDepartmentOut] = Field(default_factory=list)


class FunnelOut(BaseModel):
    as_of: datetime  # момент среза
    contour: Contour
    vacancy_id: uuid.UUID | None
    position_id: uuid.UUID | None
    period_from: date | None
    period_to: date | None
    timezone: str  # в каком поясе даты периода превращаются в границы суток
    total_applications: int
    stages: list[FunnelStageOut]
    closures: list[FunnelClosureOut]
    closures_without_reason: int
    open_waits: OpenWaitsOut


# --- Передача руководителю и ответы департамента (workflow-01) -------------------

class HandoffSummaryNoteOut(BaseModel):
    seq: int
    stage_code: str
    stage_title: str
    actor: UserBriefOut | None
    created_at: datetime
    text: str


class HandoffSummaryQuestionOut(BaseModel):
    question_id: uuid.UUID
    gap: str | None
    question: str
    answer_text: str | None


class HandoffSummaryInterviewItemOut(BaseModel):
    interview_id: uuid.UUID
    kind: str
    result: str
    held_at: datetime | None
    summary: str | None
    questions: list[HandoffSummaryQuestionOut] = Field(default_factory=list)


class HandoffSummaryPayloadOut(BaseModel):
    application_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_code: str
    is_training: bool
    vacancy: VacancyBriefOut | None
    posting_title: str | None
    stage: StageOut
    versions: dict[str, Any]
    assessment_status: AssessmentStatus
    stale_reason: StaleReason | None
    candidate_brief: dict[str, Any]
    formal_summary: dict[str, Any] | None
    competencies: list[dict[str, Any]] = Field(default_factory=list)
    gaps: dict[str, list[str]]
    interview_notes: list[HandoffSummaryInterviewItemOut] = Field(default_factory=list)
    hr_notes: list[HandoffSummaryNoteOut] = Field(default_factory=list)
    omitted_notes_count: int = 0
    referenced_text_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HandoffSummaryOut(BaseModel):
    summary_revision: str
    summary: HandoffSummaryPayloadOut
    markdown: str
    from_snapshot: bool = False
    attempt_id: uuid.UUID | None = None


class HandoffFeedbackIn(BaseModel):
    attempt_id: uuid.UUID
    outcome: FeedbackOutcome
    contact_status: ProcessFactStatus = ProcessFactStatus.NOT_REPORTED
    interview_status: ProcessFactStatus = ProcessFactStatus.NOT_REPORTED
    interview_held: bool | None = None
    confirmed_competencies: list[str] = Field(default_factory=list)
    gaps: str | None = None
    rejection_reason_code: str | None = None
    keep_in_reserve: bool | None = None
    comment: str | None = None
    response_channel: HandoffChannel | None = None
    reported_by_name: str | None = None
    reported_by_user_id: uuid.UUID | None = None
    reported_at: datetime | None = None
    supersedes_id: uuid.UUID | None = None
    request_id: uuid.UUID


class HandoffFeedbackOut(BaseModel):
    feedback_id: uuid.UUID
    application_id: uuid.UUID
    attempt_id: uuid.UUID | None
    revision: int
    supersedes_id: uuid.UUID | None
    is_current: bool
    origin_unrecorded: bool
    outcome: FeedbackOutcome
    contact_status: ProcessFactStatus
    interview_status: ProcessFactStatus
    interview_held: bool | None
    confirmed_competencies: list[str]
    gaps: str | None
    rejection_reason: RejectionReasonOut | None
    keep_in_reserve: bool | None
    comment: str | None
    response_channel: HandoffChannel | None
    reported_by_name: str | None
    reported_by: UserBriefOut | None
    reported_at: datetime | None
    recorded_by: UserBriefOut | None
    received_at: datetime
    received_after_due: bool | None = None


class HandoffFeedbackCreatedOut(BaseModel):
    created: bool
    feedback: HandoffFeedbackOut


class HandoffFeedbackListOut(BaseModel):
    application_id: uuid.UUID
    total: int
    items: list[HandoffFeedbackOut]


DeadlineStatus = Literal["on_track", "due_soon", "overdue", "responded", "closed_without_response"]


class HandoffDeadlineExtendIn(BaseModel):
    new_due_date: date
    expected_due_date: date
    reason_code: DeadlineExtensionReason
    comment: str | None = None
    request_id: uuid.UUID


class HandoffDeadlineExtensionOut(BaseModel):
    extension_id: uuid.UUID
    seq: int
    previous_due_date: date
    new_due_date: date
    previous_reminder_date: date
    new_reminder_date: date
    was_overdue: bool
    reason_code: DeadlineExtensionReason
    reason_title: str
    comment: str | None
    actor: UserBriefOut | None
    created_at: datetime


class HandoffAttemptOut(BaseModel):
    attempt_id: uuid.UUID
    application_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_code: str
    is_training: bool
    vacancy_id: uuid.UUID | None
    vacancy_title: str | None
    position_code: str | None
    stage_event_id: uuid.UUID | None
    recipient_user: UserBriefOut | None
    recipient_name: str
    recipient_department: str
    channel: HandoffChannel
    handed_off_at: datetime
    initial_due_date: date
    due_date: date
    reminder_date: date
    deadline_business_days: int
    reminder_business_day: int
    extensions_count: int = 0
    deadline_status: DeadlineStatus
    business_days_left: int | None = None
    is_overdue: bool = False
    overdue_notice: str | None = None
    cross_assessments_url: str | None = None
    answered_late: bool | None = None
    response_business_days: int | None = None
    created_by: UserBriefOut | None
    created_at: datetime
    summary_revision: str
    status: HandoffStatus
    closed_at: datetime | None
    close_reason: str | None
    wait_hours: float
    latest_feedback: HandoffFeedbackOut | None


class HandoffAttemptDetailOut(HandoffAttemptOut):
    summary: HandoffSummaryPayloadOut
    markdown: str
    feedback_history: list[HandoffFeedbackOut]
    deadline_extensions: list[HandoffDeadlineExtensionOut] = Field(default_factory=list)


class HandoffDeadlineExtendedOut(BaseModel):
    created: bool
    extension: HandoffDeadlineExtensionOut
    attempt: HandoffAttemptOut


class HandoffCreateIn(BaseModel):
    expected_seq: int
    handoff: HandoffIn


class HandoffCreatedOut(BaseModel):
    created: bool
    attempt: HandoffAttemptOut


class HandoffListOut(BaseModel):
    as_of: datetime
    total: int
    items: list[HandoffAttemptOut]


StageMoveOut.model_rebuild()


# --- Гайд интервью и ответы (interview.md v0.4, задача interview-01) ----------------

class InterviewKindIn(StrEnum):
    PHONE = "phone"
    DEPARTMENT = "department"


class AnswerSourceIn(StrEnum):
    """Источник ответа через API; unknown бывает только у перенесённых миграцией."""
    PHONE = "phone"
    IN_PERSON = "in_person"
    WRITTEN = "written"


class ConfirmBasisIn(StrEnum):
    """Основание подтверждения человеком; resume пишет только оценщик."""
    DOCUMENTS = "documents"
    INTERVIEW = "interview"
    TEST = "test"


class InterviewUserOut(BaseModel):
    user_id: uuid.UUID
    login: str


class InterviewGuideIn(BaseModel):
    kind: InterviewKindIn = InterviewKindIn.PHONE
    regenerate: bool = False
    request_id: uuid.UUID


class CriterionOut(BaseModel):
    good_answer: str | None = None
    insufficient_answer: str | None = None


class AnswerOut(BaseModel):
    answer_id: uuid.UUID
    question_id: uuid.UUID
    revision: int
    text: str
    source: str
    author: InterviewUserOut | None = None   # null — ответ перенесён из старых заметок, автор не зафиксирован
    created_at: datetime
    previous_answer_id: uuid.UUID | None = None
    carried_over: bool = False


class ResolvedByOut(BaseModel):
    assessment_id: uuid.UUID
    assessment_version: int
    requirement_id: uuid.UUID
    result: CheckResult
    basis: VerificationMethod
    confirmed_by: InterviewUserOut | None = None


class InterviewQuestionOut(BaseModel):
    question_id: uuid.UUID
    kind: str
    sort_order: int
    question: str
    criterion: CriterionOut | None = None
    author: str
    gap: str | None = None
    gap_ref_id: str | None = None
    rubric_question_id: uuid.UUID | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["open", "answered", "resolved"]
    resolved_by: ResolvedByOut | None = None
    carried_from_question_id: uuid.UUID | None = None
    answer: AnswerOut | None = None


class DocumentRequestOut(BaseModel):
    requirement_id: uuid.UUID
    requirement_key: str
    title: str
    reason: str | None = None


class InterviewGuideOut(BaseModel):
    interview_id: uuid.UUID
    guide_id: uuid.UUID
    application_id: uuid.UUID
    kind: str
    guide_version: int
    is_training: bool
    assessment_id: uuid.UUID | None = None       # базовая оценка, по которой собран гайд
    assessment_version: int | None = None
    current_assessment_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    profile_version: int | None = None
    rubric_status: Literal["draft", "approved"] | None = None
    is_stale: bool
    stale_reason: Literal["assessment_changed", "assessment_stale", "profile_changed", "rubric_changed"] | None = None
    prompt_version: str | None = None
    model_calls: int
    created_at: datetime
    created_by: InterviewUserOut | None = None
    core: list[InterviewQuestionOut]
    clarifications: list[InterviewQuestionOut]
    document_requests: list[DocumentRequestOut]
    uncovered_gaps: list[dict[str, Any]]


class AnswerIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    source: AnswerSourceIn
    expected_revision: int = Field(ge=0)
    request_id: uuid.UUID


class AnswerListOut(BaseModel):
    question_id: uuid.UUID
    items: list[AnswerOut]


class ConfirmIn(BaseModel):
    result: CheckResult
    basis: ConfirmBasisIn
    comment: str = Field(min_length=1)
    answer_id: uuid.UUID | None = None
    request_id: uuid.UUID
