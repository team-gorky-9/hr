"""Tests run against a real PostgreSQL (HIRING_TEST_DATABASE_URL); the schema is created by the
service's own Alembic migrations, so the migrations are tested on every run. No broker is needed."""
import json
import os
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from hiring.api import create_app
from hiring.config import Settings
from hiring.database import make_engine, migrate

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/wave-1"
EXTRA = Path(__file__).resolve().parents[1] / "fixtures/extra-selections.json"
DEFAULT_URL = "postgresql+psycopg://hiring:hiring@localhost:5413/hiring_test"
CANDIDATE = "00000000-0000-4000-8000-000000000105"
CHECKLIST = [
    {"key": "passport", "title": "Копия паспорта", "required": True},
    {"key": "education", "title": "Документ об образовании", "required": True},
    {"key": "photo", "title": "Фотография", "required": False},
]


def pdf(label: str = "doc") -> bytes:
    return b"%PDF-1.4\n% synthetic " + label.encode() + b"\n%%EOF\n"


@pytest.fixture(scope="session")
def database_url():
    url = os.getenv("HIRING_TEST_DATABASE_URL", DEFAULT_URL)
    engine = make_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    migrate(engine)
    engine.dispose()
    return url


@pytest.fixture
def settings(database_url, tmp_path):
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE case_events, checklist_items, documents, cases, idempotent_commands, "
            "candidate_request_events, candidate_requests"))
    engine.dispose()
    return Settings(database_url=database_url, auth_mode="fixture", source_mode="fixture",
                    fixture_dir=FIXTURES, extra_selections_file=EXTRA, file_root=tmp_path / "files",
                    file_max_bytes=1024)


class Api:
    """Thin client: as(login).post(...) with a fresh Idempotency-Key unless one is given."""

    def __init__(self, client: TestClient):
        self.client = client

    def headers(self, login, key=None, **extra):
        headers = {"Authorization": f"Bearer fixture:{login}"} if login else {}
        if key is not None:
            headers["Idempotency-Key"] = key
        headers.update(extra)
        return headers

    def get(self, login, path, **kwargs):
        return self.client.get(f"/api/v1{path}", headers=self.headers(login), **kwargs)

    def post(self, login, path, body, key=None):
        return self.client.post(f"/api/v1{path}", headers=self.headers(login, key or str(uuid.uuid4())), json=body)

    def post_without_key(self, login, path, body):
        return self.client.post(f"/api/v1{path}", headers=self.headers(login), json=body)

    def upload(self, login, kind="hiring_application", content=None, name="scan.pdf", key=None):
        return self.client.post("/api/v1/documents", headers=self.headers(login, key or str(uuid.uuid4())),
                                data={"kind": kind}, files={"file": (name, pdf(name) if content is None else content, "application/pdf")})


@pytest.fixture
def app(settings):
    application = create_app(settings)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def api(app):
    with TestClient(app) as client:
        yield Api(client)


@pytest.fixture
def marina():
    return json.loads((FIXTURES / "selection.json").read_text(encoding="utf-8"))


@pytest.fixture
def petr():
    return json.loads(EXTRA.read_text(encoding="utf-8"))["selections"][0]


def create_case(api, selection, linked=True, checklist=None):
    body = {"selection": selection, "checklist": checklist or CHECKLIST, "checklist_version": "training-1"}
    if linked:
        body |= {"candidate_actor_id": CANDIDATE, "identity_basis": "Учебная проверка личности"}
    response = api.post("hr", "/cases", body)
    assert response.status_code == 201, response.text
    return response.json()


def item(case, key):
    return next(entry for entry in case["checklist"] if entry["key"] == key)


def submit(api, case, key, login="candidate", kind="hiring_application", content=None):
    document = api.upload(login, kind, content=content or pdf(f"{key}-{uuid.uuid4()}"))
    assert document.status_code == 201, document.text
    entry = item(api.get("hr", f"/cases/{case['id']}").json(), key)
    response = api.post(login, f"/cases/{case['id']}/items/{entry['id']}/submit",
                        {"expected_revision": entry["revision"], "document_id": document.json()["id"]})
    assert response.status_code == 200, response.text
    return response.json()


def review(api, case, key, result="accepted", reason=None):
    entry = item(api.get("hr", f"/cases/{case['id']}").json(), key)
    response = api.post("hr", f"/cases/{case['id']}/items/{entry['id']}/review",
                        {"expected_revision": entry["revision"], "result": result, "reason": reason})
    assert response.status_code == 200, response.text
    return response.json()


def current(api, case):
    return api.get("hr", f"/cases/{case['id']}").json()


def ready_case(api, selection):
    case = create_case(api, selection)
    for key in ("passport", "education"):
        submit(api, case, key)
        review(api, case, key)
    response = api.post("hr", f"/cases/{case['id']}/ready", {"expected_revision": current(api, case)["revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def basis_document(api, login="hr"):
    response = api.upload(login, "employment_basis", name="order.pdf")
    assert response.status_code == 201, response.text
    return response.json()


def started_case(api, selection, starts_on="2026-11-23"):
    case = ready_case(api, selection)
    order = basis_document(api)
    response = api.post("hr", f"/cases/{case['id']}/start", {
        "expected_revision": case["revision"], "starts_on": starts_on,
        "basis": {"document_id": order["id"], "reference": "DEMO-21", "issued_on": "2026-11-21"},
        "confirmation_basis": "Оригиналы сверены"})
    assert response.status_code == 200, response.text
    return response.json()


def with_settings(settings, **changes):
    return replace(settings, **changes)
