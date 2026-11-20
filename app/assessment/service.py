"""Извлечение карточки и оценивание кандидата (контракт assessment.md v0.2, п. 3).

Путь одного кандидата:
1. Очищенный текст → модель → CandidateCard → repository.add_candidate_card.
2. Профиль: проверка режима (operational/technical) и разбор params (rules.py).
3. Модель извлекает по формальным требованиям периоды, фразу о стаже и статусы альтернатив
   образования — с цитатами; по каждой компетенции — статусы индикаторов с цитатами.
4. Код находит позиции цитат (evidence.py), считает стаж (experience.py), сводит альтернативы,
   понижает неподтверждённое (verification.py) и считает счётчики «X из Y».
5. repository.save_assessment. Функции не делают commit: транзакцией управляет вызывающий.
"""
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.ai.client import LLMClient
from app.assessment.errors import AssessmentDomainError
from app.ai.errors import LLMInvalidResponseError
from app.assessment.counters import aggregate_competency, validate_groups
from app.assessment.version import ALGORITHM_VERSION
from app.assessment.evidence import ResolvedQuote, resolve_quote
from app.assessment.experience import Period, Statement, decide_commercial
from app.assessment.llm_schemas import CompetencyExtraction, FormalExtraction
from app.assessment.prompts import (
    ASSESS_COMPETENCY_SYSTEM,
    ASSESS_FORMAL_SYSTEM,
    ASSESS_PROMPT_VERSION,
    CARD_PROMPT_VERSION,
    CARD_SYSTEM,
    card_user,
    competency_user,
    formal_user,
)
from app.assessment.rules import (
    EducationRule,
    ExperienceRule,
    Rule,
    parse_rule,
)
from app.assessment.verification import EvidenceVerdict, confirm_result, formal_result
from app.db import repository as repo
from app.db.enums import AuditAction, CheckResult, RequirementStatus
from app.db.models import CandidateCard as CardRow
from app.db.models import (
    CandidateText,
    Candidate,
    Competency,
    FormalRequirement,
    RequirementProfile,
)
from app.schemas.assessment import AlternativeResultIn, CompetencyScoreIn, FormalCheckIn
from app.schemas.competency_details import IndicatorResult
from app.schemas.card import CandidateCard, Evidence

Mode = Literal["operational", "technical"]
_AS_OF = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# --- Журнал вызовов модели -----------------------------------------------------

def record_llm_calls(session: Session, llm: LLMClient, candidate_id: uuid.UUID) -> None:
    """Записать накопленные вызовы модели в audit_log: модель, версия промпта, статус, время.
    Текста резюме и ключей в записи нет."""
    for call in llm.calls:
        repo.write_audit(session, action=AuditAction.LLM_CALL, entity_type="candidate",
                         entity_id=str(candidate_id), details=call.as_audit())
    llm.calls.clear()


# --- Карточка ------------------------------------------------------------------

def extract_candidate_card(session: Session, *, candidate_id: uuid.UUID, llm: LLMClient,
                           prompt_version: str = CARD_PROMPT_VERSION, record_calls: bool = True) -> uuid.UUID:
    text = repo.get_current_text(session, candidate_id)
    if text is None:
        raise AssessmentDomainError("no_clean_text", "у кандидата нет очищенного текста")
    card = llm.complete_structured(CARD_SYSTEM, card_user(text.text), CandidateCard,
                                   model_role="extract", prompt_version=prompt_version)
    card.pii_hidden = True  # модель видела только очищенный текст
    row = repo.add_candidate_card(session, candidate_id, card, extractor=llm.model_name("extract"),
                                  prompt_version=prompt_version, candidate_text_id=text.id)
    if record_calls:
        record_llm_calls(session, llm, candidate_id)
    return row.id


# --- Оценка --------------------------------------------------------------------

@dataclass
class _CheckDraft:
    """Проверка формального требования до сохранения."""
    requirement: FormalRequirement
    result: CheckResult
    evidence: list[Evidence] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    alternatives: list[AlternativeResultIn] = field(default_factory=list)


