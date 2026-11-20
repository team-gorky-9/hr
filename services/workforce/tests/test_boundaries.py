from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import DEPT, assignment, auth, command, employee
from workforce.api import create_app
from workforce.database import seed
from workforce.models import Actor, Assignment, Audit, Department, Employee, LoginSession, now


def test_seed_does_not_reset_edited_data_or_revoked_sessions(app, client):
    headers = auth(client, "admin")
    response = command(
        client, f"/departments/{DEPT}", {"expected_revision": 1, "name": "Changed"}, headers, method="patch"
    )
    assert response.status_code == 200
    client.delete("/api/v1/session", headers=headers)
    seed(app.state.engine, app.state.settings)
    assert client.get("/api/v1/session", headers=headers).status_code == 401
    with Session(app.state.engine) as session:
        assert session.get(Department, DEPT).name == "Changed"
        assert session.scalar(select(func.count()).select_from(Actor)) == 6


def test_expired_and_deactivated_sessions_are_denied(app, client):
    headers = auth(client)
    with Session(app.state.engine) as session, session.begin():
        row = session.scalar(select(LoginSession))
        row.expires_at = now() - timedelta(seconds=1)
    assert client.get("/api/v1/session", headers=headers).status_code == 401
    headers = auth(client)
    with Session(app.state.engine) as session, session.begin():
        actor = session.scalar(select(Actor).where(Actor.login == "hr"))
        actor.active = False
    assert client.get("/api/v1/session", headers=headers).status_code == 401


def test_fixture_mode_is_server_controlled(app):
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/session", headers={"Authorization": "Bearer fixture:hr"}).status_code == 401
        )
    fixture_app = create_app(replace(app.state.settings, auth_mode="fixture"))
    with TestClient(fixture_app) as client:
        assert client.get("/health").json()["auth_mode"] == "fixture"
        assert (
            client.get("/api/v1/session", headers={"Authorization": "Bearer fixture:hr"}).status_code == 200
        )
        assert (
            client.get("/api/v1/employees", headers={"Authorization": "Bearer fixture:candidate"}).status_code
            == 403
        )
    fixture_app.state.engine.dispose()


def test_parallel_same_key_creates_only_one_employee(app, client):
    headers = auth(client)
    key = str(uuid4())
    body = {
        "display_name": "Concurrent",
        "source_refs": [{"system": "test", "id": "parallel"}],
        "confirmation_basis": "test",
    }

    def send(_):
        with TestClient(app) as http:
            return command(http, "/employees", body, headers, key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, range(2)))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Employee)) == 1


def test_parallel_distinct_commands_one_revision_changes_once(app, client):
    headers = auth(client)
    person = employee(client, headers)

    def send(index):
        with TestClient(app) as http:
            return command(
                http,
                f"/employees/{person['id']}",
                {
                    "expected_revision": 1,
                    "display_name": f"Change {index}",
                    "correction_basis": "test",
                },
                headers,
                method="patch",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    with Session(app.state.engine) as session:
        assert session.get(Employee, person["id"]).revision == 2
        assert (
            session.scalar(select(func.count()).select_from(Audit).where(Audit.action == "employee.correct"))
            == 1
        )


def test_foreign_links_rejected_atomically(client):
    headers = auth(client)
    foreign = employee(client, auth(client, "hr_other"))
    person = employee(client, headers)
    result = command(
        client,
        f"/employees/{person['id']}/assignments",
        {
            "department_id": DEPT,
            "position_code": "test",
            "starts_on": "2026-11-23",
            "manager_employee_id": foreign["id"],
            "basis": {"reference": "test", "issued_on": "2026-11-21"},
        },
        headers,
    )
    assert result.status_code == 404
    assert client.get(f"/api/v1/employees/{person['id']}", headers=headers).json()["assignments"] == []
    result = command(
        client,
        f"/employees/{person['id']}",
        {
            "expected_revision": 1,
            "account_actor_id": "00000000-0000-4000-8000-000000000106",
            "correction_basis": "test",
        },
        headers,
        method="patch",
    )
    assert result.status_code == 404


def test_period_end_and_invalid_dates(client):
    person = employee(client)
    item = assignment(client, person)
    bad = command(
        client,
        f"/assignments/{item['id']}/end",
        {"expected_revision": 1, "ends_on": "2026-11-22", "reason": "test"},
    )
    assert bad.status_code == 422
    good = command(
        client,
        f"/assignments/{item['id']}/end",
        {"expected_revision": 1, "ends_on": "2027-01-01", "reason": "planned end"},
    )
    assert good.status_code == 200
    assert good.json()["ends_on"] == "2027-01-01"


def test_duplicate_assignment_rejected_with_another_command_key(app, client):
    person = employee(client)
    item = assignment(client, person)
    response = command(
        client,
        f"/employees/{person['id']}/assignments",
        {key: item[key] for key in ("department_id", "position_code", "starts_on", "basis")},
    )
    assert response.status_code == 409
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Assignment)) == 1


def test_common_schema_rejects_empty_null_extra_fields(client):
    person = employee(client)
    for body in [
        {"expected_revision": 1, "display_name": None, "correction_basis": "test"},
        {"expected_revision": True, "display_name": "X", "correction_basis": "test"},
        {"expected_revision": 1, "display_name": "X", "correction_basis": " "},
    ]:
        assert command(client, f"/employees/{person['id']}", body, method="patch").status_code == 422


def test_organization_grant_does_not_accept_department_scoped_hr(app, client):
    headers = auth(client)
    with Session(app.state.engine) as session, session.begin():
        actor = session.scalar(select(Actor).where(Actor.login == "hr"))
        actor.grants = [{"role": "hr", "scope_type": "department", "scope_id": DEPT}]
    assert client.get("/api/v1/employees", headers=headers).status_code == 403


def test_health_and_readiness_without_migration(tmp_path):
    from workforce.config import Settings

    unprepared = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'empty.db'}"))
    with TestClient(unprepared) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
    unprepared.state.engine.dispose()


def test_ready_reports_missing_migration_as_503_on_current_database(app, client):
    from sqlalchemy import text

    with app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    assert client.get("/ready").status_code == 503


def test_numeric_dates_rejected_in_http_contract(client):
    person = employee(client)
    item = assignment(client, person)
    for invalid in [0, "20261201", "1796083200"]:
        response = command(
            client,
            f"/assignments/{item['id']}/end",
            {"expected_revision": 1, "ends_on": invalid, "reason": "test"},
        )
        assert response.status_code == 422


def test_existing_employee_source_confirmation_has_history(app, client):
    from tests.test_broker_integration import example
    from tests.test_events import intake, receive, register

    headers = auth(client)
    person = employee(client, headers)
    receive(app, example())
    result = register(client, intake(client, headers), headers, person=person["id"])
    assert result.status_code == 200
    assert result.json()["employee"]["revision"] == 2
    history = client.get(f"/api/v1/employees/{person['id']}/history", headers=headers).json()["items"]
    confirmation = next(item for item in history if item["action"] == "employee.source_confirm")
    assert confirmation["before"]["revision"] == 1
    assert confirmation["after"]["revision"] == 2
    assert confirmation["basis"]["identity_basis"] == "Verified demo identity"
