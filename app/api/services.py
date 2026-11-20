"""Чтение данных для маршрутов Этапа 1 (оценку в DTO собирает и кросс-подбор Этапа 2).

Здесь вся логика API: какой профиль действует, какой статус у оценки, как пересчитать
границы цитат для браузера. Маршруты (routes.py) только принимают параметры и отдают
результат.

Слепой режим: модуль не обращается к CandidatePii и SourceDocument.raw_text — эти
таблицы и поля здесь просто не импортируются и не читаются.
"""
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.errors import ApiError, not_found
from app.assessment.applicability import resolve_applicability
from app.assessment.ranking import rank, rank_input
# Правила актуальности оценки и границ цитат живут в слое оценки и общие с кросс-оценкой ai-02.
from app.assessment.state import AssessmentState, assessment_texts, evidence_with_utf16, resolve_states  # noqa: F401
from app.assessment.verification import utf16_offsets
from app.assessment.counters import aggregate_profile
from app.schemas.competency_details import CompetencyDetails
from app.api.schemas import ComparisonOut, CompetencyDetailsOut
from app.api.schemas import (
    AlternativeOut,
    ApplicationDetailOut,
    ApplicationListItemOut,
    ApplicationListOut,
    AssessmentOut,
    AssessmentStatus,
    CandidateOut,
    CandidateTextOut,
    CompetencyScoreOut,
    Contour,
    EvidenceOut,
    FormalCheckOut,
    StageOut,
    StaleReason,
    VacancyBriefOut,
    VacancyListOut,
    VacancyOut,
)
from app.db import repository as repo
from app.db.enums import CheckResult, RequirementStatus
from app.db.models import (
    Application,
    Assessment,
    Candidate,
    CandidateCard,
    CandidateText,
    Competency,
    FormalCheck,
    FormalRequirement,
    Position,
    RequirementProfile,
    SelectionStage,
    User,
    Vacancy,
)


# --- Границы цитат для JavaScript ----------------------------------------------

def utf16_offset(text: str, index: int) -> int:
    """Позиция в кодовых точках Python → позиция в единицах UTF-16 (как считает String в JS).
    Формула одна на проект: app.assessment.verification.utf16_offsets."""
    return utf16_offsets(text, index, index)[0]


def evidence_out(items: Iterable[dict[str, Any]], texts: dict[uuid.UUID, str]) -> list[EvidenceOut]:
    """Цитаты из JSONB оценки + границы UTF-16 по тексту, на который цитата ссылается
    (общая функция app.assessment.state.evidence_with_utf16)."""
    return [EvidenceOut.model_validate(item) for item in evidence_with_utf16(items, texts)]


# --- Статус оценки -------------------------------------------------------------

def application_state(state: AssessmentState, position_code: str, posting_title: str | None):
    mapping = resolve_applicability(position_code, posting_title)
    if mapping and mapping.status != 'confirmed':
        status = AssessmentStatus.NOT_APPLICABLE if mapping.status == 'mismatch' else AssessmentStatus.MAPPING_REQUIRED
        return AssessmentState(status), mapping
    return state, mapping


def _competency_details_out(details, texts):
    if details is None:
        return None
    return CompetencyDetailsOut.model_validate({**details, 'indicators': [
        {**item, 'evidence': evidence_out(item['evidence'], texts)} for item in details['indicators']]})