def assess_candidate(
    session: Session,
    *,
    candidate_id: uuid.UUID,
    profile_id: uuid.UUID,
    llm: LLMClient,
    mode: Mode = "operational",
    card_id: uuid.UUID | None = None,
    as_of: str | None = None,
    prompt_version: str = ASSESS_PROMPT_VERSION,
) -> uuid.UUID:
    profile = session.get(RequirementProfile, profile_id)
    if profile is None:
        raise AssessmentDomainError("no_profile", f"нет профиля требований {profile_id}")
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise AssessmentDomainError('no_candidate', 'кандидат не найден')
    _check_mode(profile, mode, candidate=candidate)
    validate_groups(profile.competencies)
    # Правила разбираются до вызова модели: неизвестный формат — оценки нет вовсе.
    rules = {r.key: parse_rule(r.key, r.kind, r.params, r.verification) for r in profile.formal_requirements}

    text = repo.get_current_text(session, candidate_id)
    if text is None:
        raise AssessmentDomainError("no_clean_text", "у кандидата нет очищенного текста")
    as_of = as_of or datetime.now(UTC).strftime("%Y-%m")
    if not _AS_OF.match(as_of):
        raise AssessmentDomainError("bad_as_of", f"as_of должен быть 'ГГГГ-ММ', получено {as_of!r}")
    card_row = _card_for_text(session, candidate_id=candidate_id, text=text, card_id=card_id, llm=llm)

    drafts = _assess_formal(profile, rules, text, llm, prompt_version, as_of)
    scores = [_assess_competency(c, text, llm, prompt_version) for c in profile.competencies]

    checks = [_to_check_in(d) for d in drafts]
    effective = {d.requirement.id: d.result for d in drafts}
    mandatory = [r.id for r in profile.formal_requirements if r.is_mandatory and r.check_stage == 'screening']
    summary = _summary(formal_result(effective, mandatory), drafts)

    assessment = repo.save_assessment(
        session,
        candidate_id=candidate_id,
        profile_id=profile.id,
        card_id=card_row.id,
        model=llm.model_name("assess"),
        formal_checks=checks,
        competency_scores=scores,
        summary=summary,
        prompt_version=prompt_version,
        algorithm_version=ALGORITHM_VERSION,
        calculation_as_of=as_of,
    )
    record_llm_calls(session, llm, candidate_id)
    return assessment.id


def _check_mode(profile: RequirementProfile, mode: Mode, *, candidate: Candidate) -> None:
    if mode not in ('operational', 'technical'):
        raise AssessmentDomainError("bad_mode", f"неизвестный режим {mode!r}")
    if profile.status == RequirementStatus.ARCHIVED:
        raise AssessmentDomainError("profile_archived", "профиль в архиве")
    if mode == "operational":
        if candidate.is_synthetic:
            raise AssessmentDomainError('training_candidate', 'рабочий режим требует реального кандидата')
        if profile.is_synthetic or profile.status != RequirementStatus.APPROVED:
            raise AssessmentDomainError(
                "profile_not_approved",
                "рабочая оценка — только по утверждённому реальному профилю; учебный профиль — в режиме technical",
            )
    elif mode == "technical":
        if not candidate.is_synthetic:
            raise AssessmentDomainError('technical_mode_real_candidate', 'технический режим требует учебного кандидата')


def _card_for_text(session: Session, *, candidate_id: uuid.UUID, text: CandidateText,
                   card_id: uuid.UUID | None, llm: LLMClient) -> CardRow:
    """Карточка той же версии текста. Явно переданная устаревшая карточка — ошибка;
    без card_id устаревшая или отсутствующая карточка извлекается заново."""
    if card_id is not None:
        row = session.get(CardRow, card_id)
        if row is None or row.candidate_id != candidate_id:
            raise AssessmentDomainError("stale_card", "карточка не найдена или чужая")
        if row.candidate_text_id != text.id:
            raise AssessmentDomainError("stale_card", "карточка построена по другой версии текста")
        return row
    row = repo.get_current_card(session, candidate_id)
    if row is None or row.candidate_text_id != text.id:
        # Keep calls until the whole assessment succeeds; a later rollback must not
        # lose the extraction call before CLI writes its failure audit transaction.
        new_id = extract_candidate_card(session, candidate_id=candidate_id, llm=llm, record_calls=False)
        row = session.get(CardRow, new_id)
    return row


