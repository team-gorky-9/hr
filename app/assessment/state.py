"""Актуальность сохранённой оценки и цитаты для браузера — одно правило для всего проекта.

Им пользуются API (список откликов, карточка, comparison) и модель чтения кросс-оценок
(app.assessment.cross). Раньше у каждого была своя копия, и статус одной и той же пары
«кандидат × профиль» мог различаться в списке и в рекомендациях.
"""
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment.prompts import ASSESS_PROMPT_VERSION
from app.assessment.verification import utf16_offsets
from app.assessment.version import ALGORITHM_VERSION
from app.db.models import Assessment, CandidateCard, CandidateText, RequirementProfile


class AssessmentStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    MAPPING_REQUIRED = "mapping_required"
    READY = "ready"                              # актуальная оценка по текущему тексту и утверждённому профилю
    STALE = "stale"                              # оценка есть, но текст, алгоритм или утверждённый профиль сменились
    NOT_ASSESSED = "not_assessed"                # утверждённый профиль есть, оценки нет
    NO_APPROVED_PROFILE = "no_approved_profile"  # у должности нет утверждённого профиля в этом контуре


class StaleReason(StrEnum):
    ALGORITHM_CHANGED = "algorithm_changed"  # другая версия алгоритма или промпта оценки
    TEXT_CHANGED = "text_changed"            # оценка по прежней версии очищенного текста
    PROFILE_CHANGED = "profile_changed"      # оценка по прежней версии профиля требований


@dataclass
class AssessmentState:
    """Что показывать по оценке одного кандидата на одной должности."""
    status: AssessmentStatus
    # Оценка, которую показываем: актуальная (ready) или устаревшая (stale). Иначе None.
    assessment: Assessment | None = None
    stale_reason: StaleReason | None = None


def resolve_states(
    session: Session,
    candidate_ids: Sequence[uuid.UUID],
    approved_profile: RequirementProfile | None,
    position_id: uuid.UUID,
    synthetic: bool,
) -> dict[uuid.UUID, AssessmentState]:
    """Статус оценки для каждого кандидата — общий для списка откликов и карточки.

    Правила (api.md п. 2.2, развилка Р2 плана):
    1. нет утверждённого профиля в контуре → no_approved_profile;
    2. есть текущая оценка по утверждённому профилю → ready, но если карточка этой оценки
       извлечена не из текущей версии текста → stale (text_changed), а алгоритм или
       промпт оценки отличается от текущего → stale (algorithm_changed);
    3. есть только текущая оценка по другому профилю этой должности в том же контуре
       (утверждённый профиль с тех пор сменился) → stale (profile_changed);
    4. иначе → not_assessed.
    Запросов фиксированное число на любое количество кандидатов.
    """
    if approved_profile is None:
        return {cid: AssessmentState(AssessmentStatus.NO_APPROVED_PROFILE) for cid in candidate_ids}
    if not candidate_ids:
        return {}

    current_text_ids = dict(
        session.execute(
            select(CandidateText.candidate_id, CandidateText.id).where(
                CandidateText.candidate_id.in_(candidate_ids), CandidateText.is_current
            )
        ).all()
    )
    rows = session.execute(
        select(Assessment, CandidateCard.candidate_text_id)
        .join(RequirementProfile, RequirementProfile.id == Assessment.profile_id)
        .join(CandidateCard, CandidateCard.id == Assessment.card_id)
        .where(
            Assessment.candidate_id.in_(candidate_ids),
            Assessment.is_current,
            RequirementProfile.position_id == position_id,
            RequirementProfile.is_synthetic == synthetic,
        )
        # Самая свежая оценка первой: при нескольких старых профилях берём последнюю.
        .order_by(Assessment.created_at.desc(), Assessment.version.desc())
    ).all()

    on_approved: dict[uuid.UUID, tuple[Assessment, uuid.UUID]] = {}
    on_other: dict[uuid.UUID, Assessment] = {}
    for assessment, card_text_id in rows:
        if assessment.profile_id == approved_profile.id:
            on_approved[assessment.candidate_id] = (assessment, card_text_id)
        else:
            on_other.setdefault(assessment.candidate_id, assessment)

    states = {}
    for cid in candidate_ids:
        if cid in on_approved:
            assessment, card_text_id = on_approved[cid]
            if card_text_id != current_text_ids.get(cid):
                states[cid] = AssessmentState(AssessmentStatus.STALE, assessment, StaleReason.TEXT_CHANGED)
            elif (assessment.algorithm_version != ALGORITHM_VERSION
                  or assessment.prompt_version != ASSESS_PROMPT_VERSION):
                states[cid] = AssessmentState(AssessmentStatus.STALE, assessment, StaleReason.ALGORITHM_CHANGED)
            else:
                states[cid] = AssessmentState(AssessmentStatus.READY, assessment)
        elif cid in on_other:
            states[cid] = AssessmentState(AssessmentStatus.STALE, on_other[cid], StaleReason.PROFILE_CHANGED)
        else:
            states[cid] = AssessmentState(AssessmentStatus.NOT_ASSESSED)
    return states


def assessment_texts(session: Session, *groups: Iterable[Any]) -> dict[uuid.UUID, str]:
    """Тексты всех версий, на которые ссылаются цитаты строк оценки (formal_checks, competency_scores),
    одним запросом. Цитаты могут лежать в альтернативах и в индикаторах details."""
    ids: set[uuid.UUID] = set()
    for group in groups:
        for row in group:
            items = list(row.evidence or [])
            for alt in getattr(row, "alternatives", None) or []:
                items.extend(alt.get("evidence", []))
            for indicator in (getattr(row, "details", None) or {}).get("indicators", []):
                items.extend(indicator["evidence"])
            ids.update(uuid.UUID(str(item["candidate_text_id"])) for item in items)
    if not ids:
        return {}
    return dict(session.execute(select(CandidateText.id, CandidateText.text).where(CandidateText.id.in_(ids))).all())


def evidence_with_utf16(items: Iterable[dict[str, Any]], texts: dict[uuid.UUID, str]) -> list[dict[str, Any]]:
    """Цитата + границы UTF-16 по тексту, на который она ссылается (в том числе прежней версии)."""
    result = []
    for item in items:
        text_id = uuid.UUID(str(item["candidate_text_id"]))
        utf16_start, utf16_end = utf16_offsets(texts[text_id], item["start"], item["end"])
        result.append({"candidate_text_id": text_id, "quote": item["quote"], "start": item["start"],
                       "end": item["end"], "utf16_start": utf16_start, "utf16_end": utf16_end})
    return result