def get_comparison(session: Session, application_id: uuid.UUID, profile_id: uuid.UUID) -> ComparisonOut:
    application = session.get(Application, application_id)
    profile = session.get(RequirementProfile, profile_id)
    if application is None or profile is None:
        raise not_found('COMPARISON_NOT_FOUND', 'Отклик или профиль не найден')
    candidate = session.get(Candidate, application.candidate_id)
    if profile.status == RequirementStatus.ARCHIVED or (not candidate.is_synthetic and
            (profile.is_synthetic or profile.status != RequirementStatus.APPROVED)):
        raise ApiError(422, 'PROFILE_NOT_ALLOWED', 'Профиль недоступен в контуре кандидата', {})
    position = session.get(Position, profile.position_id)
    state = resolve_states(session, [candidate.id], profile, position.id, profile.is_synthetic)[candidate.id]
    return ComparisonOut(application_id=application.id, candidate_id=candidate.id,
        posting_title=application.posting_title, target_position_code=position.code, profile_id=profile.id,
        applicability=resolve_applicability(position.code, application.posting_title),
        assessment_status=state.status,
        assessment=assessment_out(session, candidate, state) if state.assessment else None)


# --- GET /vacancies ------------------------------------------------------------

def list_vacancies(session: Session, contour: Contour) -> VacancyListOut:
    synthetic = contour == Contour.TRAINING
    vacancies = session.execute(
        select(Vacancy, Position).join(Position, Position.id == Vacancy.position_id).order_by(Position.code, Vacancy.title)
    ).all()
    # Утверждённый профиль каждой должности в контуре. Это тот же выбор, что делает
    # repo.get_approved_profile (статус approved + контур), только одним запросом на все должности.
    approved = {
        profile.position_id: profile
        for profile in session.scalars(
            select(RequirementProfile).where(
                RequirementProfile.status == RequirementStatus.APPROVED,
                RequirementProfile.is_synthetic == synthetic,
            )
        )
    }
    counts = dict(
        session.execute(
            select(Application.vacancy_id, func.count())
            .join(Candidate, Candidate.id == Application.candidate_id)
            .where(Application.vacancy_id.is_not(None), Candidate.is_synthetic == synthetic)
            .group_by(Application.vacancy_id)
        ).all()
    )
    items = []
    for vacancy, position in vacancies:
        profile = approved.get(position.id)
        items.append(
            VacancyOut(
                vacancy_id=vacancy.id,
                position_id=position.id,
                position_code=position.code,
                title=vacancy.title,
                employer=position.employer,
                is_municipal_service=position.is_municipal_service,
                channel=vacancy.channel,
                status=vacancy.status,
                approved_profile_id=profile.id if profile else None,
                approved_profile_version=profile.version if profile else None,
                approved_profile_is_training=profile.is_synthetic if profile else None,
                applications_count=counts.get(vacancy.id, 0),
            )
        )
    return VacancyListOut(items=items)


# --- GET /vacancies/{id}/applications ------------------------------------------

@dataclass
class ApplicationFilters:
    applicability: str | None = None
    stage_code: str | None = None
    formal_result: CheckResult | None = None
    formal_preliminary: bool | None = None
    assessment_status: AssessmentStatus | None = None


