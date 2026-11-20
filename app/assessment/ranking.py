"""Светофор и порядок откликов одной вакансии (бриф «Светофор и порядок откликов», 20.11.2026).

Процента пригодности нет. Отклик получает группу по формальному итогу, место внутри вакансии
и строку причины. Расчёт — только код по сохранённой оценке, без модели и без весов.

Группы (сверху вниз):
- ready    🟢 «Готов к звонку»        — формально met, нет ручной сверки;
- clarify  🟡 «Нужно уточнить»        — unknown или противоречие в обязательной группе компетенции;
- not_met  🔴 «Формально не проходит» — подтверждённое несоответствие обязательному требованию;
- needs_action ⚪ «Нужна оценка» / «Другая публикация» — оценки нет, она устарела, нет профиля
  или отклик на другую публикацию. Это задача для HR или системы, а не оценка человека; места нет.

Порядок внутри группы — по ключам по очереди, без весов (внутри одной вакансии у всех один
профиль, поэтому счётчики сравнимы):
1) меньше открытых вопросов по обязательным формальным требованиям этапа screening (unknown
   или строки проверки нет — так же считает итог formal_result);
2) меньше противоречий по обязательным индикаторам компетенций;
3) больше подтверждённых обязательных индикаторов;
4) больше подтверждённых желательных;
5) раньше откликнулся; затем код кандидата (стабильность).

Красный — подсказка, а не отказ: функция никого не скрывает и не отклоняет.
"""
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

Group = Literal["ready", "clarify", "not_met", "needs_action"]

GROUP_ORDER: dict[str, int] = {"ready": 0, "clarify": 1, "not_met": 2, "needs_action": 3}
GROUP_TITLE: dict[str, str] = {
    "ready": "Готов к звонку", "clarify": "Нужно уточнить",
    "not_met": "Формально не проходит", "needs_action": "Требует действия",
}
_NEEDS_ACTION_REASON = {
    "not_assessed": "Нужна оценка: отклик ещё не оценивался",
    "stale": "Нужна переоценка: резюме, профиль или алгоритм изменились",
    "no_approved_profile": "Нет утверждённого профиля должности — оценить нельзя",
    "not_applicable": "Отклик на другую публикацию — к этой вакансии не применяется",
    "mapping_required": "Публикация не сопоставлена с должностью — нужна проверка",
}
_MAX_TITLES = 2  # сколько пробелов назвать в строке причины


@dataclass
class RankInput:
    """Всё, что нужно для места отклика; строится из сохранённой оценки (rank_input) или вручную в тестах."""
    key: Any                                  # обычно application_id
    candidate_code: str
    assessment_status: str                    # ready | stale | not_assessed | no_approved_profile | …
    applied_at: date | None = None
    formal_result: str | None = None          # met | unknown | not_met
    formal_preliminary: bool = False
    open_mandatory: list[str] = field(default_factory=list)       # формальные unknown (заголовки пробелов)
    not_met_mandatory: list[str] = field(default_factory=list)    # обязательные not_met (описания)
    manual_review: list[str] = field(default_factory=list)        # обязательные группы с ручной сверкой
    mandatory_confirmed: int = 0
    mandatory_contradicted: int = 0
    mandatory_no_info: int = 0
    mandatory_total: int = 0
    desired_confirmed: int = 0
    desired_total: int = 0


@dataclass
class RankResult:
    key: Any
    group: Group
    position: int | None        # место внутри вакансии (1…N) для ready/clarify/not_met; None для needs_action
    reason: str


def group_of(item: RankInput) -> Group:
    if item.assessment_status != "ready" or item.formal_result is None:
        return "needs_action"
    if item.formal_result == "not_met":
        return "not_met"
    if item.formal_result == "unknown" or item.manual_review:
        return "clarify"
    return "ready"


def open_questions(item: RankInput) -> int:
    """Вопросы к уточнению по обязательным формальным требованиям (unknown или не проверено).
    Навыки без сведений сюда не входят: их учитывает ключ «подтверждённые обязательные»."""
    return len(item.open_mandatory)


def sort_key(item: RankInput) -> tuple:
    return (
        GROUP_ORDER[group_of(item)],
        open_questions(item),
        item.mandatory_contradicted,
        -item.mandatory_confirmed,
        -item.desired_confirmed,
        item.applied_at or date.max,
        item.candidate_code,
    )


