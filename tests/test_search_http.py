from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from app.api.schemas import Contour
from app.db.session import get_session
from app.main import create_app
from app.search import api
from app.search.schemas import SearchResponse


PATH = "/api/v1/search/candidates"


def test_openapi_and_working_route_gate_before_repository(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: SimpleNamespace(get_bind=lambda: None)
    monkeypatch.setattr(api.settings, "hr_search_work_token", SecretStr("search-test-token"))
    calls = []

    def search(_session, request, **_):
        calls.append(request.contour)
        return SearchResponse(contour=request.contour, mode="hybrid", semantic_status="ready", items=[])

    monkeypatch.setattr(api, "search_candidates", search)
    with TestClient(app) as client:
        doc = client.get("/openapi.json").json()
        route = doc["paths"][PATH]["post"]
        assert route["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/SearchRequest")
        assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/SearchResponse")
        assert route["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("/SearchErrorResponse")
        assert set(route["responses"]) == {"200", "401", "422", "500", "503"}
        assert {"SearchWorkBearer": []} in route["security"]
        assert {} in route["security"]

        for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}):
            payload = client.post(PATH, json={"query": "FastAPI"}, headers=headers)
            assert payload.status_code == 401
            assert payload.json() == {"error": {"code": "SEARCH_AUTH_REQUIRED",
                                                 "message": "Требуется доступ к рабочему поиску", "details": {}}}
        assert calls == []
        training = client.post(PATH, json={"contour": "training", "query": "FastAPI"})
        assert training.json() == {"contour": "training", "mode": "hybrid", "semantic_status": "ready", "items": []}
        assert training.headers["Cache-Control"] == "private, no-store"
        working = client.post(PATH, json={"query": "FastAPI"},
                              headers={"Authorization": "Bearer search-test-token"})
        assert working.status_code == 200
        monkeypatch.setattr(api.settings, "hr_search_work_token", SecretStr(""))
        assert client.post(PATH, json={"query": "FastAPI"},
                           headers={"Authorization": "Bearer search-test-token"}).status_code == 401
    assert calls == [Contour.TRAINING, Contour.WORKING]


def test_validation_and_database_failure_use_common_error_without_input(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: SimpleNamespace(get_bind=lambda: None)

    def fail(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, ValueError("db credentials"))

    monkeypatch.setattr(api, "search_candidates", fail)
    with TestClient(app) as client:
        bad_requests = [
            {}, {"query": "   ", "filters": {"skill_match": "all"}}, {"query": "???"},
            {"query": 123}, {"query": "a" * 513}, {"query": "a", "limit": "1"},
            {"query": "a", "limit": True}, {"filters": {"in_reserve": 1}},
            {"filters": {"required_terms": ["   "]}}, {"filters": {"required_terms": ["__"]}},
            {"filters": {"skills": [" "]}}, {"filters": {"unknown": True}},
        ]
        for request in bad_requests:
            invalid = client.post(PATH, json=request)
            assert invalid.status_code == 422
            assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
            assert all("input" not in detail for detail in invalid.json()["error"]["details"]["errors"])
        failed = client.post(PATH, json={"query": "FastAPI", "contour": "training"})
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "SEARCH_UNAVAILABLE"
        assert "db credentials" not in failed.text
