"""Светофор и порядок откликов (бриф «Светофор и порядок откликов», вариант C).

Контрольный пример брифа: одни и те же А и Б на двух вакансиях стоят в разном порядке.
Плюс правила групп, ключи порядка по очереди, серые без места и сборка входа из сохранённой оценки."""
import json
import uuid
from datetime import date
from types import SimpleNamespace as NS

from app.assessment.fixtures import create_fixture_profile
from app.assessment.ranking import RankInput, group_of, rank, rank_input, reason
from app.db.models import Assessment
from tests.test_interview_guide import BASE, FIXTURE, assess


def item(key, **fields):
    fields.setdefault("assessment_status", "ready")
    fields.setdefault("candidate_code", key)
    return RankInput(key=key, **fields)


# --- Пример брифа: те же два человека на двух вакансиях ---------------------------------

def test_brief_example_python_developer():
    a = item("А", formal_result="unknown", open_mandatory=["длительность коммерческого опыта"],
             mandatory_confirmed=1, mandatory_no_info=1, mandatory_total=2)
    b = item("Б", formal_result="unknown", open_mandatory=["образование"],
             mandatory_confirmed=0, mandatory_no_info=2, mandatory_total=2, desired_confirmed=1, desired_total=1)
    result = rank([b, a])
    assert [(r.key, r.group, r.position) for r in result] == [("А", "clarify", 1), ("Б", "clarify", 2)]
    assert result[0].reason == ("1 вопрос к уточнению: длительность коммерческого опыта"
                                " · навыки: 1 из 2 обязательных")
    assert result[1].reason == ("1 вопрос к уточнению: образование"
                                " · навыки: 0 из 2 обязательных, 1 из 1 желательных")


def test_brief_example_recruiter_consultant():
    a = item("А", formal_result="not_met", not_met_mandatory=["Направление подготовки из перечня"])
    b = item("Б", formal_result="unknown", open_mandatory=["образование"])
    result = rank([a, b])
    assert [(r.key, r.group, r.position) for r in result] == [("Б", "clarify", 1), ("А", "not_met", 2)]
    assert result[0].reason == "1 вопрос к уточнению: образование"
    assert result[1].reason == "Не проходит: Направление подготовки из перечня"


# --- Группы ---------------------------------------------------------------------------

def test_groups_follow_formal_result_and_manual_review():
    assert group_of(item("x", formal_result="met")) == "ready"
    assert group_of(item("x", formal_result="met", manual_review=["Право"])) == "clarify"
    assert group_of(item("x", formal_result="unknown")) == "clarify"
    assert group_of(item("x", formal_result="not_met", manual_review=["Право"])) == "not_met"


def test_needs_action_has_no_position_and_goes_last():
    stale = item("s", assessment_status="stale", formal_result="met")
    missing = item("n", assessment_status="not_assessed")
    other = item("o", assessment_status="not_applicable")
    red = item("r", formal_result="not_met", not_met_mandatory=["Стаж"])
    result = rank([stale, missing, red, other])
    assert [r.key for r in result] == ["r", "n", "o", "s"]
    assert [r.position for r in result] == [1, None, None, None]
    assert result[1].reason.startswith("Нужна оценка") and result[3].reason.startswith("Нужна переоценка")
    assert result[2].reason.startswith("Отклик на другую публикацию")


def test_red_is_never_dropped():
    reds = [item(f"r{i}", formal_result="not_met", not_met_mandatory=["Стаж"]) for i in range(3)]
    assert len(rank(reds)) == 3


# --- Ключи порядка по очереди ------------------------------------------------------------

def test_keys_apply_in_order_without_weights():
    # Меньше вопросов важнее, чем больше подтверждённых навыков.
    few_questions = item("a", formal_result="unknown", open_mandatory=["стаж"], mandatory_confirmed=0)
    many_skills = item("b", formal_result="unknown", open_mandatory=["стаж", "образование"], mandatory_confirmed=5)
    assert [r.key for r in rank([many_skills, few_questions])] == ["a", "b"]
    # При равных вопросах меньше противоречий важнее подтверждений.
    calm = item("c", formal_result="met", mandatory_contradicted=0, mandatory_confirmed=1)
    torn = item("d", formal_result="met", mandatory_contradicted=1, mandatory_confirmed=3)
    assert [r.key for r in rank([torn, calm])] == ["c", "d"]
    # Затем обязательные, затем желательные, затем дата отклика, затем код.
    m = item("m", formal_result="met", mandatory_confirmed=2, desired_confirmed=0)
    d = item("d2", formal_result="met", mandatory_confirmed=1, desired_confirmed=3)
    early = item("z", formal_result="met", mandatory_confirmed=1, desired_confirmed=3, applied_at=date(2026, 11, 1))
    assert [r.key for r in rank([d, early, m])] == ["m", "z", "d2"]


def test_order_is_stable_for_equal_items():
    items = [item(code, formal_result="met") for code in ("c", "a", "b")]
    assert [r.key for r in rank(items)] == ["a", "b", "c"]


# --- Строка причины --------------------------------------------------------------------

