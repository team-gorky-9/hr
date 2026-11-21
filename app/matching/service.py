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
from app.assessment.state import AssessmentStatus, resolve_states
from app.db import repository as repo
from app.db.enums import RequirementStatus
from app.db.models import Position, RequirementProfile
from app.matching.schemas import CandidateMatch, CandidatesForVacancyIn, CandidatesForVacancyOut, VacancySnapshot
from app.search.schemas import SearchRequest, SearchResponse

Qualification = tuple[str, str, uuid.UUID | None]  # статус, причина, id оценки


def check_vacancy(vacancy: VacancySnapshot) -> None:
    if vacancy.status != "published":
        raise ApiError(409, "VACANCY_NOT_PUBLISHED", "Подбор доступен только для опубликованной вакансии",
                       {"status": vacancy.status})


def exact_profile(session: Session, vacancy: VacancySnapshot) -> tuple[RequirementProfile | None, str]:
    """Профиль, по которому можно читать оценки, либо причина, почему оценки не читаются.
    Профиль другого контура — ошибка запроса (контуры не смешиваются), остальное — not_evaluated."""
    ref = vacancy.profile_ref
    if ref is None:
        return None, "no_profile_ref"
    if ref.system != "legacy-hr":
        return None, "unmapped_profile"  # профиль нового Requirements без подтверждённого отображения
    profile = session.get(RequirementProfile, ref.id)
    if profile is None:
        return None, "profile_not_found"
    if profile.is_synthetic != (vacancy.contour == "training"):
        raise ApiError(409, "CONTOUR_MISMATCH", "Профиль и вакансия из разных контуров",
                       {"contour": str(vacancy.contour)})
    position = session.get(Position, profile.position_id)
    if profile.version != ref.version or position is None or position.code != vacancy.position_code:
        return None, "profile_mismatch"
    approved = repo.get_approved_profile(session, profile.position_id, synthetic=profile.is_synthetic)
    if profile.status != RequirementStatus.APPROVED or approved is None or approved.id != profile.id:
        return None, "profile_not_current"
    return profile, "evaluated"


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