def list_applications(
    session: Session,
    vacancy_id: uuid.UUID,
    contour: Contour,
    filters: ApplicationFilters,
    sort: Literal["fit", "date"] = "date",
) -> ApplicationListOut:
    vacancy = session.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise not_found("VACANCY_NOT_FOUND", "Вакансия не найдена", vacancy_id=vacancy_id)
    if filters.stage_code is not None and session.get(SelectionStage, filters.stage_code) is None:
        raise ApiError(422, "UNKNOWN_STAGE_CODE", "Неизвестный этап отбора", {"stage_code": filters.stage_code})

    synthetic = contour == Contour.TRAINING
    query = (
        select(Application, Candidate, SelectionStage)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(SelectionStage, SelectionStage.code == Application.current_stage_code)
        .where(Application.vacancy_id == vacancy.id, Candidate.is_synthetic == synthetic)
        .order_by(Application.applied_at.desc().nulls_last(), Candidate.code)
    )
    rows = session.execute(query).all()
    position = session.get(Position, vacancy.position_id)

    candidate_ids = [candidate.id for _, candidate, _ in rows]
    profile = repo.get_approved_profile(session, vacancy.position_id, synthetic=synthetic)
    states = resolve_states(session, candidate_ids, profile, vacancy.position_id, synthetic)
    cards = _current_cards(session, candidate_ids)

    assessment_ids = {s.assessment.id for s in states.values() if s.assessment is not None}
    assessments_by_id: dict[uuid.UUID, Assessment] = {}
    profiles_by_id: dict[uuid.UUID, RequirementProfile] = {}
    if assessment_ids:
        assessments_by_id = {
            a.id: a
            for a in session.scalars(
                select(Assessment)
                .where(Assessment.id.in_(assessment_ids))
                .options(
                    selectinload(Assessment.formal_checks),
                    selectinload(Assessment.competency_scores),
                )
            )
        }
        profile_ids = {a.profile_id for a in assessments_by_id.values()}
        if profile_ids:
            profiles_by_id = {
                p.id: p
                for p in session.scalars(
                    select(RequirementProfile)
                    .where(RequirementProfile.id.in_(profile_ids))
                    .options(
                        selectinload(RequirementProfile.formal_requirements),
                        selectinload(RequirementProfile.competencies),
                    )
                )
            }

    row_entries = []
    rank_inputs = []
    counts = dict(confirmed=0, mismatch=0, unresolved=0, not_covered=0)
    for application, candidate, stage in rows:
        state, mapping = application_state(states[candidate.id], position.code, application.posting_title)
        counts[mapping.status if mapping else 'not_covered'] += 1
        loaded_assessment = assessments_by_id.get(state.assessment.id) if state.assessment else None
        assessment_profile = profiles_by_id.get(loaded_assessment.profile_id) if loaded_assessment else None
        rank_inputs.append(
            rank_input(
                key=application.id,
                candidate_code=candidate.code,
                assessment_status=state.status,
                applied_at=application.applied_at,
                assessment=loaded_assessment,
                profile=assessment_profile,
            )
        )
        row_entries.append((application, candidate, stage, state, mapping, loaded_assessment))

    ranked = rank(rank_inputs)
    rank_by_app = {r.key: r for r in ranked}
    fit_order = {r.key: idx for idx, r in enumerate(ranked)}

    items = []
    for application, candidate, stage, state, mapping, assessment in row_entries:
        card = cards.get(candidate.id)
        ranked_item = rank_by_app[application.id]
        item = ApplicationListItemOut(
            posting_title=application.posting_title, target_position_code=position.code, applicability=mapping,
            application_id=application.id,
            candidate_id=candidate.id,
            candidate_code=candidate.code,
            headline=candidate.headline or (card.card.get("headline") if card else None),
            is_training=candidate.is_synthetic or (profile is not None and profile.is_synthetic),
            current_stage_code=stage.code,
            current_stage_title=stage.title,
            applied_at=application.applied_at,
            assessment_status=state.status,
            formal_result=assessment.formal_result if assessment else None,
            formal_preliminary=assessment.formal_preliminary if assessment else None,
            overall_score=assessment.overall_score if assessment else None,
            missing_count=card.missing_count if card else None,
            rank_group=ranked_item.group,
            rank_position=ranked_item.position,
            rank_reason=ranked_item.reason,
        )
        if _matches(item, filters):
            items.append(item)
    if sort == "fit":
        items.sort(key=lambda item: fit_order[item.application_id])
    return ApplicationListOut(vacancy_id=vacancy.id, total=len(items), items=items, imported_count=len(rows),
                              **{f'{key}_count': value for key, value in counts.items()})


def _matches(item: ApplicationListItemOut, filters: ApplicationFilters) -> bool:
    """Фильтры по вычисленным полям: статус считается в Python, поэтому и фильтр здесь."""
    if filters.stage_code is not None and item.current_stage_code != filters.stage_code:
        return False
    if filters.applicability is not None and (item.applicability.status if item.applicability else 'not_covered') != filters.applicability:
        return False
    if filters.assessment_status is not None and item.assessment_status != filters.assessment_status:
        return False
    if filters.formal_result is not None and item.formal_result != filters.formal_result:
        return False
    if filters.formal_preliminary is not None and item.formal_preliminary != filters.formal_preliminary:
        return False
    return True


