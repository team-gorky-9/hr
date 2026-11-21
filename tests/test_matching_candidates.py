"""3A: люди под выбранную вакансию (wave-3-matching-stage-1) на учебном корпусе поиска.

Поиск — действующий /search (лексическая ветка, плотная выключена). Статус оценки — по точному
профилю: учебный профиль python-dev из fixtures py-9001 и оценка с FakeLLMClient."""
import uuid

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.db.models import Application, ReserveEntry
from app.db.session import get_session
from app.main import create_app
from app.search import api as search_api
from app.search.demo import load_demo
from tests.posting_helpers import posting_registry  # noqa: F401 (фикстура)
from tests.test_api_interview import case, training_profile

PATH = "/api/v1/matching/candidates"
HR = {"X-User-Login": "hr_demo"}
VACANCY_ID = "00000000-0000-4000-8000-0000000000a1"


def snapshot(**changes):
    vacancy = {
        "ref": {"system": "legacy-hr", "id": VACANCY_ID}, "revision": 1,
        "title": "Аналитик информационных систем (учебная)",
        "description": "Длинное объявление: " + "анализ требований, согласование с подрядчиком. " * 40,
        "position_code": "analyst-training", "status": "published", "contour": "training",
        "observed_at": "2026-11-21T09:00:00+03:00", "profile_ref": None,
        "search_query": "анализ и согласование требований к ИС",
    }
    return vacancy | changes


def client_for(session, monkeypatch):
    monkeypatch.setattr(search_api.settings, "hr_search_semantic_enabled", False)
    monkeypatch.setattr(search_api.settings, "hr_search_work_token", SecretStr("test-work-search"))
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def counts(session):
    return (session.scalar(select(func.count()).select_from(Application)),
            session.scalar(select(func.count()).select_from(ReserveEntry)))


def test_vacancy_query_finds_fragment_and_missing_term_gives_empty(session, monkeypatch):
    load_demo(session)
    before = counts(session)
    with client_for(session, monkeypatch) as client:
        response = client.post(PATH, headers=HR, json={"vacancy": snapshot(), "limit": 5})
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["source_mode"], body["contour"], body["unit"], body["matching_status"]) == (
            "provided", "training", "candidate_record", "completed")
        assert (body["vacancy_ref"]["id"], body["vacancy_revision"]) == (VACANCY_ID, 1)
        assert body["observed_at"] == "2026-11-21T09:00:00+03:00"
        top = body["items"][0]
        assert top["candidate_code"] == "search-9015"
        assert "Анализ и согласование требований к ИС" in top["evidence"]["fragment"]
        text = client.get(f"/api/v1/candidate-texts/{top['evidence']['candidate_text_id']}", headers=HR).json()["text"]
        assert top["evidence"]["fragment"] in text  # цитата проверяема по исходному очищенному тексту
        assert {(i["qualification_status"], i["qualification_reason"]) for i in body["items"]} == {
            ("not_evaluated", "no_profile_ref")}

        missing = client.post(PATH, headers=HR, json={
            "vacancy": snapshot(), "filters": {"required_terms": ["SAP ERP"]}})
        assert (missing.status_code, missing.json()["items"]) == (200, [])
    assert counts(session) == before  # подбор не создаёт откликов и записей резерва


def test_closed_vacancy_contour_and_roles_are_rejected(session, monkeypatch):
    load_demo(session)
    with client_for(session, monkeypatch) as client:
        closed = client.post(PATH, headers=HR, json={"vacancy": snapshot(status="closed")})
        assert (closed.status_code, closed.json()["error"]["code"]) == (409, "VACANCY_NOT_PUBLISHED")
        working = client.post(PATH, headers=HR, json={"vacancy": snapshot(contour="working")})
        assert (working.status_code, working.json()["error"]["code"]) == (401, "SEARCH_AUTH_REQUIRED")
        department = client.post(PATH, headers={"X-User-Login": "dept_demo"}, json={"vacancy": snapshot()})
        assert department.status_code == 403
        assert client.post(PATH, json={"vacancy": snapshot()}).status_code == 401
        for bad in (snapshot(search_query="   "), snapshot(search_query="а" * 513),
                    snapshot(observed_at="2026-11-21T09:00:00"), snapshot(extra=1)):
            assert client.post(PATH, headers=HR, json={"vacancy": bad}).status_code == 422
        # Длинное описание не урезается и в запрос не подставляется.
        long_text = snapshot(description="требования " * 3000)
        assert client.post(PATH, headers=HR, json={"vacancy": long_text}).status_code == 200


def test_qualification_comes_only_from_the_exact_profile(session, monkeypatch, posting_registry):  # noqa: F811
    profile = training_profile(session)
    data = case(session, profile, "py-9301")  # текст: «Написал API-тесты…», оценка по этому профилю
    other = case(session, profile, "py-9302", statement="Общий коммерческий опыт — 3 года.")
    ref = {"system": "legacy-hr", "id": str(profile.id), "version": profile.version}
    vacancy = snapshot(position_code="python-dev", search_query="API-тесты", profile_ref=ref)
    with client_for(session, monkeypatch) as client:
        items = client.post(PATH, headers=HR, json={"vacancy": vacancy}).json()["items"]
        by_code = {i["candidate_code"]: i for i in items}
        assert by_code["py-9301"]["qualification_status"] == "unknown"
        assert by_code["py-9301"]["assessment_id"] == str(data["assessment_id"])
        assert by_code["py-9302"]["qualification_status"] == "met"
        assert by_code["py-9302"]["assessment_id"] == str(other["assessment_id"])
        assert by_code["py-9301"]["applications"]  # прежний отклик виден отдельно от оценки

        for changed, reason in (
            ({"version": profile.version + 1}, "profile_mismatch"),
            ({"id": str(uuid.uuid4())}, "profile_not_found"),
            ({"system": "catalog"}, "unmapped_profile"),
        ):
            items = client.post(PATH, headers=HR, json={"vacancy": vacancy | {"profile_ref": ref | changed}}).json()["items"]
            assert {(i["qualification_status"], i["qualification_reason"], i["assessment_id"]) for i in items} == {
                ("not_evaluated", reason, None)}
        wrong_position = vacancy | {"position_code": "hr-consultant"}
        items = client.post(PATH, headers=HR, json={"vacancy": wrong_position}).json()["items"]
        assert {i["qualification_reason"] for i in items} == {"profile_mismatch"}
