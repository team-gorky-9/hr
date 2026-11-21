"""3B: вакансии по присланному резюме (wave-3-matching-stage-1) на сохранённых учебных оценках.

Одна учебная кандидатская запись: оценки по python-dev (met) и qa-manual (unknown), утверждённый, но
не оценённый frontend-dev и закрытая вакансия. Модель — FakeLLMClient, живой LLM не вызывается."""
import copy
import uuid

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.assessment.fixtures import create_fixture_profile
from app.db.models import Application, Assessment
from app.db.session import get_session
from app.main import create_app
from app.search import api as search_api
from tests import factories as f
from tests.posting_helpers import posting_registry  # noqa: F401 (фикстура)
from tests.test_api_interview import FIXTURE, STAZH, assess, case, training_profile

PATH = "/api/v1/matching/vacancies"
HR = {"X-User-Login": "hr_demo"}


def approved_copy(session, position_code):
    fixture = copy.deepcopy(FIXTURE)
    fixture["profile"]["position_code"] = position_code
    return f.approve(session, create_fixture_profile(session, fixture))


def vacancy(number, position_code, profile=None, **changes):
    snapshot = {
        "ref": {"system": "legacy-hr", "id": f"00000000-0000-4000-8000-0000000000b{number}"}, "revision": 1,
        "title": f"Учебная вакансия {position_code}", "description": "Учебное объявление",
        "position_code": position_code, "status": "published", "contour": "training",
        "observed_at": "2026-11-21T09:00:00+03:00",
        "profile_ref": {"system": "legacy-hr", "id": str(profile.id), "version": profile.version} if profile else None,
    }
    return snapshot | changes


def client_for(session, monkeypatch):
    monkeypatch.setattr(search_api.settings, "hr_search_work_token", SecretStr("test-work-search"))
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def setup(session):
    python = training_profile(session)
    data = case(session, python, "py-9401", statement=STAZH)  # python-dev: met
    qa = approved_copy(session, "qa-manual")
    assess(session, qa, data["candidate"])                      # qa-manual: unknown (стаж не указан)
    frontend = approved_copy(session, "frontend-dev")           # утверждён, оценки нет
    session.commit()
    return data, python, qa, frontend


def test_items_needs_evaluation_and_excluded(session, monkeypatch, posting_registry):  # noqa: F811
    data, python, qa, frontend = setup(session)
    before = (session.scalar(select(func.count()).select_from(Application)),
              session.scalar(select(func.count()).select_from(Assessment)))
    body = {"candidate_id": str(data["candidate"].id), "contour": "training", "vacancies": [
        vacancy(1, "qa-manual", qa), vacancy(2, "python-dev", python), vacancy(3, "frontend-dev", frontend),
        vacancy(4, "python-dev", python, status="closed"), vacancy(5, "python-dev"),
        vacancy(6, "hr-consultant", python),  # тот же профиль, но другая должность — не сопоставляется
    ]}
    with client_for(session, monkeypatch) as client:
        response = client.post(PATH, headers=HR, json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert (result["source_mode"], result["contour"]) == ("provided", "training")
        assert result["current_text_id"]
        assert [(i["vacancy_ref"]["id"][-2:], i["formal_result"]) for i in result["items"]] == [
            ("b2", "met"), ("b1", "unknown")]  # met → unknown → not_met
        met, unknown = result["items"]
        assert met["reason"].startswith("Обязательные требования выполнены")
        assert unknown["reason"].startswith("Нет сведений: ") and unknown["assessment_id"]
        assert {(n["vacancy_ref"]["id"][-2:], n["reason"]) for n in result["needs_evaluation"]} == {
            ("b3", "not_assessed"), ("b5", "no_profile_ref"), ("b6", "profile_mismatch")}
        assert result["excluded"] == [{"vacancy_ref": body["vacancies"][3]["ref"], "reason": "closed"}]
        # Перечитывание даёт тот же ответ: данные берутся из сохранённых оценок.
        assert client.post(PATH, headers=HR, json=body).json() == result
    after = (session.scalar(select(func.count()).select_from(Application)),
             session.scalar(select(func.count()).select_from(Assessment)))
    assert after == before  # ни откликов, ни оценок не создано


def test_without_ready_assessments_hr_sees_what_to_evaluate(session, monkeypatch, posting_registry):  # noqa: F811
    data, python, qa, frontend = setup(session)
    body = {"candidate_id": str(data["candidate"].id), "contour": "training", "vacancies": [
        vacancy(3, "frontend-dev", frontend), vacancy(7, "python-dev", None, profile_ref={
            "system": "catalog", "id": str(uuid.uuid4()), "version": 1})]}
    with client_for(session, monkeypatch) as client:
        result = client.post(PATH, headers=HR, json=body).json()
    assert result["items"] == []
    assert [n["reason"] for n in result["needs_evaluation"]] == ["not_assessed", "unmapped_profile"]


def test_access_contour_and_inputs(session, monkeypatch, posting_registry):  # noqa: F811
    data, python, qa, frontend = setup(session)
    candidate_id = str(data["candidate"].id)
    one = [vacancy(2, "python-dev", python)]
    with client_for(session, monkeypatch) as client:
        assert client.post(PATH, headers={"X-User-Login": "dept_demo"},
                           json={"candidate_id": candidate_id, "contour": "training", "vacancies": one}).status_code == 403
        working = client.post(PATH, headers=HR, json={"candidate_id": candidate_id, "contour": "working",
                                                      "vacancies": one})
        assert (working.status_code, working.json()["error"]["code"]) == (401, "SEARCH_AUTH_REQUIRED")
        foreign = client.post(PATH, headers={**HR, "Authorization": "Bearer test-work-search"},
                              json={"candidate_id": candidate_id, "contour": "working", "vacancies": one})
        assert (foreign.status_code, foreign.json()["error"]["code"]) == (409, "CONTOUR_MISMATCH")
        missing = client.post(PATH, headers=HR, json={"candidate_id": str(uuid.uuid4()), "contour": "training",
                                                      "vacancies": one})
        assert (missing.status_code, missing.json()["error"]["code"]) == (404, "CANDIDATE_NOT_FOUND")
        other_contour = client.post(PATH, headers=HR, json={"candidate_id": candidate_id, "contour": "training",
                                                            "vacancies": [vacancy(2, "python-dev", python, contour="working")]})
        assert other_contour.json()["excluded"][0]["reason"] == "other_contour"
        for bad in ({"vacancies": []}, {"vacancies": one * 2}, {"vacancies": [vacancy(2, "python-dev") | {"ref": {"system": "legacy-hr", "id": str(uuid.uuid4())}}
                                   for _ in range(51)]},
                    {"limit": 0}, {"extra": 1}):
            payload = {"candidate_id": candidate_id, "contour": "training", "vacancies": one} | bad
            assert client.post(PATH, headers=HR, json=payload).status_code == 422, bad