def _current_cards(session: Session, candidate_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, CandidateCard]:
    if not candidate_ids:
        return {}
    return {
        card.candidate_id: card
        for card in session.scalars(
            select(CandidateCard).where(CandidateCard.candidate_id.in_(candidate_ids), CandidateCard.is_current)
        )
    }


# --- GET /applications/{id} ----------------------------------------------------

def get_application(session: Session, application_id: uuid.UUID) -> ApplicationDetailOut:
    application = session.get(Application, application_id)
    if application is None:
        raise not_found("APPLICATION_NOT_FOUND", "Отклик не найден", application_id=application_id)
    candidate = session.get(Candidate, application.candidate_id)
    stage = session.get(SelectionStage, application.current_stage_code)
    vacancy = session.get(Vacancy, application.vacancy_id) if application.vacancy_id else None
    position = session.get(Position, vacancy.position_id) if vacancy else None

    # Контур карточки задаёт кандидат (развилка Р3): учебный — учебный профиль, реальный — рабочий.
    # Так карточка всегда совпадает со строкой списка своего контура.
    synthetic = candidate.is_synthetic
    profile = repo.get_approved_profile(session, position.id, synthetic=synthetic) if position else None
    if position is None:
        state = AssessmentState(AssessmentStatus.NO_APPROVED_PROFILE)
    else:
        state = resolve_states(session, [candidate.id], profile, position.id, synthetic)[candidate.id]
    mapping = None
    if position:
        state, mapping = application_state(state, position.code, application.posting_title)

    current_text = repo.get_current_text(session, candidate.id)
    card = repo.get_current_card(session, candidate.id)
    card_out = {"version": card.version, "extractor": card.extractor, **card.card} if card else None

    return ApplicationDetailOut(
        posting_title=application.posting_title, target_position_code=position.code if position else None,
        applicability=mapping,
        application_id=application.id,
        vacancy=VacancyBriefOut(
            vacancy_id=vacancy.id,
            position_code=position.code,
            title=vacancy.title,
            is_municipal_service=position.is_municipal_service,
        ) if vacancy else None,
        stage=StageOut(code=stage.code, title=stage.title, is_final=stage.is_final),
        candidate=CandidateOut(
            candidate_id=candidate.id,
            code=candidate.code,
            headline=candidate.headline or (card.card.get("headline") if card else None),
            current_text_id=current_text.id if current_text else None,
            is_training=candidate.is_synthetic,
            card=card_out,
        ),
        assessment_status=state.status,
        assessment=assessment_out(session, candidate, state) if state.assessment else None,
    )