# --- Формальные требования ------------------------------------------------------

def _assess_formal(profile: RequirementProfile, rules: dict[str, Rule], text: CandidateText,
                   llm: LLMClient, prompt_version: str, as_of: str) -> list[_CheckDraft]:
    active = {r.key for r in profile.formal_requirements if r.check_stage == 'screening'}
    education = [r for r in rules.values() if isinstance(r, EducationRule) and r.key in active]
    experience = [r for r in rules.values() if isinstance(r, ExperienceRule) and r.key in active]
    requirements = {r.key: r for r in profile.formal_requirements}
    extraction = FormalExtraction()
    if education or experience:
        hints = [{"requirement": r.key, "relevant_experience": r.relevance_hint,
                  "acceptance": requirements[r.key].acceptance} for r in experience]
        alternatives = [
            {"alternative_key": alt["key"], "requirement": rule.key,
             "condition": {k: v for k, v in alt.items() if k != "key"},
             "description": _description(profile, rule.key),
             "acceptance": requirements[rule.key].acceptance,
             "requires_requirement": rule.requires}
            for rule in education for alt in rule.alternatives
        ]
        extraction = llm.complete_structured(
            ASSESS_FORMAL_SYSTEM,
            formal_user(text.text, experience=hints or ([{"requirement": r.key} for r in experience] or None),
                        alternatives=alternatives),
            FormalExtraction, model_role="assess", prompt_version=prompt_version,
        )
        _validate_answer_keys([a.alternative_key for a in extraction.alternatives],
                              {a['key'] for r in education for a in r.alternatives})

    drafts: dict[str, _CheckDraft] = {}
    # Сначала требования без зависимостей, затем зависящие (направление после уровня).
    ordered = sorted(profile.formal_requirements,
                     key=lambda r: (isinstance(rules[r.key], EducationRule) and rules[r.key].requires is not None,
                                    r.sort_order))
    for requirement in ordered:
        rule = rules[requirement.key]
        if requirement.key not in active:
            draft = _CheckDraft(requirement, CheckResult.UNKNOWN,
                                details={'notes': ['проверяется на интервью']})
        elif isinstance(rule, ExperienceRule):
            draft = _experience_check(requirement, rule, extraction, text, as_of)
        elif isinstance(rule, EducationRule):
            draft = _education_check(requirement, rule, extraction, text)
            dependency = drafts.get(rule.requires) if rule.requires else None
            if dependency is not None and dependency.result != CheckResult.MET:
                draft.result, draft.evidence = CheckResult.UNKNOWN, []
                draft.details.setdefault("notes", []).append(f"зависит от {rule.requires}: там нет сведений")
        else:
            draft = _CheckDraft(requirement, CheckResult.UNKNOWN,
                                details={"notes": ["по резюме не проверяется: вопрос интервью"]})
        drafts[requirement.key] = _apply_basis(draft)
    return [drafts[r.key] for r in sorted(profile.formal_requirements, key=lambda r: r.sort_order)]


def _description(profile: RequirementProfile, key: str) -> str:
    return next((r.description for r in profile.formal_requirements if r.key == key), "")


def _resolve(text: CandidateText, quote: str | None, context: str | None) -> ResolvedQuote | None:
    return resolve_quote(text.text, quote, candidate_text_id=text.id, context_before=context)