def rank(items: Iterable[RankInput]) -> list[RankResult]:
    """Упорядочить отклики вакансии и выдать место и причину каждому. Возвращает в порядке выдачи."""
    ordered = sorted(items, key=sort_key)
    results, position = [], 0
    for item in ordered:
        group = group_of(item)
        if group != "needs_action":
            position += 1
        results.append(RankResult(item.key, group, position if group != "needs_action" else None, reason(item)))
    return results


def reason(item: RankInput) -> str:
    """Одна строка: почему у отклика такой цвет и такое место (шаблоны брифа, раздел 4)."""
    group = group_of(item)
    if group == "needs_action":
        return _NEEDS_ACTION_REASON.get(item.assessment_status, "Нужна оценка")
    skills = _skills(item)
    if group == "not_met":
        return "Не проходит: " + _titles(item.not_met_mandatory)
    if group == "ready":
        head = "Все обязательные подтверждены"
        if item.formal_preliminary:
            head += " · нужен документ"
        return f"{head} · {skills}" if skills else head
    parts = []
    if item.open_mandatory:
        count = open_questions(item)
        parts.append(f"{count} {_plural(count, 'вопрос', 'вопроса', 'вопросов')} к уточнению: "
                     + _titles(item.open_mandatory))
    if item.manual_review:
        parts.append("Сверить противоречие: " + _titles(item.manual_review))
    if skills:
        parts.append(skills)
    return " · ".join(parts)


def _skills(item: RankInput) -> str:
    parts = []
    if item.mandatory_total:
        parts.append(f"{item.mandatory_confirmed} из {item.mandatory_total} обязательных")
    if item.desired_total:
        parts.append(f"{item.desired_confirmed} из {item.desired_total} желательных")
    return "навыки: " + ", ".join(parts) if parts else ""


def _titles(values: list[str]) -> str:
    shown = ", ".join(values[:_MAX_TITLES])
    rest = len(values) - _MAX_TITLES
    return shown + (f" и ещё {rest}" if rest > 0 else "")


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# --- Из сохранённой оценки -------------------------------------------------------------

def rank_input(*, key: Any, candidate_code: str, assessment_status: str, applied_at: date | None,
               assessment=None, profile=None) -> RankInput:
    """Собрать вход из Assessment (formal_checks, competency_scores.details) и профиля оценки.
    Только формальные требования этапа screening; итог — тот, что сохранил оценщик."""
    item = RankInput(key=key, candidate_code=candidate_code, assessment_status=str(assessment_status),
                     applied_at=applied_at)
    if assessment is None or profile is None:
        return item
    item.formal_result = _value(assessment.formal_result)
    item.formal_preliminary = bool(assessment.formal_preliminary)
    checks = {c.requirement_id: c for c in assessment.formal_checks}
    gate = [r for r in profile.formal_requirements
            if r.is_mandatory and _value(r.check_stage) == "screening"]
    for requirement in sorted(gate, key=lambda r: (r.sort_order or 0, r.key)):
        check = checks.get(requirement.id)
        result = _value(check.result) if check is not None else "unknown"
        if result == "unknown":
            title = (_gap_title(check) if check is not None else None) or requirement.description
            if title not in item.open_mandatory:  # одинаковый пробел у двух требований — один вопрос
                item.open_mandatory.append(title)
        elif result == "not_met":
            item.not_met_mandatory.append(requirement.description)
    competencies = {c.id: c for c in profile.competencies}
    for score in assessment.competency_scores:
        details = score.details or {}
        mandatory, desired = details.get("mandatory") or {}, details.get("desired") or {}
        item.mandatory_confirmed += mandatory.get("confirmed", 0)
        item.mandatory_contradicted += mandatory.get("contradicted", 0)
        item.mandatory_no_info += mandatory.get("no_info", 0)
        item.mandatory_total += mandatory.get("total", 0)
        item.desired_confirmed += desired.get("confirmed", 0)
        item.desired_total += desired.get("total", 0)
        competency = competencies.get(score.competency_id)
        for group in details.get("groups", []):
            if group.get("manual_review") and group.get("is_mandatory"):
                item.manual_review.append(competency.name if competency else group["key"])
    return item


def _gap_title(check) -> str | None:
    """Заголовок пробела из explanation «[resume] {JSON}» (assessment.md)."""
    _, _, body = (check.explanation or "").partition(" ")
    try:
        return json.loads(body).get("gap") if body.startswith("{") else None
    except json.JSONDecodeError:
        return None


def _value(value):
    return getattr(value, "value", value)