def assessment_out(session: Session, candidate: Candidate, state: AssessmentState) -> AssessmentOut:
    assessment = session.scalar(
        select(Assessment)
        .where(Assessment.id == state.assessment.id)
        .options(selectinload(Assessment.formal_checks), selectinload(Assessment.competency_scores))
    )
    profile = session.get(RequirementProfile, assessment.profile_id)
    requirements = {
        r.id: r for r in session.scalars(select(FormalRequirement).where(FormalRequirement.profile_id == profile.id))
    }
    competencies = {c.id: c for c in session.scalars(select(Competency).where(Competency.profile_id == profile.id))}
    texts = _evidence_texts(session, assessment.formal_checks, assessment.competency_scores)
    confirmers = _user_logins(session, {c.confirmed_by_user_id for c in assessment.formal_checks})

    checks = sorted(assessment.formal_checks, key=lambda c: (requirements[c.requirement_id].sort_order, requirements[c.requirement_id].key))
    scores = sorted(assessment.competency_scores, key=lambda s: (competencies[s.competency_id].sort_order, competencies[s.competency_id].code))
    return AssessmentOut(
        competency_summary=aggregate_profile([CompetencyDetails.model_validate(s.details) if s.details else None
                                              for s in scores]) if len(scores) == len(competencies) else None,
        algorithm_version=assessment.algorithm_version, calculation_as_of=assessment.calculation_as_of,
        assessment_id=assessment.id,
        version=assessment.version,
        profile_id=profile.id,
        profile_version=profile.version,
        profile_status=profile.status,
        is_training=repo.is_training_assessment(candidate, profile),
        formal_preliminary=assessment.formal_preliminary,
        model=assessment.model,
        created_at=assessment.created_at,
        is_stale=state.status == AssessmentStatus.STALE,
        stale_reason=state.stale_reason,
        formal_result=assessment.formal_result,
        overall_score=assessment.overall_score,
        summary=assessment.summary,
        formal_checks=[_formal_check_out(c, requirements[c.requirement_id], texts, confirmers) for c in checks],
        competency_scores=[
            CompetencyScoreOut(
                competency_id=s.competency_id,
                rank=competencies[s.competency_id].rank,
                code=competencies[s.competency_id].code,
                name=competencies[s.competency_id].name,
                target_level_min=competencies[s.competency_id].target_level_min,
                target_level_max=competencies[s.competency_id].target_level_max,
                level=s.level,
                explanation=s.explanation,
                evidence=evidence_out(s.evidence, texts),
                details=_competency_details_out(s.details, texts),
            )
            for s in scores
        ],
    )


def _formal_check_out(
    check: FormalCheck,
    requirement: FormalRequirement,
    texts: dict[uuid.UUID, str],
    confirmers: dict[uuid.UUID, str],
) -> FormalCheckOut:
    return FormalCheckOut(
        requirement_id=requirement.id,
        key=requirement.key,
        kind=requirement.kind,
        description=requirement.description,
        is_mandatory=requirement.is_mandatory,
        verification=requirement.verification,
        check_stage=requirement.check_stage,
        source_quote=source_quote(requirement),
        result=check.result,
        basis=check.basis,
        is_preliminary=check.is_preliminary,
        confirmed_by=confirmers.get(check.confirmed_by_user_id) if check.confirmed_by_user_id else None,
        explanation=check.explanation,
        evidence=evidence_out(check.evidence, texts),
        alternatives=[
            AlternativeOut(key=alt["key"], result=alt["result"], evidence=evidence_out(alt.get("evidence", []), texts))
            for alt in check.alternatives
        ],
    )


def source_quote(requirement: FormalRequirement) -> str | None:
    """Откуда требование: дословные цитаты документов, а у строки команды — её обоснование."""
    quotes = [ref["quote"] for ref in requirement.source_refs if ref.get("quote")]
    if quotes:
        return "\n".join(quotes)
    return requirement.note


_evidence_texts = assessment_texts  # одно место сбора текстов цитат: app.assessment.state


def _user_logins(session: Session, user_ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}
    return dict(session.execute(select(User.id, User.login).where(User.id.in_(ids))).all())


# --- GET /candidate-texts/{id} -------------------------------------------------

def get_candidate_text(session: Session, candidate_text_id: uuid.UUID) -> CandidateTextOut:
    row = session.get(CandidateText, candidate_text_id)
    if row is None:
        raise not_found("CANDIDATE_TEXT_NOT_FOUND", "Текст кандидата не найден", candidate_text_id=candidate_text_id)
    candidate = session.get(Candidate, row.candidate_id)
    return CandidateTextOut(
        candidate_text_id=row.id,
        candidate_id=candidate.id,
        candidate_code=candidate.code,
        is_training=candidate.is_synthetic,
        version=row.version,
        is_current=row.is_current,
        redaction_method=row.redaction_method,
        text=row.text,
        char_length=len(row.text),
        utf16_length=utf16_offset(row.text, len(row.text)),
    )
