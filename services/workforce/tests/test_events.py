import copy
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import FIXTURES, auth, command, employee


@pytest.fixture
def event():
    return json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))["events"][0]


def receive(app, event):
    from workforce.events import receive_event

    return receive_event(app.state.engine, event)


def intake(client, headers):
    return client.get("/api/v1/intakes", headers=headers).json()["items"][0]


def register(client, item, headers, key=None, person=None):
    return command(
        client,
        f"/intakes/{item['id']}/register",
        {
            "expected_revision": item["revision"],
            "employee_id": person,
            "create_employee": None if person else {"display_name": "Марина Учебная"},
            "identity_basis": "Verified demo identity",
        },
        headers,
        key,
    )


def test_event_and_command_duplicates_preserve_ids_and_correlation(app, client, event):
    from workforce.models import Outbox

    assert receive(app, event) == "received"
    assert receive(app, event) == "duplicate"
    headers = auth(client)
    item = intake(client, headers)
    key = str(uuid4())
    first = register(client, item, headers, key)
    again = register(client, item, headers, key)
    assert first.status_code == again.status_code == 200, first.text
    assert first.json() == again.json()
    with Session(app.state.engine) as session:
        rows = list(session.scalars(select(Outbox)))
        assert len(rows) == 1
        published = rows[0].envelope
        assert published["correlation_id"] == event["correlation_id"]
        assert published["payload"]["source_event_id"] == event["event_id"]
        assert published["payload"]["source_case_revision"] == 4
        assert published["payload"]["employee_id"] == first.json()["employee"]["id"]
    assert receive(app, event) == "duplicate"
    assert len(client.get("/api/v1/employees", headers=headers).json()["items"]) == 1


def test_explicit_existing_homonym_selected(app, client, event):
    headers = auth(client)
    first, second = employee(client, headers), employee(client, headers)
    receive(app, event)
    response = register(client, intake(client, headers), headers, person=second["id"])
    assert response.status_code == 200, response.text
    assert response.json()["employee"]["id"] == second["id"]
    untouched = client.get(f"/api/v1/employees/{first['id']}", headers=headers).json()
    assert untouched["assignments"] == []


@pytest.mark.parametrize("mutation", ["organization", "producer", "version", "case", "actor"])
def test_invalid_event_cannot_create_intake(app, client, event, mutation):
    from workforce.events import InvalidEvent

    if mutation == "organization":
        event["organization_id"] = "00000000-0000-4000-8000-000000000002"
    elif mutation == "producer":
        event["producer"] = "requirements"
    elif mutation == "version":
        event["schema_version"] = "2.0"
    elif mutation == "case":
        event["payload"]["case_id"] = str(uuid4())
    else:
        event["payload"]["confirmed_by_actor_id"] = "00000000-0000-4000-8000-000000000106"
    with pytest.raises(InvalidEvent):
        receive(app, event)
    assert client.get("/api/v1/intakes", headers=auth(client)).json()["items"] == []


def test_stale_and_equal_conflicting_versions_do_not_overwrite(app, client, event):
    receive(app, event)
    headers = auth(client)
    stale = copy.deepcopy(event)
    stale.update(event_id=str(uuid4()), aggregate_revision=3)
    stale["payload"]["position_code"] = "stale"
    assert receive(app, stale) == "stale"
    assert intake(client, headers)["proposed_assignment"]["position_code"] == "economist-training"
    conflict = copy.deepcopy(event)
    conflict["event_id"] = str(uuid4())
    conflict["payload"]["position_code"] = "conflict"
    assert receive(app, conflict) == "needs_review"
    current = intake(client, headers)
    assert current["status"] == "needs_review"
    assert current["proposed_assignment"]["position_code"] == "economist-training"


def test_new_version_after_registration_retains_assignment(app, client, event):
    from workforce.models import Assignment

    receive(app, event)
    headers = auth(client)
    first = register(client, intake(client, headers), headers).json()
    event.update(event_id=str(uuid4()), aggregate_revision=5)
    event["payload"]["starts_on"] = "2026-12-01"
    assert receive(app, event) == "needs_review"
    current = intake(client, headers)
    assert current["assignment_id"] == first["assignment"]["id"]
    assert current["status"] == "needs_review"
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Assignment)) == 1


def test_rejected_intake_does_not_register(app, client, event):
    receive(app, event)
    headers = auth(client)
    item = intake(client, headers)
    response = command(
        client, f"/intakes/{item['id']}/reject", {"expected_revision": 1, "reason": "wrong person"}, headers
    )
    assert response.status_code == 200
    assert register(client, response.json(), headers).status_code == 409


def test_broker_failure_preserves_fact_and_pending_delivery(app, client, event):
    from workforce.worker import publish_pending

    receive(app, event)
    headers = auth(client)
    result = register(client, intake(client, headers), headers)
    assert result.status_code == 200
    # Real connection to a closed local port; no fake in-memory publisher.
    from dataclasses import replace

    settings = replace(app.state.settings, rabbitmq_url="amqp://guest:guest@127.0.0.1:1/%2F")
    publish_pending(app.state.engine, settings)
    row = client.get("/api/v1/deliveries?status=pending", headers=headers).json()["items"][0]
    assert row["attempts"] == 1
    assert row["last_error"]
    assert "guest" not in row["last_error"]
    assert (
        client.get(f"/api/v1/employees/{result.json()['employee']['id']}", headers=headers).status_code == 200
    )


def test_registration_preserves_source_document_without_extending_assignment_dto(app, client, event):
    receive(app, event)
    headers = auth(client)
    result = register(client, intake(client, headers), headers)
    assert result.status_code == 200
    assert result.json()["assignment"]["basis"] == {"reference": "DEMO-21", "issued_on": "2026-11-21"}
    assert (
        result.json()["intake"]["proposed_assignment"]["basis"]["document_ref"]
        == event["payload"]["basis"]["document_ref"]
    )


def test_delivery_retry_checks_revision_and_foreign_scope(app, client, event):
    from workforce.models import Outbox

    receive(app, event)
    headers = auth(client)
    register(client, intake(client, headers), headers)
    with Session(app.state.engine) as session, session.begin():
        delivery = session.scalar(select(Outbox))
        delivery.status, delivery.attempts = "failed", 5
        event_id = delivery.event_id
    response = command(client, f"/deliveries/{event_id}/retry", {"expected_revision": 1}, headers)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["attempts"] == 0
    assert (
        command(client, f"/deliveries/{event_id}/retry", {"expected_revision": 1}, headers).status_code == 409
    )
    assert (
        command(
            client, f"/deliveries/{event_id}/retry", {"expected_revision": 2}, auth(client, "hr_other")
        ).status_code
        == 404
    )
