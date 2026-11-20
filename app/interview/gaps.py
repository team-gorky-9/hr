"""Сборка пробелов для звонка — только код, без модели (контракт interview.md, §2).

Источники: формальные проверки этапа screening с результатом unknown, индикаторы компетенций
без сведений (группа same_as — одна единица), группы с ручной сверкой и слова из card.missing.
Предварительный вывод по документальному требованию — не вопрос, а просьба о документе.
"""
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# Слова card.missing (assessment.prompts.MISSING_VOCABULARY) → вид требования, к которому относятся.
MISSING_TO_KIND = {
    "длительность коммерческого опыта": "experience",
    "опыт работы": "experience",
    "образование": "education_level",
    "направление подготовки": "education_field",
}

DEFAULT_BUDGET = 6
# Сколько навыков одной компетенции спрашивать одним вопросом. Больше — вопрос не умещается в 300
# символов, модель обрезает его или дробит на ответы с одним ключом (найдено на консультанте: 13 ДК).
UNITS_PER_GAP = 3


@dataclass
class Gap:
    """Один смысловой пробел — один будущий вопрос."""
    gap_ref_id: str
    title: str
    priority: int                       # 1 — обязательное требование … 4 — только желательные индикаторы
    order: tuple[int, ...]              # порядок строк профиля внутри приоритета (и часть компетенции)
    sources: list[dict[str, Any]] = field(default_factory=list)
    acceptance: list[dict[str, Any]] = field(default_factory=list)   # критерии исходных строк
    known_quotes: list[str] = field(default_factory=list)            # что уже найдено в резюме


@dataclass
class GapPlan:
    selected: list[Gap]
    uncovered: list[dict[str, Any]]
    document_requests: list[dict[str, Any]]


def gap_ref_id(source_keys: Iterable[str]) -> str:
    """Зависит только от ключей строк профиля: при переоценке той же пары пробел сохраняет id."""
    digest = hashlib.sha256("|".join(sorted(set(source_keys))).encode()).hexdigest()
    return "gap:" + digest[:12]


def _value(item, name):
    value = getattr(item, name, None)
    return getattr(value, "value", value)


def _explanation(check) -> dict[str, Any]:
    """explanation формальной проверки — «[resume] {JSON}» (assessment.md)."""
    text = check.explanation or ""
    _, _, body = text.partition(" ")
    try:
        return json.loads(body) if body.startswith("{") else {}
    except json.JSONDecodeError:
        return {}


def assemble_gaps(profile, assessment, card_missing: list[str] | None, *, budget: int = DEFAULT_BUDGET) -> GapPlan:
    checks = {c.requirement_id: c for c in assessment.formal_checks}
    gaps: list[Gap] = []
    requests: list[dict[str, Any]] = []
    by_kind: dict[str, Gap] = {}

    for requirement in profile.formal_requirements:
        if _value(requirement, "check_stage") != "screening":
            continue  # строки интервью — общее ядро, не уточнения
        check = checks.get(requirement.id)
        result = _value(check, "result") if check else "unknown"
        if result == "unknown":
            details = _explanation(check) if check else {}
            source = {"type": "formal_check", "requirement_id": str(requirement.id), "key": requirement.key,
                      "result": "unknown" if check else "not_checked"}
            gap = Gap(
                gap_ref_id=gap_ref_id([f"formal:{requirement.key}"]),
                title=details.get("gap") or requirement.description,
                priority=1 if requirement.is_mandatory else 3,
                order=(0, requirement.sort_order),
                sources=[source],
                acceptance=[{"row": requirement.key, "text": requirement.description, **(requirement.acceptance or {})}],
            )
            gaps.append(gap)
            by_kind.setdefault(_value(requirement, "kind"), gap)
        elif check is not None and check.is_preliminary and _value(requirement, "verification") == "documents":
            requests.append({
                "requirement_id": str(requirement.id), "requirement_key": requirement.key,
                "title": requirement.description,
                "reason": "по резюме: " + "; ".join(e.get("quote", "") for e in (check.evidence or [])[:2])
                          + " — подтверждается документом",
            })

    for word in card_missing or []:
        gap = by_kind.get(MISSING_TO_KIND.get(word, ""))
        if gap is not None:  # тот же пробел из карточки — источник, а не второй вопрос
            gap.sources.append({"type": "card_missing", "value": word})

    scores = {s.competency_id: s for s in assessment.competency_scores}
    for competency in profile.competencies:
        gaps.extend(_competency_gaps(competency, scores.get(competency.id)))

    gaps.sort(key=lambda g: (g.priority, g.order))
    selected, rest = gaps[:budget], gaps[budget:]
    uncovered = [{"gap_ref_id": g.gap_ref_id, "title": g.title, "reason": "over_budget"} for g in rest]
    return GapPlan(selected=selected, uncovered=uncovered, document_requests=requests)


def _competency_gaps(competency, score) -> list[Gap]:
    details = (score.details if score is not None else None) or {}
    statuses = {i["key"]: i for i in details.get("indicators", [])}
    groups = {g["key"]: g for g in details.get("groups", [])}
    result: list[Gap] = []

    silent: dict[str, list] = {}  # единица (индикатор или группа same_as) → её индикаторы
    for indicator in competency.indicators:
        if indicator.excluded_from_scoring or _value(indicator, "check_stage") != "screening":
            continue
        unit = f"group:{indicator.same_as}" if indicator.same_as else f"indicator:{indicator.key}"
        group = groups.get(indicator.same_as) if indicator.same_as else None
        status = group["status"] if group else statuses.get(indicator.key, {}).get("status", "no_info")
        if group and group.get("manual_review"):
            continue  # отдельный пробел ниже
        if status == "no_info":
            silent.setdefault(unit, []).append(indicator)

    # Обязательные навыки — в первые вопросы; не больше UNITS_PER_GAP навыков на вопрос.
    units = sorted(silent.items(), key=lambda unit: not any(i.is_mandatory for i in unit[1]))
    for part, start in enumerate(range(0, len(units), UNITS_PER_GAP)):
        chunk = dict(units[start:start + UNITS_PER_GAP])
        indicators = [i for unit in chunk.values() for i in unit]
        mandatory = any(i.is_mandatory for i in indicators)
        result.append(Gap(
            gap_ref_id=gap_ref_id(chunk.keys()),
            title=f"{competency.name}: нет сведений — " + "; ".join(dict.fromkeys(i.text for i in indicators)),
            priority=2 if mandatory else 4,
            order=(1, competency.sort_order, part),
            sources=[{"type": "indicator", "competency_id": str(competency.id), "key": i.key, "status": "no_info"}
                     for i in indicators],
            acceptance=[{"row": i.key, "text": i.text, **(i.acceptance or {})} for i in indicators],
        ))

    for key, group in groups.items():
        if group.get("manual_review"):
            members = [i for i in competency.indicators if i.same_as == key]
            result.append(Gap(
                gap_ref_id=gap_ref_id([f"group:{key}"]),
                title=f"{competency.name}: в резюме есть и подтверждение, и опровержение — сверить",
                priority=2,
                order=(1, competency.sort_order),
                sources=[{"type": "group", "competency_id": str(competency.id), "key": key, "manual_review": True}],
                acceptance=[{"row": i.key, "text": i.text, **(i.acceptance or {})} for i in members],
                known_quotes=[e.get("quote", "") for i in members
                              for e in statuses.get(i.key, {}).get("evidence", [])],
            ))
    return result
