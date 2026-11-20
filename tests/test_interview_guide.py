"""Гайд интервью (контракт interview.md v0.1): пробелы — кодом, вопросы — моделью с проверкой ключей.

Контрольные примеры §6: py-9001 с неизвестным стажем → один вопрос; кандидат без пробелов → ноль
вызовов модели; одинаковое ядро у разных кандидатов; сбой модели не создаёт гайд."""
import json
import re
import uuid
from types import SimpleNamespace as NS

import pytest

from app.ai import FakeLLMClient, LLMUnavailableError
from app.assessment.fixtures import FIXTURES_DIR, create_fixture_profile, load
from app.assessment.service import assess_candidate
from app.db import repository as repo
from app.db.enums import Channel, DocumentKind, FileFormat
from app.interview import assemble_gaps, build_guide
from app.interview.gaps import gap_ref_id

FIXTURE = load(FIXTURES_DIR / "py-9001.json")
BASE = "Написал API-тесты для сервиса заявок."
IND = FIXTURE["profile"]["competencies"][0]["indicators"][0]["key"]


# --- Сборка пробелов без базы ------------------------------------------------------

def req(key, *, kind="experience", mandatory=True, stage="screening", verification="resume", order=0):
    return NS(id=uuid.uuid4(), key=key, kind=kind, description=f"требование {key}", is_mandatory=mandatory,
              check_stage=stage, verification=verification, acceptance={"met": "даты", "unknown": "нет дат"},
              sort_order=order)


def check(requirement, result, *, gap=None, preliminary=False, evidence=()):
    body = json.dumps({"gap": gap} if gap else {}, ensure_ascii=False)
    return NS(requirement_id=requirement.id, result=result, is_preliminary=preliminary,
              explanation=f"[resume] {body}", evidence=list(evidence))


def indicator(key, *, mandatory=True, stage="screening", same_as=None, excluded=False, order=0):
    return NS(key=key, text=f"индикатор {key}", is_mandatory=mandatory, check_stage=stage, same_as=same_as,
              excluded_from_scoring=excluded, acceptance={}, sort_order=order)


def test_unknown_requirement_and_card_missing_are_one_gap():
    exp = req("exp")
    profile = NS(formal_requirements=[exp], competencies=[])
    assessment = NS(formal_checks=[check(exp, "unknown", gap="длительность коммерческого опыта")], competency_scores=[])
    plan = assemble_gaps(profile, assessment, ["длительность коммерческого опыта", "сопроводительное письмо"])
    assert len(plan.selected) == 1
    gap = plan.selected[0]
    assert gap.title == "длительность коммерческого опыта" and gap.priority == 1
    assert [s["type"] for s in gap.sources] == ["formal_check", "card_missing"]
    assert gap.gap_ref_id == gap_ref_id(["formal:exp"])


def test_preliminary_document_requirement_is_a_document_request_not_a_question():
    edu = req("edu", kind="education_level", verification="documents")
    plan = assemble_gaps(NS(formal_requirements=[edu], competencies=[]),
                         NS(formal_checks=[check(edu, "met", preliminary=True, evidence=[{"quote": "Высшее"}])],
                            competency_scores=[]), [])
    assert plan.selected == [] and plan.document_requests[0]["requirement_key"] == "edu"


def test_interview_rows_met_and_excluded_do_not_become_gaps():
    exp, law = req("exp"), req("law", kind="knowledge", stage="interview", verification="interview")
    comp = NS(id=uuid.uuid4(), name="Тест", sort_order=0, indicators=[
        indicator("i1"), indicator("i2", stage="interview"), indicator("i3", excluded=True)])
    score = NS(competency_id=comp.id, details={"indicators": [{"key": "i1", "status": "confirmed"}], "groups": []})
    plan = assemble_gaps(NS(formal_requirements=[exp, law], competencies=[comp]),
                         NS(formal_checks=[check(exp, "met")], competency_scores=[score]), [])
    assert plan.selected == []


def test_silent_indicators_of_one_competency_are_one_gap_and_same_as_counts_once():
    comp = NS(id=uuid.uuid4(), name="Право", sort_order=0, indicators=[
        indicator("a", same_as="law"), indicator("b", same_as="law"), indicator("c", mandatory=False)])
    score = NS(competency_id=comp.id, details={"indicators": [], "groups": [
        {"key": "law", "members": ["a", "b"], "is_mandatory": True, "status": "no_info", "manual_review": False}]})
    plan = assemble_gaps(NS(formal_requirements=[], competencies=[comp]), NS(formal_checks=[], competency_scores=[score]), [])
    assert len(plan.selected) == 1
    gap = plan.selected[0]
    assert gap.priority == 2 and gap.gap_ref_id == gap_ref_id(["group:law", "indicator:c"])


def test_manual_review_group_is_its_own_gap():
    comp = NS(id=uuid.uuid4(), name="Право", sort_order=0, indicators=[indicator("a", same_as="law"),
                                                                       indicator("b", same_as="law")])
    score = NS(competency_id=comp.id, details={
        "indicators": [{"key": "a", "status": "confirmed", "evidence": [{"quote": "знаю 25-ФЗ"}]},
                       {"key": "b", "status": "contradicted", "evidence": [{"quote": "законы не изучал"}]}],
        "groups": [{"key": "law", "members": ["a", "b"], "is_mandatory": True, "status": "contradicted",
                    "manual_review": True}]})
    plan = assemble_gaps(NS(formal_requirements=[], competencies=[comp]), NS(formal_checks=[], competency_scores=[score]), [])
    assert len(plan.selected) == 1 and "сверить" in plan.selected[0].title
    assert plan.selected[0].known_quotes == ["знаю 25-ФЗ", "законы не изучал"]


