"""Кросс-оценка: один человек × утверждённые профили всех должностей контура (задача ai-02).

Запуск пакета (`run_cross_batch`) и чтение результата для API (`cross_assessments`).

- Пара `кандидат × профиль` оценивается через `assess_in_context` (оркестратор hr#15). Должность
  собственного прямого отклика — цель `primary` с проверкой применимости публикации, остальные
  должности — `comparison`. Новый отклик, событие этапа или запись резерва не создаются.
- Карточка извлекается один раз на версию текста и переиспользуется всеми профилями. Пары одного
  человека идут последовательно в одном потоке, параллельно обрабатываются разные люди (`workers`).
- Одна текущая оценка на пару гарантируется уникальным индексом `uq_assessments_current`. Если
  параллельный запуск успел записать ту же пару, пара повторяется один раз и берёт уже готовую оценку.
- GET только читает сохранённое: пакет запускает CLI. Статус и цитаты — общими правилами
  app.assessment.state, как в списке откликов.
"""
import uuid
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assessment.prompts import ASSESS_PROMPT_VERSION
from app.assessment.state import assessment_texts, evidence_with_utf16, resolve_states
from app.assessment.version import ALGORITHM_VERSION
from app.db import repository as repo
from app.db.models import (
    Application,
    Assessment,
    Candidate,
    CandidateCard,
    CandidateText,
    Competency,
    Position,
    RequirementProfile,
    Vacancy,
)

RESPONSE = "response"  # прямой отклик; source=history — исторический факт, не основание primary


@dataclass(frozen=True)
class Pair:
    candidate_id: uuid.UUID
    candidate_code: str
    profile_id: uuid.UUID
    position_code: str
    purpose: str                      # primary | comparison
    application_id: uuid.UUID | None


# --- Выбор пар -----------------------------------------------------------------

def approved_profiles(session: Session, *, technical: bool) -> tuple[list[RequirementProfile], list[str]]:
    """Действующие профили контура по всем должностям и коды должностей без утверждённого профиля."""
    profiles, missing = [], []
    for position in session.scalars(select(Position).order_by(Position.code)):
        profile = repo.get_approved_profile(session, position.id, synthetic=technical)
        (profiles.append(profile) if profile is not None else missing.append(position.code))
    return profiles, missing


def select_pairs(session: Session, *, technical: bool, candidate_codes: Iterable[str] | None = None,
                 source_position_code: str | None = None, limit: int | None = None,
                 profiles: list[RequirementProfile] | None = None) -> tuple[list[Pair], dict[str, Any]]:
    """Пары для пакета. Людей выбирает оператор (решение Р1 плана ai-02): коды, должность
    исходного отклика, лимит. Возвращает пары и пояснения, что не вошло и почему."""
    if profiles is None:
        profiles, missing_positions = approved_profiles(session, technical=technical)
    else:
        missing_positions = []
    query = (select(Candidate).join(CandidateText, CandidateText.candidate_id == Candidate.id)
             .where(Candidate.is_synthetic.is_(technical), CandidateText.is_current).order_by(Candidate.code))
    codes = list(candidate_codes or [])
    if codes:
        query = query.where(Candidate.code.in_(codes))
    if source_position_code:
        query = query.where(Candidate.id.in_(
            select(Application.candidate_id).join(Vacancy, Vacancy.id == Application.vacancy_id)
            .join(Position, Position.id == Vacancy.position_id)
            .where(Position.code == source_position_code, Application.source == RESPONSE)))
    candidates = list(session.scalars(query.distinct()))
    if limit:
        candidates = candidates[:limit]
    found = {c.code for c in candidates}

    positions = {p.id: session.get(Position, p.position_id).code for p in profiles}
    pairs: list[Pair] = []
    for candidate in candidates:
        own = _response_applications(session, candidate.id)  # position_id → application_id
        for profile in profiles:
            application_id = own.get(profile.position_id)
            pairs.append(Pair(candidate.id, candidate.code, profile.id, positions[profile.id],
                              "primary" if application_id else "comparison", application_id))
    explained = {
        "positions_without_approved_profile": missing_positions,
        "unknown_or_other_contour_codes": sorted(set(codes) - found),
    }
    return pairs, explained