def test_reason_templates():
    ready = item("x", formal_result="met", formal_preliminary=True, mandatory_confirmed=2, mandatory_total=2,
                 desired_confirmed=1, desired_total=3)
    assert reason(ready) == ("Все обязательные подтверждены · нужен документ"
                             " · навыки: 2 из 2 обязательных, 1 из 3 желательных")
    review = item("x", formal_result="met", manual_review=["Знание 25-ФЗ"])
    assert reason(review) == "Сверить противоречие: Знание 25-ФЗ"
    many = item("x", formal_result="unknown", open_mandatory=["стаж", "образование", "гражданство"])
    assert reason(many) == "3 вопроса к уточнению: стаж, образование и ещё 1"
    assert "%" not in reason(ready) + reason(review) + reason(many)


# --- Вход из сохранённой оценки ----------------------------------------------------------

def _req(key, *, mandatory=True, stage="screening", order=0, kind="other"):
    return NS(id=uuid.uuid4(), key=key, kind=kind, description=f"требование {key}", is_mandatory=mandatory,
              check_stage=stage, sort_order=order)


def _check(requirement, result, gap=None, quotes=()):
    body = json.dumps({"gap": gap} if gap else {}, ensure_ascii=False)
    return NS(requirement_id=requirement.id, result=result, explanation=f"[resume] {body}",
              evidence=[{"quote": q} for q in quotes])


def test_rank_input_counts_only_mandatory_screening_and_missing_check_is_a_question():
    exp, edu, nice, talk, cit = (_req("exp"), _req("edu", order=1), _req("nice", mandatory=False),
                                 _req("talk", stage="interview"), _req("cit", order=2))
    comp = NS(id=uuid.uuid4(), name="Право")
    profile = NS(formal_requirements=[cit, nice, talk, edu, exp], competencies=[comp])
    details = {"mandatory": {"confirmed": 1, "contradicted": 1, "no_info": 0, "total": 2},
               "desired": {"confirmed": 1, "contradicted": 0, "no_info": 1, "total": 2},
               "groups": [{"key": "law", "members": ["a", "b"], "is_mandatory": True,
                           "status": "contradicted", "manual_review": True}]}
    assessment = NS(formal_result="unknown", formal_preliminary=False,
                    formal_checks=[_check(exp, "unknown", gap="длительность коммерческого опыта"),
                                   _check(edu, "not_met"), _check(nice, "unknown"), _check(talk, "unknown")],
                    competency_scores=[NS(competency_id=comp.id, details=details)])
    built = rank_input(key=1, candidate_code="py-1", assessment_status="ready", applied_at=None,
                       assessment=assessment, profile=profile)
    assert built.open_mandatory == ["длительность коммерческого опыта", "требование cit"]
    assert built.not_met_mandatory == ["требование edu"]
    assert built.manual_review == ["Право"]
    assert (built.mandatory_confirmed, built.mandatory_contradicted, built.mandatory_total) == (1, 1, 2)
    assert (built.desired_confirmed, built.desired_total) == (1, 2)


def test_rank_input_without_assessment_is_needs_action():
    built = rank_input(key=1, candidate_code="py-1", assessment_status="not_assessed", applied_at=None)
    assert group_of(built) == "needs_action" and reason(built) == "Нужна оценка: отклик ещё не оценивался"


def test_saved_assessments_rank_known_experience_first(session):
    """Две настоящие оценки py-9001 по одному профилю: со стажем — зелёный, без стажа — жёлтый ниже."""
    profile = create_fixture_profile(session, FIXTURE)
    quote = "Общий коммерческий опыт — 3 года."
    unknown_id = assess(session, profile, BASE, "py-9001")
    met_id = assess(session, profile, BASE + "\n" + quote, "py-9002", statement=quote)
    items = []
    for code, assessment_id in (("py-9001", unknown_id), ("py-9002", met_id)):
        saved = session.get(Assessment, assessment_id)
        items.append(rank_input(key=code, candidate_code=code, assessment_status="ready", applied_at=None,
                                assessment=saved, profile=profile))
    result = rank(items)
    assert [(r.key, r.group, r.position) for r in result] == [("py-9002", "ready", 1), ("py-9001", "clarify", 2)]
    assert result[0].reason.startswith("Все обязательные подтверждены")
    assert result[1].reason.startswith("1 вопрос к уточнению: длительность коммерческого опыта")


def test_not_met_reason_names_the_requirement_kind_and_quotes_the_basis():
    exp = _req("exp", kind="experience")
    profile = NS(formal_requirements=[exp], competencies=[])
    assessment = NS(formal_result="not_met", formal_preliminary=False, competency_scores=[],
                    formal_checks=[_check(exp, "not_met", quotes=["Коммерческого опыта   в разработке нет."])])
    built = rank_input(key=1, candidate_code="py-1", assessment_status="ready", applied_at=None,
                       assessment=assessment, profile=profile)
    assert reason(built) == "Не проходит: опыт работы — «Коммерческого опыта в разработке нет.»"
    long = _check(exp, "not_met", quotes=["слово " * 40])
    assessment.formal_checks = [long]
    built = rank_input(key=1, candidate_code="py-1", assessment_status="ready", applied_at=None,
                       assessment=assessment, profile=profile)
    assert reason(built).endswith("…»") and len(reason(built)) < 140