def _experience_check(requirement: FormalRequirement, rule: ExperienceRule, extraction: FormalExtraction,
                      text: CandidateText, as_of: str) -> _CheckDraft:
    periods: list[tuple[Period, ResolvedQuote, bool | None]] = []
    dropped = 0
    for item in extraction.periods:
        found = _resolve(text, item.quote, item.context_before)
        if found is None:
            dropped += 1  # период без цитаты в тексте не учитываем
            continue
        periods.append((Period(item.start, item.end, item.is_current, item.kind), found, item.relevant))
    notes = [f"не найдено в тексте и не учтено периодов: {dropped}"] if dropped else []

    if rule.scope == "relevant_role":
        work = [(p, q) for p, q, rel in periods if rel and p.kind in ("work", "internship", "contract")]
        if work:
            return _CheckDraft(requirement, CheckResult.MET, [q.evidence for _, q in work],
                               {"rule": "relevant_role", "notes": notes, "ambiguous": _ambiguous(q for _, q in work)})
        no_exp = _resolve(text, extraction.no_experience_quote, None)
        if no_exp is not None:
            return _CheckDraft(requirement, CheckResult.NOT_MET, [no_exp.evidence],
                               {"rule": "relevant_role", "notes": notes})
        if any(rel and p.kind == "project" for p, _, rel in periods):
            notes.append("релевантный опыт только в учебном или личном проекте: уточнить на интервью")
        return _CheckDraft(requirement, CheckResult.UNKNOWN, [],
                           {"rule": "relevant_role", "gap": "опыт работы", "notes": notes})

    statement_found = None
    statement = None
    if extraction.statement is not None:
        statement_found = _resolve(text, extraction.statement.quote, None)
        if statement_found is not None:
            statement = Statement(months=extraction.statement.years * 12 + extraction.statement.months,
                                  commercial=extraction.statement.commercial)
    decision = decide_commercial([p for p, _, _ in periods], statement, min_months=rule.min_months, as_of=as_of)
    evidence = [q.evidence for p, q, _ in periods if p.kind in ("work", "contract", "internship", "unknown")]
    if statement_found is not None:
        evidence.append(statement_found.evidence)
    result = CheckResult(decision.outcome)
    details: dict[str, Any] = {
        "rule": "total_commercial", "min_months": rule.min_months, "as_of": as_of,
        "from_periods": decision.from_periods, "from_statement": decision.from_statement,
        "statement_months": decision.statement_months, "conflict": decision.conflict,
        "divergence": decision.divergence, "notes": notes + decision.notes,
    }
    if decision.months is not None:
        details["months_low"] = decision.months.low
        details["months_high"] = None if decision.months.high == float("inf") else decision.months.high
    if result == CheckResult.UNKNOWN:
        details["gap"] = "длительность коммерческого опыта"
    return _CheckDraft(requirement, result, evidence if result != CheckResult.UNKNOWN or decision.conflict else [],
                       details)


def _education_check(requirement: FormalRequirement, rule: EducationRule, extraction: FormalExtraction,
                     text: CandidateText) -> _CheckDraft:
    answers = {a.alternative_key: a for a in extraction.alternatives}
    statuses: dict[str, str] = {}
    met_evidence: list[Evidence] = []
    refuted_evidence: list[Evidence] = []
    alternative_results = []
    for alternative in rule.alternatives:
        answer = answers.get(alternative["key"])
        fragments = list(answer.quotes) if answer else []
        if answer and answer.quote:
            fragments.append(answer)
        resolved = [_resolve(text, q.quote, q.context_before) for q in fragments]
        valid = bool(resolved) and all(resolved)
        quotes = list({(q.evidence.start, q.evidence.end): q.evidence for q in resolved if q}.values())
        if answer and answer.status == "confirmed" and valid:
            statuses[alternative["key"]] = "met"
            met_evidence.extend(quotes)
        elif answer and answer.status == "refuted" and valid:
            statuses[alternative["key"]] = "not_met"
            refuted_evidence.extend(quotes)
        else:
            statuses[alternative["key"]] = "unknown"
        alternative_results.append(AlternativeResultIn(key=alternative['key'],
            result=statuses[alternative['key']], evidence=quotes))
    details = {"rule": requirement.kind, "alternatives": statuses}
    if "met" in statuses.values():
        return _CheckDraft(requirement, CheckResult.MET, met_evidence, details, alternative_results)
    if statuses and all(s == "not_met" for s in statuses.values()):
        return _CheckDraft(requirement, CheckResult.NOT_MET, refuted_evidence, details, alternative_results)
    details["gap"] = "образование" if requirement.kind == "education_level" else "направление подготовки"
    return _CheckDraft(requirement, CheckResult.UNKNOWN, [], details, alternative_results)


