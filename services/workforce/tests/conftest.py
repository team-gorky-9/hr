import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

FIXTURES = Path(os.getenv("FIXTURE_DIR", str(Path(__file__).resolve().parents[3] / "fixtures" / "wave-1")))
ORG = "00000000-0000-4000-8000-000000000001"
DEPT = "00000000-0000-4000-8000-000000000011"


@pytest.fixture
def app(tmp_path):
    assert importlib.util.find_spec("workforce.api"), "Workforce HTTP application is not implemented"
    from workforce.api import create_app
    from workforce.config import Settings
    from workforce.database import migrate, seed

    database_url = os.getenv("WORKFORCE_TEST_DATABASE_URL")
    admin_engine = None
    if database_url:
        url = make_url(database_url)
        if url.get_backend_name() != "postgresql" or not url.database.endswith("_test"):
            pytest.fail("WORKFORCE_TEST_DATABASE_URL must point to a dedicated PostgreSQL *_test database")
        schema = "wf_" + uuid4().hex
        admin_engine = create_engine(url)
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        database_url = url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
            hide_password=False
        )
    else:
        database_url = f"sqlite:///{tmp_path / 'test.db'}"
    settings = Settings(database_url=database_url, fixture_dir=FIXTURES)
    instance = create_app(settings)
    migrate(instance.state.engine)
    seed(instance.state.engine, settings)
    yield instance
    instance.state.engine.dispose()
    if admin_engine:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as http:
        yield http
    app.state.engine.dispose()


def auth(client, login="hr"):
    response = client.post(
        "/api/v1/sessions",
        json={"login": login, "password": "123"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def command(client, path, body, headers=None, key=None, method="post"):
    return getattr(client, method)(
        "/api/v1" + path,
        json=body,
        headers={**(headers or auth(client)), "Idempotency-Key": key or str(uuid4())},
    )


def employee(client, headers=None, name="Марина Учебная", source=None, **extra):
    response = command(
        client,
        "/employees",
        {
            "display_name": name,
            "source_refs": [{"system": "test", "id": source or str(uuid4())}],
            "confirmation_basis": "Учебное подтверждение",
            **extra,
        },
        headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def assignment(client, person, headers=None, **extra):
    response = command(
        client,
        f"/employees/{person['id']}/assignments",
        {
            "department_id": DEPT,
            "position_code": "economist-training",
            "starts_on": "2026-11-23",
            "basis": {"reference": "DEMO-21", "issued_on": "2026-11-21"},
            **extra,
        },
        headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
