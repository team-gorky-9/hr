"""3A: люди под выбранную вакансию — тот же поиск по профессиональному тексту плюс статус оценки.

Пример. HR передаёт снимок учебной вакансии «Аналитик ИС» с search_query «анализ и согласование
требований к ИС» и profile_ref на утверждённый учебный профиль. Сервис:
1. отклоняет закрытую публикацию и профиль другого контура;
2. выполняет SearchRequest(query=search_query, contour, filters, limit) — ту же функцию, что /search;
3. для каждого найденного candidate_id ищет актуальную оценку по этому точному профилю
   (resolve_states — те же правила, что в списке откликов) и показывает met/unknown/not_met,
   иначе not_evaluated с причиной.
Отклики, приглашения и записи резерва не создаются."""
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.assessment import cross
from app.assessment.state import AssessmentStatus, resolve_states
from app.db import repository as repo
from app.db.enums import RequirementStatus
from app.db.models import Candidate, Position, RequirementProfile
from app.matching.schemas import (
    CandidateMatch,
    CandidatesForVacancyIn,
    CandidatesForVacancyOut,
    VacanciesForCandidateIn,
    VacanciesForCandidateOut,
    VacancyExcluded,
    VacancyMatch,
    VacancyNeedsEvaluation,
    VacancySnapshot,
)
from app.search.schemas import SearchRequest, SearchResponse

Qualification = tuple[str, str, uuid.UUID | None]  # статус, причина, id оценки


def check_vacancy(vacancy: VacancySnapshot) -> None:
    if vacancy.status != "published":
        raise ApiError(409, "VACANCY_NOT_PUBLISHED", "Подбор доступен только для опубликованной вакансии",
                       {"status": vacancy.status})


def match_profile(session: Session, vacancy: VacancySnapshot) -> tuple[RequirementProfile | None, str]:
    """Точный профиль вакансии, по которому можно читать оценки, либо причина, почему нельзя.
    Сопоставление — только по id, версии и коду должности; похожее название не используется."""
    ref = vacancy.profile_ref
    if ref is None:
        return None, "no_profile_ref"
    if ref.system != "legacy-hr":
        return None, "unmapped_profile"  # профиль нового Requirements без подтверждённого отображения
    profile = session.get(RequirementProfile, ref.id)
    if profile is None:
        return None, "profile_not_found"
    if profile.is_synthetic != (vacancy.contour == "training"):
        return None, "contour_mismatch"
    position = session.get(Position, profile.position_id)
    if profile.version != ref.version or position is None or position.code != vacancy.position_code:
        return None, "profile_mismatch"
    approved = repo.get_approved_profile(session, profile.position_id, synthetic=profile.is_synthetic)
    if profile.status != RequirementStatus.APPROVED or approved is None or approved.id != profile.id:
        return None, "profile_not_current"
    return profile, "evaluated"


def exact_profile(session: Session, vacancy: VacancySnapshot) -> tuple[RequirementProfile | None, str]:
    """3A: профиль другого контура — ошибка запроса (контуры не смешиваются), остальное — not_evaluated."""
    profile, reason = match_profile(session, vacancy)
    if reason == "contour_mismatch":
        raise ApiError(409, "CONTOUR_MISMATCH", "Профиль и вакансия из разных контуров",
                       {"contour": str(vacancy.contour)})
    return profile, reason


def qualifications(session: Session, profile: RequirementProfile | None, reason: str,
                   candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, Qualification]:
    if profile is None:
        return {cid: ("not_evaluated", reason, None) for cid in candidate_ids}
    states = resolve_states(session, candidate_ids, profile, profile.position_id, profile.is_synthetic)
    result = {}
    for cid in candidate_ids:
        state = states[cid]
        if state.status == AssessmentStatus.READY:
            result[cid] = (str(state.assessment.formal_result), "evaluated", state.assessment.id)
        elif state.status == AssessmentStatus.STALE:
            result[cid] = ("not_evaluated", "assessment_stale", None)
        else:
            result[cid] = ("not_evaluated", "not_assessed", None)
    return result


