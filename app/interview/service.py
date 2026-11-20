"""Сборка гайда по сохранённой оценке (interview.md, §1–4). Ничего не записывает: хранение гайда,
ответов и рубрики ядра — модуль БД по контракту. Функция не делает commit."""
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai.client import LLMClient
from app.assessment.service import record_llm_calls
from app.db.models import Assessment, Candidate, CandidateCard, RequirementProfile
from app.interview.gaps import DEFAULT_BUDGET, assemble_gaps
from app.interview.generate import (
    GUIDE_PROMPT_VERSION,
    core_rows,
    generate_clarifications,
    generate_core,
)


class GuideError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass
class GuideDraft:
    assessment_id: str
    assessment_version: int
    profile_id: str
    profile_version: int
    is_training: bool
    rubric_status: str
    prompt_version: str = GUIDE_PROMPT_VERSION
    model_calls: int = 0
    core: list[dict[str, Any]] = field(default_factory=list)
    clarifications: list[dict[str, Any]] = field(default_factory=list)
    document_requests: list[dict[str, Any]] = field(default_factory=list)
    uncovered_gaps: list[dict[str, Any]] = field(default_factory=list)


def _question(kind: str, order: int, item, *, ref: str | None, sources: list[dict]) -> dict[str, Any]:
    return {"kind": kind, "sort_order": order, "question": item.question,
            "criterion": {"good_answer": item.good_answer, "insufficient_answer": item.insufficient_answer},
            "author": "model", "gap_ref_id": ref, "sources": sources, "answer": None}


def build_guide(session: Session, *, assessment_id: uuid.UUID, llm: LLMClient, budget: int = DEFAULT_BUDGET,
                include_core: bool = True, core_cache: dict[str, Any] | None = None,
                record_calls: bool = True) -> GuideDraft:
    """Собрать гайд по текущей оценке пары. Только чтение: вызывающий (модуль хранения, контракт
    interview.md v0.2, §4) зовёт функцию вне транзакции записи и сам сохраняет результат.

    core_cache — уже сохранённая рубрика ядра этой версии профиля {row_key: QuestionItem}: с ней ядро
    не генерируется повторно и совпадает у всех кандидатов. record_calls=False — журнал вызовов
    модели (llm.calls) пишет вызывающий в своей транзакции.

    В GuideDraft.assessment_id — **базовая** оценка (вывод модели по резюме, v0.2 §4): версия из
    confirm_formal_check ссылается на неё через base_assessment_id, и гайд по ней не устаревает."""
    assessment = session.get(Assessment, assessment_id)
    if assessment is None:
        raise GuideError("assessment_required", "у отклика нет оценки")
    if not assessment.is_current:
        raise GuideError("assessment_stale", "оценка не текущая: гайд строится по текущей версии")
    # До миграции 0006 столбца нет — тогда базовая оценка и есть текущая.
    base_id = getattr(assessment, "base_assessment_id", None) or assessment.id
    profile = session.get(RequirementProfile, assessment.profile_id)
    card = session.get(CandidateCard, assessment.card_id)
    plan = assemble_gaps(profile, assessment, (card.card or {}).get("missing") if card else [], budget=budget)

    calls_before = len(llm.calls)
    draft = GuideDraft(
        assessment_id=str(base_id), assessment_version=assessment.version,
        profile_id=str(profile.id), profile_version=profile.version,
        is_training=bool(profile.is_synthetic or session.get(Candidate, assessment.candidate_id).is_synthetic),
        rubric_status="draft", document_requests=plan.document_requests, uncovered_gaps=list(plan.uncovered),
    )

    items, missing = generate_clarifications(plan.selected, llm)
    for number, gap in enumerate(plan.selected, 1):
        if gap.gap_ref_id in items:
            draft.clarifications.append(_question("clarification", number, items[gap.gap_ref_id],
                                                  ref=gap.gap_ref_id, sources=gap.sources))
    draft.uncovered_gaps += [{"gap_ref_id": ref, "title": next(g.title for g in plan.selected if g.gap_ref_id == ref),
                              "reason": "not_generated"} for ref in missing]

    if include_core:
        rows = core_rows(profile)
        cached = core_cache or {}
        todo = [r for r in rows if r["row_key"] not in cached]
        generated, _ = generate_core(todo, llm) if todo else ({}, 0)
        questions = {**cached, **generated}
        draft.core = [_question("core", n, questions[r["row_key"]], ref=None, sources=[r["source"]])
                      for n, r in enumerate(rows, 1) if r["row_key"] in questions]

    draft.model_calls = len(llm.calls) - calls_before
    if record_calls and llm.calls:
        record_llm_calls(session, llm, assessment.candidate_id)
    return draft
