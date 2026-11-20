"""Даты неполной точности и стаж по периодам работы.

Дата в карточке пишется с той точностью, что в резюме: «2019», «2024-05» или «2024-05-17».
Такая дата — это не точка, а диапазон дней: «2019» — с 1 января по 31 декабря.

Стаж считается по правилам контракта оценки (docs/contracts/assessment.md, п. 4.3):
- единица — месяц, обе границы периода включительно (как считает hh.ru: май 2024 — май 2025 = 13 мес.);
- пересекающиеся периоды сливаются, месяц не считается дважды;
- текущее место работы — до месяца `as_of`;
- неполные даты дают границы: нижняя L — самое позднее начало и самый ранний конец,
  верхняя U — самое раннее начало и самый поздний конец; период без начала или конца — U = ∞.

Пример: «2019 — 2021» → L = 14 мес. (дек. 2019 — янв. 2021), U = 36 мес. (янв. 2019 — дек. 2021),
оценка (L + U) / 2 = 25 мес. ≈ 2,1 года. Порог 24 мес. → `unknown`, порог 12 мес. → `met`.
"""
import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

# «2019», «2024-05», «2024-05-17». Проверка дня по календарю — в date_range.
PARTIAL_DATE = r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$"

# Для общего коммерческого стажа (контракт оценки, п. 4.3): работа и подряд точно считаются,
# стажировка и период без вида — только в верхнюю границу, проект — не считается.
LOWER_KINDS = frozenset({"work", "contract"})
UPPER_KINDS = frozenset({"work", "contract", "internship", None})


def date_range(value: str) -> tuple[date, date]:
    """Первый и последний день, которые может означать дата: «2019» → 01.01.2019–31.12.2019."""
    parts = [int(p) for p in value.split("-")]
    if len(parts) == 1:
        return date(parts[0], 1, 1), date(parts[0], 12, 31)
    year, month = parts[0], parts[1]
    if len(parts) == 2:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    day = date(year, month, parts[2])  # ValueError на «2024-02-30»
    return day, day


def _month(day: date) -> int:
    return day.year * 12 + day.month - 1


class _Period(Protocol):
    start: str | None
    end: str | None
    is_current: bool
    kind: object


@dataclass(frozen=True)
class ExperienceBounds:
    """Стаж в месяцах: точно не меньше `lower`, не больше `upper` (None — верхней границы нет)."""
    lower: int
    upper: int | None
    undated: int  # периодов без начала или без конца: из-за них upper = None

    @property
    def estimate(self) -> float | None:
        """Средняя оценка для показа и сортировки; для решения по порогу — verdict."""
        return None if self.upper is None else (self.lower + self.upper) / 2

    def verdict(self, min_months: int) -> str:
        """Исход по порогу только по периодам: met при L ≥ T, not_met при U < T, иначе unknown."""
        if self.lower >= min_months:
            return "met"
        if self.upper is not None and self.upper < min_months:
            return "not_met"
        return "unknown"


def _union_months(intervals: Iterable[tuple[int, int]]) -> int:
    total, last_end = 0, None
    for start, end in sorted(intervals):
        if last_end is not None and start <= last_end:
            if end > last_end:
                total += end - last_end
                last_end = end
            continue
        total += end - start + 1
        last_end = end
    return total


def experience_bounds(
    periods: Iterable[_Period],
    as_of: date,
    *,
    lower_kinds: frozenset = LOWER_KINDS,
    upper_kinds: frozenset = UPPER_KINDS,
) -> ExperienceBounds:
    """Границы стажа по периодам карточки (`Experience`). `as_of` — дата, на которую считаем."""
    lower: list[tuple[int, int]] = []
    upper: list[tuple[int, int]] = []
    undated = 0
    for period in periods:
        kind = getattr(period.kind, "value", period.kind)
        if kind not in upper_kinds:
            continue
        end_text = as_of.isoformat() if period.is_current else period.end
        if period.start is None or end_text is None:
            undated += 1
            continue
        start_lo, start_hi = date_range(period.start)
        end_lo, end_hi = date_range(end_text)
        if _month(start_lo) <= _month(min(end_hi, as_of)):
            upper.append((_month(start_lo), _month(min(end_hi, as_of))))
        if kind in lower_kinds and _month(start_hi) <= _month(end_lo):
            lower.append((_month(start_hi), _month(end_lo)))
    return ExperienceBounds(
        lower=_union_months(lower),
        upper=None if undated else _union_months(upper),
        undated=undated,
    )