def _apply_basis(draft: _CheckDraft) -> _CheckDraft:
    """Невалидная цитата понижает результат; необходимость документа — только предварительность."""
    confirmation = confirm_result(draft.result, [EvidenceVerdict.OK] * len(draft.evidence))
    if confirmation.issue is not None:
        draft.details["downgraded"] = confirmation.issue.value
        draft.result, draft.evidence = confirmation.effective, []
    draft.details["basis"] = "resume"
    verification = draft.requirement.verification
    if draft.result == CheckResult.MET and verification != "resume":
        draft.details["is_preliminary"] = True
        draft.details["needs"] = str(verification)
    return draft


def _to_check_in(draft: _CheckDraft) -> FormalCheckIn:
    return FormalCheckIn(
        requirement_id=draft.requirement.id,
        result=draft.result,
        explanation=_explanation(draft.details),
        evidence=draft.evidence,
        alternatives=draft.alternatives,
    )


def _explanation(details: dict[str, Any]) -> str:
    basis = details.get("basis", "resume")
    return f"[{basis}] " + json.dumps({k: v for k, v in details.items() if v not in (None, [], {})},
                                       ensure_ascii=False)


def _ambiguous(found) -> bool:
    return any(q.ambiguous_location for q in found)


# --- Компетенции -----------------------------------------------------------------

def _assess_competency(competency: Competency, text: CandidateText, llm: LLMClient,
                       prompt_version: str) -> CompetencyScoreIn:
    excluded = [i for i in competency.indicators if i.excluded_from_scoring]
    on_interview = [i for i in competency.indicators
                    if not i.excluded_from_scoring and i.check_stage == 'interview']
    screening = [i for i in competency.indicators if i not in excluded and i not in on_interview]

    answers = {}
    if screening:
        extraction = llm.complete_structured(
            ASSESS_COMPETENCY_SYSTEM,
            competency_user(text.text, competency=competency.name,
                            indicators=[{"indicator_key": i.key, "text": i.text,
                                         "acceptance": i.acceptance} for i in screening]),
            CompetencyExtraction, model_role="assess", prompt_version=prompt_version,
        )
        _validate_answer_keys([a.indicator_key for a in extraction.indicators], {i.key for i in screening})
        answers = {a.indicator_key: a for a in extraction.indicators}

    statuses: dict[str, dict[str, Any]] = {}
    evidence: list[Evidence] = []
    indicator_results = []
    for indicator in screening:
        answer = answers.get(indicator.key)
        found = _resolve(text, answer.quote, answer.context_before) if answer else None
        if answer and answer.status in ("confirmed", "contradicted") and found:
            status = answer.status
            evidence.append(found.evidence)
        else:
            status = "no_info"
        statuses[indicator.key] = {"status": status}
        if found is not None and found.ambiguous_location:
            statuses[indicator.key]["ambiguous_location"] = True
        indicator_results.append(IndicatorResult(key=indicator.key, status=status,
            evidence=[found.evidence] if found else [], ambiguous_location=bool(found and found.ambiguous_location)))

    typed = aggregate_competency(competency.indicators, {r.key: r.status for r in indicator_results})
    typed.indicators = indicator_results
    details = typed.model_dump(mode='json')
    # Keep the historical explanation readable; typed data is authoritative.
    details['indicators'] = statuses
    return CompetencyScoreIn(competency_id=competency.id, level=None,
                             explanation="[resume] " + json.dumps(details, ensure_ascii=False), evidence=evidence,
                             details=typed)


def _validate_answer_keys(keys: list[str], expected: set[str]) -> None:
    if len(keys) != len(set(keys)) or not set(keys) <= expected:
        raise LLMInvalidResponseError('ответ содержит повторяющийся или неизвестный ключ')


def _summary(result: CheckResult, drafts: list[_CheckDraft]) -> str:
    gaps = sorted({d.details["gap"] for d in drafts if d.result == CheckResult.UNKNOWN and d.details.get("gap")})
    claimed = [d.requirement.description for d in drafts if d.details.get("is_preliminary")]
    parts = [f"Формальные требования: {result.value}."]
    if gaps:
        parts.append("Пробелы: " + ", ".join(gaps) + ".")
    if claimed:
        parts.append("Заявлено по резюме, нужен документ: " + "; ".join(claimed) + ".")
    return " ".join(parts)
