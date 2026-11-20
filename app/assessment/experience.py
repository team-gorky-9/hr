"""Стаж считает код (контракт assessment.md п. 4.3; правила, согласованные 20.11.2026).

Модель только извлекает периоды и фразу «общий опыт N» с цитатами. Здесь:
- месяцы считаются включительно: 2021-01 — 2022-12 = 24;
- у каждого периода две границы: L — месяцы, привязанные к календарю (точно были),
  U — сколько могло быть максимум; периоды без дат дают [0, ∞];
- пересечения сливаются, каждый месяц считается один раз;
- решение по порогу и правило расхождений периодов и заявления.
"""
import math
import re
from datetime import date
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

Outcome = Literal["met", "not_met", "unknown"]
Kind = Literal["work", "contract", "internship", "project", "unknown"]

_YEAR_MONTH = re.compile(r"^(\d{4})(?:-(0[1-9]|1[0-2]))?$")


def month_number(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def parse_point(value: str | None) -> tuple[int, int | None] | None:
    """Preserve year/month precision; full valid card dates count calendar months."""
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        try:
            point = date.fromisoformat(value)
        except ValueError:
            return None
        return point.year, point.month
    found = _YEAR_MONTH.match(value.strip())
    if not found:
        return None
    return int(found.group(1)), int(found.group(2)) if found.group(2) else None


@dataclass(frozen=True)
class Period:
    start: str | None
    end: str | None
    is_current: bool = False
    kind: Kind = "unknown"


@dataclass(frozen=True)
class Span:
    """Промежуток месяцев [first, last] включительно."""
    first: int
    last: int


@dataclass(frozen=True)
class PeriodBounds:
    guaranteed: Span | None   # месяцы, которые точно были (для L)
    widest: Span | None       # самые широкие возможные границы (для U); None — неограничен


def period_bounds(period: Period, *, as_of: str) -> PeriodBounds:
    """Границы одного периода. as_of — месяц расчёта «ГГГГ-ММ» для текущего места работы."""
    start = parse_point(period.start)
    end = parse_point(as_of) if period.is_current else parse_point(period.end)
    if start is None or end is None:
        return PeriodBounds(guaranteed=None, widest=None)
    (sy, sm), (ey, em) = start, end
    latest_start = month_number(sy, sm or 12)
    earliest_start = month_number(sy, sm or 1)
    earliest_end = month_number(ey, em or 1)
    latest_end = month_number(ey, em or 12)
    guaranteed = Span(latest_start, earliest_end) if latest_start <= earliest_end else None
    widest = Span(earliest_start, latest_end) if earliest_start <= latest_end else None
    return PeriodBounds(guaranteed=guaranteed, widest=widest)


def merged_length(spans: Iterable[Span]) -> int:
    """Сколько разных месяцев покрывают промежутки (пересечения считаются один раз)."""
    total, current = 0, None
    for span in sorted(spans, key=lambda s: s.first):
        if current is None or span.first > current.last + 1:
            if current is not None:
                total += current.last - current.first + 1
            current = Span(span.first, span.last)
        else:
            current = Span(current.first, max(current.last, span.last))
    if current is not None:
        total += current.last - current.first + 1
    return total


@dataclass(frozen=True)
class MonthsRange:
    low: int
    high: float  # math.inf, если хоть один учтённый период без дат


# Какие записи входят в границы для «общего коммерческого стажа».
_IN_LOW = {"work", "contract"}
_IN_HIGH = {"work", "contract", "internship", "unknown"}


def commercial_months(periods: Sequence[Period], *, as_of: str) -> MonthsRange | None:
    """Границы коммерческого стажа по периодам. None — подходящих периодов нет совсем."""
    counted = [p for p in periods if p.kind in _IN_HIGH]
    if not counted:
        return None
    bounds = [(p, period_bounds(p, as_of=as_of)) for p in counted]
    low = merged_length(b.guaranteed for p, b in bounds if p.kind in _IN_LOW and b.guaranteed)
    if any(b.widest is None for _, b in bounds):
        high: float = math.inf
    else:
        high = merged_length(b.widest for _, b in bounds)
    return MonthsRange(low=low, high=high)


@dataclass(frozen=True)
class Statement:
    """Фраза «общий (коммерческий) опыт N лет M месяцев»."""
    months: int
    commercial: bool


@dataclass
class ExperienceDecision:
    outcome: Outcome
    from_periods: Outcome | None = None
    from_statement: Outcome | None = None
    months: MonthsRange | None = None
    statement_months: int | None = None
    conflict: bool = False      # исходы разные → ручная сверка
    divergence: bool = False    # исход общий, но заявление не попадает в [L, U]
    notes: list[str] = field(default_factory=list)


def _by_threshold(value: float, threshold: int) -> Outcome:
    return "met" if value >= threshold else "not_met"


def decide_commercial(
    periods: Sequence[Period],
    statement: Statement | None,
    *,
    min_months: int,
    as_of: str,
) -> ExperienceDecision:
    """Итог по порогу min_months для scope=total_commercial (п. 4.3 контракта)."""
    months = commercial_months(periods, as_of=as_of)
    decision = ExperienceDecision(outcome="unknown", months=months)

    if months is not None:
        if months.low >= min_months:
            decision.from_periods = "met"
        elif months.high < min_months:
            decision.from_periods = "not_met"
        else:
            decision.from_periods = "unknown"

    if statement is not None:
        decision.statement_months = statement.months
        if statement.commercial:
            decision.from_statement = _by_threshold(statement.months, min_months)
        elif statement.months < min_months:
            # Общий стаж меньше порога → коммерческий тоже меньше.
            decision.from_statement = "not_met"
        else:
            decision.from_statement = "unknown"
            decision.notes.append("заявлен общий опыт без указания, что он коммерческий")

    p, s = decision.from_periods, decision.from_statement
    if p is None and s is None:
        decision.notes.append("нет сведений о длительности коммерческого опыта")
        return decision
    if s is None:
        decision.outcome = p
        return decision
    if p is None:
        decision.outcome = s
        return decision

    if statement.commercial:
        inside = months is not None and months.low <= statement.months <= months.high
    else:
        # Общий стаж согласуется с периодами, если он не меньше гарантированного коммерческого.
        inside = months is None or months.low <= statement.months
    if s == "unknown":
        # Заявление итог не определяет, но несогласованность с периодами всё равно показываем.
        decision.outcome, decision.divergence = p, not inside
    elif p == s:
        decision.outcome = p
        decision.divergence = not inside
    elif p == "unknown" and inside:
        decision.outcome = s
    else:
        decision.outcome, decision.conflict = "unknown", True
        decision.notes.append("заявленный стаж и периоды дают разный итог: нужна ручная сверка")
    if decision.divergence:
        decision.notes.append("расхождение: заявление не совпадает с периодами, итог от этого не меняется")
    return decision