def candidates_for_vacancy(session: Session, body: CandidatesForVacancyIn,
                           search: Callable[[Session, SearchRequest], SearchResponse]) -> CandidatesForVacancyOut:
    """search(session, SearchRequest) → SearchResponse — действующий поиск (app.search.api.run_search)."""
    vacancy = body.vacancy
    check_vacancy(vacancy)
    profile, reason = exact_profile(session, vacancy)
    found: SearchResponse = search(session, SearchRequest(
        query=vacancy.search_query, contour=vacancy.contour, limit=body.limit, filters=body.filters))
    status = qualifications(session, profile, reason, [hit.candidate_id for hit in found.items])
    items = []
    for hit in found.items:
        qualification, why, assessment_id = status[hit.candidate_id]
        items.append(CandidateMatch(**hit.model_dump(), qualification_status=qualification,
                                    qualification_reason=why, assessment_id=assessment_id))
    return CandidatesForVacancyOut(
        vacancy_ref=vacancy.ref, vacancy_revision=vacancy.revision, observed_at=vacancy.observed_at,
        source_mode="provided", contour=vacancy.contour, profile_ref=vacancy.profile_ref,
        search_query=vacancy.search_query, mode=found.mode, semantic_status=found.semantic_status, items=items,
    )



# --- 3B · вакансии по присланному резюме ------------------------------------------------------
#
# Пример. Учебный кандидат прислал резюме без вакансии. HR передаёт четыре снимка: две открытые
# вакансии на должности с сохранёнными оценками, одну без оценки и одну закрытую. Сервис читает
# сохранённые кросс-оценки (та же модель чтения, что GET /candidates/{id}/cross-assessments) и
# связывает вакансию с оценкой только по точному профилю: id, версия и код должности.
# Результат: items (met → unknown → not_met), needs_evaluation с причиной и excluded. Новые оценки,
# отклики и вызовы модели не создаются.

FORMAL_ORDER = {"met": 0, "unknown": 1, "not_met": 2}
TO_NEEDS = {"contour_mismatch": "profile_mismatch"}


def formal_reason(assessment: dict) -> str:
    """Понятное основание из сохранённых проверок формальных требований этапа отбора."""
    result = assessment["formal_result"]
    version = assessment["version"]
    if result == "met":
        return f"Обязательные требования выполнены (оценка v{version})"
    titles = [c["description"] for c in assessment["formal_checks"]
              if c["is_mandatory"] and c["check_stage"] == "screening" and c["result"] == result]
    shown = "; ".join(titles[:3]) + ("…" if len(titles) > 3 else "")
    prefix = "Нет сведений" if result == "unknown" else "Не выполнено"
    return f"{prefix}: {shown} (оценка v{version})" if shown else f"{prefix} (оценка v{version})"


def vacancies_for_candidate(session: Session, body: VacanciesForCandidateIn) -> VacanciesForCandidateOut:
    candidate = session.get(Candidate, body.candidate_id)
    if candidate is None:
        raise ApiError(404, "CANDIDATE_NOT_FOUND", "Кандидат не найден", {"candidate_id": str(body.candidate_id)})
    if candidate.is_synthetic != (body.contour == "training"):
        raise ApiError(409, "CONTOUR_MISMATCH", "Кандидатская запись из другого контура",
                       {"contour": str(body.contour)})
    data = cross.cross_assessments(session, candidate.id)
    by_profile = {(row["profile_id"], row["profile_version"], row["position_code"]): row for row in data["items"]}

    items, needs, excluded = [], [], []
    for vacancy in body.vacancies:
        if vacancy.contour != body.contour:
            excluded.append(VacancyExcluded(vacancy_ref=vacancy.ref, reason="other_contour"))
            continue
        if vacancy.status != "published":
            excluded.append(VacancyExcluded(vacancy_ref=vacancy.ref, reason="closed"))
            continue
        profile, reason = match_profile(session, vacancy)
        row = None
        if profile is not None:
            row = by_profile.get((str(profile.id), profile.version, vacancy.position_code))
            if row is None:  # профиль не среди действующих утверждённых в контуре кандидата
                reason = "profile_not_current"
        if row is not None and row["assessment_status"] == "ready":
            assessment = row["assessment"]
            items.append(VacancyMatch(
                vacancy_ref=vacancy.ref, vacancy_revision=vacancy.revision, title=vacancy.title,
                profile_ref=vacancy.profile_ref, assessment_status="ready",
                formal_result=assessment["formal_result"], assessment_id=assessment["assessment_id"],
                reason=formal_reason(assessment)))
            continue
        if row is not None:
            reason = "assessment_stale" if row["assessment_status"] == "stale" else "not_assessed"
        needs.append(VacancyNeedsEvaluation(
            vacancy_ref=vacancy.ref, title=vacancy.title, reason=TO_NEEDS.get(reason, reason),
            stale_reason=row["stale_reason"] if row is not None else None))

    items.sort(key=lambda i: (FORMAL_ORDER[i.formal_result], str(i.vacancy_ref.id)))
    return VacanciesForCandidateOut(
        candidate_id=candidate.id, current_text_id=data.get("current_text_id"), contour=body.contour,
        source_mode="provided", items=items[:body.limit], needs_evaluation=needs, excluded=excluded)
