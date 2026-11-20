"""Поиск цитаты и расчёт стажа — без модели и без базы.

Случаи стажа взяты из правил, согласованных с Давидом и Родионом 20.11.2026.
"""
import math
import uuid

import pytest

from app.assessment.evidence import resolve_quote
from app.assessment.experience import (
    Period,
    Statement,
    commercial_months,
    decide_commercial,
    period_bounds,
)
from app.schemas.card import evidence_matches

TEXT_ID = uuid.uuid4()
BASE = "Написал API-тесты для сервиса заявок."


# --- Цитаты ------------------------------------------------------------------

def resolve(text, quote, **kw):
    return resolve_quote(text, quote, candidate_text_id=TEXT_ID, **kw)


def test_exact_quote_gets_code_offsets():
    found = resolve(BASE + "\nОбщий коммерческий опыт — 3 года.", "Общий коммерческий опыт — 3 года.")
    assert (found.evidence.start, found.evidence.end) == (38, 71)
    assert not found.ambiguous_location


def test_soft_match_keeps_original_slice():
    text = "Работал   с  ёлками — «Ёж»."
    found = resolve(text, 'Работал с елками - "Еж".')
    assert found.evidence.quote == text
    assert evidence_matches(text, found.evidence)


def test_hallucinated_quote_is_not_found():
    assert resolve(BASE, "Руководил отделом") is None
    assert resolve(BASE, "") is None


def test_emoji_before_quote():
    text = "🙂 " + BASE
    found = resolve(text, BASE)
    assert (found.evidence.start, found.evidence.end) == (2, 39)


def test_repeated_phrase_uses_context_or_flags():
    text = "Организация 1\nPython\nОрганизация 2\nPython"
    by_context = resolve(text, "Python", context_before="Организация 2")
    assert by_context.evidence.start == text.rindex("Python") and not by_context.ambiguous_location
    no_context = resolve(text, "Python")
    assert no_context.evidence.start == text.index("Python") and no_context.ambiguous_location


# --- Границы периодов ----------------------------------------------------------

@pytest.mark.parametrize(
    ("period", "as_of", "low", "high"),
    [
        (Period("2021-01", "2022-12", kind="work"), "2026-11", 24, 24),        # включительно
        (Period("2025-01", None, is_current=True, kind="work"), "2026-11", 23, 23),
        (Period("2019", "2023", kind="work"), "2026-11", 38, 60),
        (Period("2022", "2022", kind="work"), "2026-11", 0, 12),
        (Period("2021", "2023-06", kind="work"), "2026-11", 19, 30),
        (Period(None, None, kind="work"), "2026-11", 0, math.inf),
    ],
)
def test_single_period_bounds(period, as_of, low, high):
    months = commercial_months([period], as_of=as_of)
    assert (months.low, months.high) == (low, high)


def test_overlap_is_counted_once_inclusive():
    periods = [Period("2021-01", "2023-01", kind="work"), Period("2022-01", "2024-01", kind="work")]
    months = commercial_months(periods, as_of="2026-11")
    assert (months.low, months.high) == (37, 37)


def test_floating_years_do_not_add_to_lower_bound():
    two_same = [Period("2022", "2022", kind="work"), Period("2022", "2022", kind="work")]
    assert (commercial_months(two_same, as_of="2026-11").low, commercial_months(two_same, as_of="2026-11").high) == (0, 12)
    two_years = [Period("2022", "2022", kind="work"), Period("2023", "2023", kind="work")]
    months = commercial_months(two_years, as_of="2026-11")
    assert (months.low, months.high) == (0, 24)


def test_kinds_and_bounds():
    internship = Period("2020-01", "2023-12", kind="internship")
    months = commercial_months([internship], as_of="2026-11")
    assert (months.low, months.high) == (0, 48)  # стажировка только расширяет верхнюю границу
    assert commercial_months([Period("2020-01", "2023-12", kind="project")], as_of="2026-11") is None


def test_period_bounds_guaranteed_empty_for_same_year():
    bounds = period_bounds(Period("2022", "2022"), as_of="2026-11")
    assert bounds.guaranteed is None and bounds.widest is not None


# --- Решение по порогу 24 месяца -------------------------------------------------

T = 24
AS_OF = "2026-11"


def decide(periods=(), statement=None):
    return decide_commercial(list(periods), statement, min_months=T, as_of=AS_OF)


def test_absent_is_unknown():
    assert decide().outcome == "unknown"


@pytest.mark.parametrize(("years", "outcome"), [(3, "met"), (1, "not_met")])
def test_statement_only(years, outcome):
    assert decide(statement=Statement(months=years * 12, commercial=True)).outcome == outcome


def test_overlap_case_is_met_with_37_months():
    result = decide([Period("2021-01", "2023-01", kind="work"), Period("2022-01", "2024-01", kind="work")])
    assert result.outcome == "met" and result.months.low == 37


def test_conflict_statement_vs_periods_is_unknown():
    result = decide([Period("2021-01", "2024-01", kind="work")], Statement(12, commercial=True))
    assert result.outcome == "unknown" and result.conflict


def test_undated_period_is_unknown():
    assert decide([Period(None, None, kind="work")]).outcome == "unknown"


def test_current_job_below_threshold():
    assert decide([Period("2025-01", None, is_current=True, kind="work")]).outcome == "not_met"


def test_year_only_met():
    assert decide([Period("2019", "2023", kind="work")]).outcome == "met"


def test_statement_consistent_with_periods():
    result = decide([Period("2021-01", "2023-12", kind="work")], Statement(36, commercial=True))
    assert result.outcome == "met" and not result.divergence and not result.conflict


def test_undated_period_with_statement_uses_statement():
    result = decide([Period(None, None, kind="work")], Statement(36, commercial=True))
    assert result.outcome == "met" and not result.conflict


def test_same_outcome_with_divergence_is_marked():
    result = decide([Period("2020-01", "2024-12", kind="work")], Statement(36, commercial=True))
    assert result.outcome == "met" and result.divergence


def test_non_commercial_statement_is_upper_bound_only():
    assert decide(statement=Statement(12, commercial=False)).outcome == "not_met"
    assert decide(statement=Statement(36, commercial=False)).outcome == "unknown"


def test_total_statement_below_guaranteed_commercial_is_marked():
    # Резюме написано раньше месяца расчёта: «по н. в.» до as_of даёт больше, чем заявлено.
    result = decide([Period("2023-01", None, is_current=True, kind="work")], Statement(34, commercial=False))
    assert result.outcome == "met" and result.divergence
