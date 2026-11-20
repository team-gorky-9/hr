"""Контрольный набор fixtures/assessment согласован сам с собой — без базы.

Вторая половина файла портит копию набора и убеждается, что проверка это замечает:
иначе зелёный результат ничего бы не доказывал.
"""
import copy

import pytest

from app.assessment.fixtures import FIXTURES_DIR, check_fixture, load

PATH = FIXTURES_DIR / "py-9001.json"
BASE = "Написал API-тесты для сервиса заявок."


@pytest.fixture(scope="module")
def fixture():
    return load(PATH)


def case(data, case_id):
    return next(c for c in data["cases"] if c["id"] == case_id)


def problems_of(data, case_id=None):
    common, reports = check_fixture(data)
    if case_id is None:
        return common + [p for r in reports for p in r.problems]
    return next(r for r in reports if r.case_id == case_id).problems


def test_fixture_is_consistent(fixture):
    common, reports = check_fixture(fixture)
    assert common == []
    assert {r.case_id: r.problems for r in reports if r.problems} == {}


def test_fixture_is_marked_synthetic(fixture):
    assert fixture["synthetic"] is True


def test_base_example_from_task(fixture):
    """Ровно то, что задано в постановке: текст, границы, три исхода."""
    base = fixture["texts"]["py-9001/text/base"]["text"]
    assert base == BASE and len(base) == 37
    c1 = case(fixture, "C1-unknown")
    quote = c1["assessment"]["competency_scores"][0]["score"]["evidence"][0]
    assert (quote["quote"], quote["start"], quote["end"]) == (BASE, 0, 37)
    assert c1["card"]["experience_years"] is None
    assert c1["card"]["missing"] == ["длительность коммерческого опыта"]
    outcomes = {c["id"]: c["expect"]["formal_result"] for c in fixture["cases"][:3]}
    assert outcomes == {"C1-unknown": "unknown", "C2-met": "met", "C3-not-met": "not_met"}


def test_quote_keeps_its_place_when_line_is_appended(fixture):
    for key in ("py-9001/text/met-3y", "py-9001/text/not-met-1y"):
        assert fixture["texts"][key]["text"].startswith(BASE)
    for case_id in ("C2-met", "C3-not-met"):
        tests_quote = case(fixture, case_id)["assessment"]["competency_scores"][0]["score"]["evidence"][0]
        assert (tests_quote["start"], tests_quote["end"]) == (0, 37)


def test_every_case_says_who_enforces_it(fixture):
    by_layer = {}
    for c in fixture["cases"]:
        by_layer.setdefault(c["enforced_by"], []).append(c["id"])
    # Ожидания этапа 1 отделены от того, что уже обеспечивает БД.
    # N3 (цитата не из текста карточки) база отклоняет с контракта v1.3, п. 3.2.
    assert set(by_layer["stage_1"]) == {"N5-missing-evidence", "N6-model-unavailable", "N7-draft-profile"}
    assert "N3-stale-text-version" in by_layer["db_v1"]


# --- Порча набора: проверка должна замечать ошибки ---------------------------

def mutated(fixture, change):
    data = copy.deepcopy(fixture)
    change(data)
    return data


def test_detects_wrong_expected_formal_result(fixture):
    data = mutated(fixture, lambda d: case(d, "C1-unknown")["expect"].update(formal_result="met"))
    assert any("formal_result" in p for p in problems_of(data, "C1-unknown"))


def test_detects_moved_quote(fixture):
    def move(d):
        case(d, "C2-met")["assessment"]["formal_checks"][0]["check"]["evidence"][0].update(start=37, end=70)
    assert any("formal_checks[0]" in p for p in problems_of(mutated(fixture, move), "C2-met"))


def test_detects_unverified_quote_shown_in_ui(fixture):
    def show(d):
        # В N1 цитата сдвинута, показывать её как подтверждённую нельзя.
        d_case = case(d, "N1-quote-not-at-offsets")
        d_case["ui"]["evidence"] = copy.deepcopy(case(d, "C1-unknown")["ui"]["evidence"])
    assert any("непроверенная цитата" in p for p in problems_of(mutated(fixture, show), "N1-quote-not-at-offsets"))


def test_detects_wrong_utf16_hint(fixture):
    def break_hint(d):
        case(d, "C5-non-bmp")["ui"]["evidence"][0]["utf16_start"] = 2
    assert any("UTF-16" in p for p in problems_of(mutated(fixture, break_hint), "C5-non-bmp"))


def test_detects_unknown_without_gap(fixture):
    def drop_gap(d):
        case(d, "C1-unknown")["assessment"]["formal_checks"][0]["gap"] = None
    assert any("пробел" in p for p in problems_of(mutated(fixture, drop_gap), "C1-unknown"))


def test_detects_gap_missing_from_card(fixture):
    def drop_missing(d):
        case(d, "C1-unknown")["card"]["missing"] = []
    assert any("card.missing" in p for p in problems_of(mutated(fixture, drop_missing), "C1-unknown"))


def test_detects_id_not_derived_from_key(fixture):
    def break_id(d):
        d["texts"]["py-9001/text/base"]["id"] = "00000000-0000-0000-0000-000000000000"
    assert any("uuid5" in p for p in problems_of(mutated(fixture, break_id)))


def test_detects_unexpected_schema_error(fixture):
    def break_schema(d):
        case(d, "C1-unknown")["card"]["salary"] = 100000
    assert any("схемой" in p for p in problems_of(mutated(fixture, break_schema), "C1-unknown"))


def test_detects_missing_refusal(fixture):
    def approve(d):
        case(d, "N7-draft-profile")["profile_status"] = "approved"
    assert any("отказ" in p for p in problems_of(mutated(fixture, approve), "N7-draft-profile"))