def test_budget_keeps_priority_and_lists_the_rest():
    requirements = [req(f"r{n}", mandatory=n < 3, order=n) for n in range(8)]
    plan = assemble_gaps(NS(formal_requirements=requirements, competencies=[]),
                         NS(formal_checks=[check(r, "unknown") for r in requirements], competency_scores=[]),
                         [], budget=4)
    assert [g.title for g in plan.selected][:3] == ["требование r0", "требование r1", "требование r2"]
    assert len(plan.uncovered) == 4 and {u["reason"] for u in plan.uncovered} == {"over_budget"}


# --- Гайд по сохранённой оценке (база) ----------------------------------------------

def make_candidate(session, text, code):
    document, _ = repo.add_source_document(
        session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.TXT,
        original_path=f"Синтетика/{code}.txt", raw_text=f"{code}\n{text}")
    return repo.create_candidate(session, code=code, source_document_id=document.id, redacted_text=text,
                                 redaction_method="test", is_synthetic=True)


def assess(session, profile, text, code, statement=None):
    def respond(role, schema, system, user):
        if schema == "CandidateCard":
            return {"missing": [] if statement else ["длительность коммерческого опыта"]}
        if schema == "FormalExtraction":
            return {"statement": {"years": 3, "commercial": True, "quote": statement}} if statement else {}
        return {"indicators": [{"indicator_key": IND, "status": "confirmed", "quote": BASE}]}
    candidate = make_candidate(session, text, code)
    return assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id, llm=FakeLLMClient(respond),
                            mode="technical", as_of="2026-11")


def guide_model(seen):
    def respond(role, schema, system, user):
        refs = re.findall(r'"(?:gap_ref_id|row_key)": "([^"]+)"', user)
        seen.append(user)
        return {"items": [{"ref": r, "question": "С какого по какой месяц длился проект и в каком качестве вы работали?",
                           "good_answer": "Месяц и год начала и окончания, характер работы",
                           "insufficient_answer": "Без дат"} for r in refs]}
    return respond


def test_py9001_unknown_experience_gives_one_question(session):
    profile = create_fixture_profile(session, FIXTURE)
    assessment_id = assess(session, profile, BASE, "py-9001")
    seen = []
    guide = build_guide(session, assessment_id=assessment_id, llm=FakeLLMClient(guide_model(seen)))
    assert len(guide.clarifications) == 1 and guide.model_calls == 1
    question = guide.clarifications[0]
    assert {s["type"] for s in question["sources"]} == {"formal_check", "card_missing"}
    assert question["criterion"]["good_answer"] and question["gap_ref_id"].startswith("gap:")
    assert guide.core == [] and guide.uncovered_gaps == [] and guide.document_requests == [] and guide.is_training
    assert BASE not in seen[0]  # текст резюме в генерацию не уходит


def test_candidate_without_gaps_needs_no_model(session):
    profile = create_fixture_profile(session, FIXTURE)
    quote = "Общий коммерческий опыт — 3 года."
    assessment_id = assess(session, profile, BASE + "\n" + quote, "py-9002", statement=quote)
    llm = FakeLLMClient(lambda *a: pytest.fail("модель не должна вызываться"))
    guide = build_guide(session, assessment_id=assessment_id, llm=llm)
    assert guide.clarifications == [] and guide.model_calls == 0


def test_core_is_shared_through_the_cache(session):
    """Ядро генерируется один раз на версию профиля; со сохранённой рубрикой второй кандидат
    получает те же вопросы без вызова модели."""
    from app.interview.generate import QuestionItem, core_rows

    profile = create_fixture_profile(session, FIXTURE)
    indicator_row = profile.competencies[0].indicators[0]
    indicator_row.check_stage = "interview"  # учебный профиль без строк интервью — делаем одну
    indicator_row.verification = "interview"
    session.flush()
    rows = core_rows(profile)
    assert [r["row_key"] for r in rows] == [IND]
    cache = {IND: QuestionItem(ref=IND, question="Расскажите, как вы проверяли API?", good_answer="пример",
                               insufficient_answer="без примера")}
    first = assess(session, profile, BASE, "py-9003")
    second = assess(session, profile, BASE, "py-9004")
    g1 = build_guide(session, assessment_id=first, llm=FakeLLMClient(guide_model([])), core_cache=cache)
    g2 = build_guide(session, assessment_id=second, llm=FakeLLMClient(guide_model([])), core_cache=cache)
    assert g1.core == g2.core and g1.core[0]["question"] == "Расскажите, как вы проверяли API?"


def test_model_failure_creates_no_guide(session):
    profile = create_fixture_profile(session, FIXTURE)
    assessment_id = assess(session, profile, BASE, "py-9005")
    with pytest.raises(LLMUnavailableError):
        build_guide(session, assessment_id=assessment_id,
                    llm=FakeLLMClient(lambda *a: LLMUnavailableError("таймаут")))


def test_unknown_ref_from_model_is_rejected():
    from pydantic import ValidationError

    from app.interview.generate import _keyed

    with pytest.raises(ValidationError):
        _keyed({"gap:1"}).model_validate({"items": [{"ref": "gap:2", "question": "Вопрос?", "good_answer": "да",
                                                     "insufficient_answer": "нет"}]})
