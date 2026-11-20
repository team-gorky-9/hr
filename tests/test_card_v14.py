"""Карточка v1.4: словарь уровня образования, новые поля, даты неполной точности, стаж."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.card import (
    CandidateCard,
    Course,
    Education,
    EducationLevel,
    Experience,
    normalize_education_level,
)
from app.schemas.periods import experience_bounds


@pytest.mark.parametrize(
    ("raw", "level"),
    [
        # Все формулировки уровня из TXT-откликов архива «Кадры» (1 434 файла).
        ("Высшее образование", EducationLevel.HIGHER),
        ("Высшее образование (Бакалавр)", EducationLevel.HIGHER),
        ("Высшее образование (Магистр)", EducationLevel.HIGHER),
        ("Высшее образование (Кандидат наук)", EducationLevel.HIGHER),
        ("Неоконченное высшее образование", EducationLevel.INCOMPLETE_HIGHER),
        ("Среднее специальное образование", EducationLevel.VOCATIONAL),
        ("Среднее образование", EducationLevel.SECONDARY),
        ("бакалавр", EducationLevel.HIGHER),
        ("специалист", EducationLevel.HIGHER),
        ("колледж", EducationLevel.VOCATIONAL),
        ("высшее", EducationLevel.HIGHER),
        ("Курсы", None),
    ],
)
def test_level_is_normalized(raw, level):
    assert normalize_education_level(raw) == level


def test_free_level_from_old_card_is_read_without_error():
    """Карточка до v1.4 со свободной строкой читается: уровень — по словарю, исходник — в level_raw."""
    old = Education.model_validate({"level": "Высшее образование (Бакалавр)", "degree": "бакалавр"})
    assert (old.level, old.level_raw, old.degree) == (EducationLevel.HIGHER, "Высшее образование (Бакалавр)", "бакалавр")
    unknown = Education.model_validate({"level": "Курсы программирования"})
    assert (unknown.level, unknown.level_raw) == (None, "Курсы программирования")
    same = Education.model_validate({"level": "высшее"})
    assert (same.level, same.level_raw) == (EducationLevel.HIGHER, None)


def test_card_roundtrip_with_new_fields():
    card = CandidateCard.model_validate({
        "education": [{"level": "неоконченное высшее", "status": "in_progress", "course": 4, "field_code": "09.03.03"}],
        "courses": [{"title": "ГМУ", "kind": "retraining", "field": "ГМУ", "completed": True, "hours": 520}],
        "experience": [{"position": "Стажёр", "start": "2023", "end": "2023-08", "kind": "internship"}],
    })
    assert CandidateCard.model_validate(card.model_dump(mode="json")) == card
    assert card.model_dump(mode="json")["education"][0]["level"] == "неоконченное высшее"


@pytest.mark.parametrize("bad", [
    {"education": [{"course": 7}]},
    {"education": [{"field_code": "09.03"}]},
    {"education": [{"status": "graduated"}]},
    {"courses": [{"title": "x", "kind": "webinar"}]},
    {"courses": [{"title": "x", "hours": -1}]},
    {"experience": [{"kind": "volunteer"}]},
])
def test_new_fields_are_checked(bad):
    with pytest.raises(ValidationError):
        CandidateCard.model_validate(bad)


def test_dates_of_any_precision_are_compared_by_range():
    assert Experience(start="2024-05", end="2024").end == "2024"        # тот же год — допустимо
    assert Experience(start="2019", end="2021-03-01").start == "2019"
    with pytest.raises(ValidationError):
        Experience(start="2024-05", end="2023")                           # точно раньше
    with pytest.raises(ValidationError):
        Experience(start="2024-05-17", end="2024-05-16")
    with pytest.raises(ValidationError):
        Experience(start="2024-02-30")                                    # нет такого дня


AS_OF = date(2026, 11, 20)


def test_years_only_give_bounds():
    bounds = experience_bounds([Experience(start="2019", end="2021", kind="work")], AS_OF)
    assert (bounds.lower, bounds.upper, bounds.estimate) == (14, 36, 25)
    assert (bounds.verdict(12), bounds.verdict(24), bounds.verdict(37)) == ("met", "unknown", "not_met")


def test_months_are_inclusive_like_hh():
    bounds = experience_bounds([Experience(start="2024-05", end="2025-05", kind="work")], AS_OF)
    assert (bounds.lower, bounds.upper) == (13, 13)


def test_days_are_counted_to_month():
    bounds = experience_bounds([Experience(start="2024-05-17", end="2025-05-03", kind="work")], AS_OF)
    assert (bounds.lower, bounds.upper) == (13, 13)


def test_overlaps_merge_and_current_job_counts_to_as_of():
    periods = [
        Experience(start="2025-01", end="2025-12", kind="work"),
        Experience(start="2025-06", is_current=True, kind="contract"),  # пересекается с первым
    ]
    bounds = experience_bounds(periods, AS_OF)
    assert (bounds.lower, bounds.upper) == (23, 23)  # янв. 2025 — нояб. 2026


def test_kinds_and_missing_dates():
    periods = [
        Experience(start="2024-01", end="2024-12", kind="work"),
        Experience(start="2023-01", end="2023-06", kind="internship"),  # только в верхнюю
        Experience(start="2022-01", end="2022-12", kind="project"),     # не считается
        Experience(start="2021-01", end="2021-03"),                      # вид не указан → только в верхнюю
    ]
    bounds = experience_bounds(periods, AS_OF)
    assert (bounds.lower, bounds.upper) == (12, 21)
    undated = experience_bounds([*periods, Experience(start="2020-01", kind="work")], AS_OF)
    assert (undated.lower, undated.upper, undated.undated) == (12, None, 1)
    assert undated.verdict(100) == "unknown"
