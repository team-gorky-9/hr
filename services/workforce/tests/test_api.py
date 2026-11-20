from uuid import uuid4

from tests.conftest import DEPT, assignment, auth, command, employee


def test_login_bad_password_and_revocation(client):
    bad = client.post("/api/v1/sessions", json={"login": "hr", "password": "bad"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_CREDENTIALS"
    headers = auth(client)
    current = client.get("/api/v1/session", headers=headers)
    assert current.json()["actor_id"] == "00000000-0000-4000-8000-000000000101"
    assert "password" not in current.json()
    assert client.delete("/api/v1/session", headers=headers).status_code == 204
    assert client.get("/api/v1/session", headers=headers).status_code == 401


def test_homonyms_are_separate_and_sources_unique(client):
    headers = auth(client)
    first = employee(client, headers, source="one")
    second = employee(client, headers, source="two")
    assert first["id"] != second["id"]
    result = client.get("/api/v1/employees?query=Марина", headers=headers).json()
    assert {p["id"] for p in result["items"]} == {first["id"], second["id"]}
    duplicate = command(
        client,
        "/employees",
        {
            "display_name": "Other",
            "source_refs": [{"system": "test", "id": "one"}],
            "confirmation_basis": "verified",
        },
        headers,
    )
    assert duplicate.status_code == 409


def test_foreign_organization_and_roles(client):
    person = employee(client)
    other = auth(client, "hr_other")
    denied = client.get(f"/api/v1/employees/{person['id']}", headers=other)
    assert denied.status_code == 404
    assert person["display_name"] not in denied.text
    assert client.get("/api/v1/employees", headers=auth(client, "department")).status_code == 403
    assert command(client, "/departments", {"code": "x", "name": "X"}).status_code == 403


def test_self_requires_explicit_link_and_has_no_hr_sources(client):
    own = employee(client, account_actor_id="00000000-0000-4000-8000-000000000104")
    other = employee(client)
    headers = auth(client, "employee")
    result = client.get(f"/api/v1/employees/{own['id']}", headers=headers)
    assert result.status_code == 200
    assert "source_refs" not in result.json()
    assert client.get(f"/api/v1/employees/{other['id']}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/employees/{own['id']}/history", headers=headers).status_code == 403


def test_idempotency_replays_before_revision_and_rechecks_access(client):
    headers = auth(client)
    person = employee(client, headers)
    key = str(uuid4())
    body = {"expected_revision": 1, "display_name": "Corrected", "correction_basis": "typo"}
    first = command(client, f"/employees/{person['id']}", body, headers, key, "patch")
    replay = command(client, f"/employees/{person['id']}", body, headers, key, "patch")
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    stale = command(client, f"/employees/{person['id']}", body, headers, method="patch")
    assert stale.json()["error"]["code"] == "STALE_REVISION"
    conflict = command(
        client, f"/employees/{person['id']}", {**body, "display_name": "changed"}, headers, key, "patch"
    )
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    client.delete("/api/v1/session", headers=headers)
    assert command(client, f"/employees/{person['id']}", body, headers, key, "patch").status_code == 401


def test_transfer_correction_and_history(client):
    headers = auth(client)
    person = employee(client, headers)
    original = assignment(client, person, headers)
    transfer = command(
        client,
        f"/assignments/{original['id']}/transfer",
        {
            "expected_revision": 1,
            "ends_on": "2026-12-01",
            "new_department_id": DEPT,
            "new_position_code": "senior",
            "starts_on": "2026-12-02",
            "basis": {"reference": "TRANSFER-1", "issued_on": "2026-12-01"},
        },
        headers,
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["ended"]["ends_on"] == "2026-12-01"
    new = transfer.json()["new"]
    assert new["id"] != original["id"]
    correction = command(
        client,
        f"/assignments/{new['id']}/correct",
        {
            "expected_revision": 1,
            "starts_on": "2026-12-03",
            "reason": "wrong date",
            "basis": {"reference": "CORRECTION-1", "issued_on": "2026-12-02"},
        },
        headers,
    )
    assert correction.status_code == 200
    history = client.get(f"/api/v1/employees/{person['id']}/history", headers=headers).json()["items"]
    corrected = next(item for item in history if item["action"] == "assignment.correct")
    assert corrected["before"]["basis"]["reference"] == "TRANSFER-1"
    assert corrected["after"]["basis"]["reference"] == "CORRECTION-1"
    assert corrected["recorded_at"] and corrected["effective_on"] and corrected["actor_id"]


def test_invalid_transfer_rolls_back_old_assignment(client):
    person = employee(client)
    original = assignment(client, person)
    result = command(
        client,
        f"/assignments/{original['id']}/transfer",
        {
            "expected_revision": 1,
            "ends_on": "2026-12-01",
            "new_department_id": str(uuid4()),
            "new_position_code": "senior",
            "starts_on": "2026-12-02",
            "basis": {"reference": "TRANSFER-1", "issued_on": "2026-12-01"},
        },
    )
    assert result.status_code == 404
    result = client.get(f"/api/v1/employees/{person['id']}", headers=auth(client)).json()
    assert result["assignments"][0]["ends_on"] is None
    assert result["assignments"][0]["revision"] == 1


def test_department_cycle_and_history_preservation(client):
    admin = auth(client, "admin")
    child = command(
        client, "/departments", {"code": "child", "name": "Child", "parent_id": DEPT}, admin
    ).json()
    cycle = command(
        client,
        f"/departments/{DEPT}",
        {"expected_revision": 1, "parent_id": child["id"]},
        admin,
        method="patch",
    )
    assert cycle.status_code == 422
    renamed = command(
        client, f"/departments/{DEPT}", {"expected_revision": 1, "name": "New name"}, admin, method="patch"
    )
    assert renamed.status_code == 200
    assert renamed.json()["revision"] == 2


def test_delegation_date_filter_and_end(client):
    headers = auth(client)
    manager, substitute = employee(client, headers), employee(client, headers)
    response = command(
        client,
        "/delegations",
        {
            "manager_employee_id": manager["id"],
            "substitute_employee_id": substitute["id"],
            "department_id": DEPT,
            "starts_on": "2026-12-01",
            "ends_on": "2026-12-10",
            "basis": {"reference": "VACATION", "issued_on": "2026-11-21"},
        },
        headers,
    )
    assert response.status_code == 201, response.text
    query = f"/api/v1/delegations?department_id={DEPT}&as_of="
    assert len(client.get(query + "2026-12-05", headers=headers).json()["items"]) == 1
    assert client.get(query + "2026-12-11", headers=headers).json()["items"] == []
    ended = command(
        client,
        f"/delegations/{response.json()['id']}/end",
        {"expected_revision": 1, "ends_on": "2026-12-04", "reason": "returned early"},
        headers,
    )
    assert ended.status_code == 200
    assert client.get(query + "2026-12-05", headers=headers).json()["items"] == []


def test_pagination_no_duplicates_and_invalid_cursor(client):
    headers = auth(client)
    ids = {employee(client, headers)["id"] for _ in range(3)}
    seen = set()
    path = "/api/v1/employees?limit=1"
    while path:
        page = client.get(path, headers=headers).json()
        assert not seen.intersection(p["id"] for p in page["items"])
        seen.update(p["id"] for p in page["items"])
        path = f"/api/v1/employees?limit=1&cursor={page['next_cursor']}" if page["next_cursor"] else None
    assert seen == ids
    assert client.get("/api/v1/employees?cursor=invalid", headers=headers).status_code == 422


def test_validation_errors_do_not_echo_secrets_and_require_keys(client):
    headers = auth(client)
    body = {"display_name": " ", "source_refs": [], "confirmation_basis": " "}
    assert command(client, "/employees", body, headers).status_code == 422
    body = {"display_name": "Test", "source_refs": [], "confirmation_basis": "proof", "unexpected": "secret"}
    response = command(client, "/employees", body, headers)
    assert response.status_code == 422
    assert "secret" not in response.text
    assert (
        client.post(
            "/api/v1/employees", json={k: v for k, v in body.items() if k != "unexpected"}, headers=headers
        ).status_code
        == 422
    )


def test_sessions_and_data_survive_application_restart(client, app):
    from fastapi.testclient import TestClient

    from workforce.api import create_app

    headers = auth(client)
    person = employee(client, headers)
    restarted = create_app(app.state.settings)
    with TestClient(restarted) as http:
        assert http.get("/api/v1/session", headers=headers).status_code == 200
        assert http.get(f"/api/v1/employees/{person['id']}", headers=headers).json()["id"] == person["id"]
    restarted.state.engine.dispose()