def _response_applications(session: Session, candidate_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    rows = session.execute(
        select(Vacancy.position_id, Application.id).join(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(Application.candidate_id == candidate_id, Application.source == RESPONSE)
        .order_by(Application.created_at, Application.id))
    result: dict[uuid.UUID, uuid.UUID] = {}
    for position_id, application_id in rows:
        result.setdefault(position_id, application_id)  # первый прямой отклик на должность
    return result


def reusable_assessment(session: Session, *, candidate_id: uuid.UUID, profile_id: uuid.UUID,
                        as_of: str) -> Assessment | None:
    """Текущая оценка пары, которую оркестратор переиспользовал бы: те же версия текста,
    алгоритма, промпта и месяц расчёта (условия assess_in_context)."""
    text = repo.get_current_text(session, candidate_id)
    if text is None:
        return None
    return session.scalar(
        select(Assessment).join(CandidateCard, CandidateCard.id == Assessment.card_id).where(
            Assessment.candidate_id == candidate_id, Assessment.profile_id == profile_id, Assessment.is_current,
            Assessment.algorithm_version == ALGORITHM_VERSION, Assessment.prompt_version == ASSESS_PROMPT_VERSION,
            Assessment.calculation_as_of == as_of, CandidateCard.candidate_text_id == text.id))


# --- Запуск пакета ---------------------------------------------------------------

RunOne = Callable[..., dict]


def run_cross_batch(session_factory, pairs: list[Pair], *, run_one: RunOne, llm_factory: Callable[[], Any],
                    technical: bool, as_of: str, skip_existing: bool = False, workers: int = 1) -> dict[str, Any]:
    """Оценить пары и вернуть отчёт, где сумма исходов равна числу пар.

    run_one — оценка одной пары с обработкой ошибок и журналом (app.assessment.__main__.run_one).
    llm_factory — новый клиент модели на человека: журнал вызовов у каждого потока свой."""
    by_person: dict[uuid.UUID, list[Pair]] = {}
    for pair in pairs:
        by_person.setdefault(pair.candidate_id, []).append(pair)

    def person(person_pairs: list[Pair]) -> list[dict]:
        llm = llm_factory()
        return [_run_pair(session_factory, pair, run_one=run_one, llm=llm, technical=technical, as_of=as_of,
                          skip_existing=skip_existing) for pair in person_pairs]

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            chunks = list(pool.map(person, by_person.values()))
    else:
        chunks = [person(p) for p in by_person.values()]
    results = [r for chunk in chunks for r in chunk]

    counts: dict[str, int] = {}
    for result in results:
        counts[result["outcome"]] = counts.get(result["outcome"], 0) + 1
    assert sum(counts.values()) == len(pairs), "отчёт пакета не сходится с числом пар"
    return {"people": len(by_person), "pairs": len(pairs), "as_of": as_of, "counts": counts, "results": results}


def _run_pair(session_factory, pair: Pair, *, run_one: RunOne, llm, technical: bool, as_of: str,
              skip_existing: bool) -> dict:
    base = {"candidate_code": pair.candidate_code, "position_code": pair.position_code,
            "profile_id": str(pair.profile_id), "purpose": pair.purpose,
            "application_id": str(pair.application_id) if pair.application_id else None}
    if skip_existing:
        with session_factory() as session:
            current = reusable_assessment(session, candidate_id=pair.candidate_id, profile_id=pair.profile_id,
                                          as_of=as_of)
            if current is not None:
                return base | {"outcome": "skipped_current", "assessment_id": str(current.id),
                               "formal_result": current.formal_result.value}
    for attempt in (1, 2):
        try:
            result = run_one(session_factory, llm, candidate_code=pair.candidate_code, profile_id=pair.profile_id,
                             technical=technical, as_of=as_of, purpose=pair.purpose,
                             application_id=pair.application_id)
            break
        except IntegrityError:
            # Ту же пару успел записать параллельный запуск: повтор возьмёт готовую оценку.
            if attempt == 2:
                return base | {"outcome": "error", "reason": "concurrent_write", "error": "конфликт записи пары"}
    status = result.get("status")
    if status == "ok":
        outcome = "reused" if result.get("reused") else "assessed"
    elif status == "skipped":
        outcome = "skipped_context"   # отклик на чужую публикацию и т. п. — не отказ кандидату
    else:
        outcome = "error"
    return base | {"outcome": outcome} | {k: result[k] for k in
        ("status", "reason", "error", "assessment_id", "formal_result") if k in result}


# --- Чтение для API -----------------------------------------------------------------

def cross_assessments(session: Session, candidate_id: uuid.UUID, *,
                      application_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Набор для GET /api/v1/candidates/{candidate_id}/cross-assessments (план ai-02, Р4; backend-02).

    Только чтение сохранённых оценок. Контур определяется кандидатом: учебный человек видит
    учебные профили, реальный — рабочие. Ничего не создаёт и не меняет.

    Актуальность оценки и границы цитат считаются общими правилами app.assessment.state —
    теми же, что в списке и карточке откликов, поэтому статус пары везде одинаковый.
    """
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        return {"candidate_id": str(candidate_id), "items": [], "empty_reason": "candidate_not_found"}
    text = repo.get_current_text(session, candidate_id)
    applications = list(session.execute(
        select(Application, Vacancy, Position).outerjoin(Vacancy, Vacancy.id == Application.vacancy_id)
        .outerjoin(Position, Position.id == Vacancy.position_id)
        .where(Application.candidate_id == candidate_id).order_by(Application.created_at, Application.id)))
    profiles, _ = approved_profiles(session, technical=candidate.is_synthetic)
    own_positions = {v.position_id for a, v, p in applications if v is not None and _value(a.source) == RESPONSE}
    by_vacancy: dict[uuid.UUID, Application] = {}
    for application, vacancy, _ in applications:
        if vacancy is not None:
            by_vacancy.setdefault(vacancy.id, application)

    items = []
    for profile in profiles:
        position = session.get(Position, profile.position_id)
        state = resolve_states(session, [candidate_id], profile, position.id, candidate.is_synthetic)[candidate_id]
        vacancies = session.scalars(select(Vacancy).where(Vacancy.position_id == position.id)
                                    .order_by(Vacancy.title, Vacancy.id))
        items.append({
            "position_id": str(position.id), "position_code": position.code, "position_title": position.title,
            "is_municipal_service": position.is_municipal_service,
            "profile_id": str(profile.id), "profile_version": profile.version,
            "is_training": repo.is_training_assessment(candidate, profile),
            "is_source_position": profile.position_id in own_positions,
            # Признак отклика по каждой вакансии должности, в том числе без отклика.
            "vacancies": [_vacancy(v, by_vacancy.get(v.id)) for v in vacancies],
            "assessment_status": _value(state.status),
            "stale_reason": _value(state.stale_reason) if state.stale_reason else None,
            "assessment": _assessment(session, state.assessment) if state.assessment is not None else None,
        })
    return {
        "candidate_id": str(candidate_id), "candidate_code": candidate.code, "is_training": candidate.is_synthetic,
        "current_text_id": str(text.id) if text else None,
        "context_application_id": str(application_id) if application_id else None,
        "applications": [{"application_id": str(a.id), "vacancy_id": str(a.vacancy_id) if a.vacancy_id else None,
                          "position_code": p.code if p else None, "source": _value(a.source),
                          "posting_title": a.posting_title, "current_stage_code": a.current_stage_code}
                         for a, v, p in applications],
        "items": items,
        "empty_reason": None if items else "no_approved_profiles",
    }


def _value(enum_or_str):
    return getattr(enum_or_str, "value", enum_or_str)


def _vacancy(vacancy: Vacancy, application: Application | None) -> dict[str, Any]:
    return {
        "vacancy_id": str(vacancy.id), "title": vacancy.title, "channel": _value(vacancy.channel),
        "status": _value(vacancy.status),
        "application_id": str(application.id) if application else None,
        "application_source": _value(application.source) if application else None,
        "application_stage_code": application.current_stage_code if application else None,
    }


def _assessment(session: Session, assessment: Assessment) -> dict[str, Any]:
    """Оценка с цитатами. Строки берутся из профиля самой оценки: при profile_changed это
    прежняя версия профиля, а не утверждённая сейчас."""
    profile = session.get(RequirementProfile, assessment.profile_id)
    requirements = {r.id: r for r in profile.formal_requirements}
    competencies = {c.id: c for c in session.scalars(select(Competency).where(Competency.profile_id == profile.id))}
    texts = assessment_texts(session, assessment.formal_checks, assessment.competency_scores)
    checks, gaps = [], []
    for check in sorted(assessment.formal_checks,
                        key=lambda c: (requirements[c.requirement_id].sort_order, requirements[c.requirement_id].key)):
        requirement = requirements[check.requirement_id]
        if _value(check.result) == "unknown" and _value(requirement.check_stage) == "screening":
            gaps.append(requirement.description)
        checks.append({
            "requirement_key": requirement.key, "description": requirement.description,
            "is_mandatory": requirement.is_mandatory, "check_stage": _value(requirement.check_stage),
            "result": _value(check.result), "basis": _value(check.basis), "is_preliminary": check.is_preliminary,
            "evidence": _evidence(check.evidence, texts),
        })
    scores = sorted(assessment.competency_scores,
                    key=lambda s: (competencies[s.competency_id].sort_order, competencies[s.competency_id].code))
    return {
        "assessment_id": str(assessment.id), "version": assessment.version,
        "profile_id": str(profile.id), "profile_version": profile.version,
        "formal_result": _value(assessment.formal_result), "formal_preliminary": assessment.formal_preliminary,
        "overall_score": assessment.overall_score,
        "summary": assessment.summary, "gaps": gaps, "formal_checks": checks,
        "competencies": [{
            "competency_id": str(s.competency_id), "code": competencies[s.competency_id].code,
            "name": competencies[s.competency_id].name, "rank": _value(competencies[s.competency_id].rank),
            "target_level_min": competencies[s.competency_id].target_level_min,
            "target_level_max": competencies[s.competency_id].target_level_max,
            "level": s.level, "explanation": s.explanation,
            "mandatory": (s.details or {}).get("mandatory"), "desired": (s.details or {}).get("desired"),
            "evidence": _evidence(s.evidence, texts),
        } for s in scores],
    }


def _evidence(items, texts: dict[uuid.UUID, str]) -> list[dict[str, Any]]:
    """Цитаты с кодовыми точками (база) и UTF-16 (браузер) по тексту, на который ссылается цитата."""
    return [{**e, "candidate_text_id": str(e["candidate_text_id"])} for e in evidence_with_utf16(items or [], texts)]
