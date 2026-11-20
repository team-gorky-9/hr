import copy
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import auth, command
from tests.test_broker_integration import example
from tests.test_events import intake, receive, register
from workforce.models import Assignment, Outbox


def corrected(app, client):
    headers = auth(client)
    event = example()
    receive(app, event)
    first = register(client, intake(client, headers), headers).json()
    correction = copy.deepcopy(event)
    correction.update(event_id=str(uuid4()), correlation_id=str(uuid4()), aggregate_revision=5)
    correction["payload"]["starts_on"] = "2026-11-24"
    correction["payload"]["basis"]["reference"] = "CORRECTED-21"
    receive(app, correction)
    return headers, first, correction, intake(client, headers)


@pytest.mark.parametrize("decision", ["apply", "keep"])
def test_review_completes_same_assignment_and_publishes_result(app, client, decision):
    headers, first, correction, pending = corrected(app, client)
    key = str(uuid4())
    body = {"expected_revision": pending["revision"], "expected_assignment_revision": 1, "decision": decision}
    if decision == "keep":
        body["reason"] = "Original employment order remains valid"
    path = f"/intakes/{pending['id']}/review"
    result = command(client, path, body, headers, key)
    assert result.status_code == 200, result.text
    reviewed = result.json()
    assert reviewed["intake"]["status"] == "registered"
    assert reviewed["assignment"]["id"] == first["assignment"]["id"]
    assert reviewed["assignment"]["starts_on"] == ("2026-11-24" if decision == "apply" else "2026-11-23")
    assert reviewed["assignment"]["revision"] == (2 if decision == "apply" else 1)
    assert command(client, path, body, headers, key).json() == reviewed
    assert command(client, path, body, headers).status_code == 409
    assert intake(client, headers)["last_review"]["decision"] == decision
    history = client.get(f"/api/v1/employees/{first['employee']['id']}/history", headers=headers).json()[
        "items"
    ]
    audit = next(row for row in history if row["action"] == "assignment.review")
    assert audit["before"]["basis"]["reference"] == "DEMO-21"
    assert audit["after"]["basis"]["reference"] == ("CORRECTED-21" if decision == "apply" else "DEMO-21")
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Assignment)) == 1
        result_events = list(
            session.scalars(select(Outbox).where(Outbox.event_type == "assignment.reviewed"))
        )
        assert len(result_events) == 1
        message = result_events[0].envelope
        assert message["correlation_id"] == correction["correlation_id"]
        assert message["payload"]["source_event_id"] == correction["event_id"]
        assert message["payload"]["source_case_revision"] == 5
        assert message["payload"]["decision"] == decision
        assert message["payload"]["assignment_id"] == first["assignment"]["id"]
        assert message["payload"]["starts_on"] == reviewed["assignment"]["starts_on"]
        assert message["payload"]["basis"] == reviewed["assignment"]["basis"]


def test_keep_requires_explanation_and_access(app, client):
    headers, _, _, pending = corrected(app, client)
    body = {"expected_revision": pending["revision"], "expected_assignment_revision": 1, "decision": "keep"}
    path = f"/intakes/{pending['id']}/review"
    assert command(client, path, body, headers).status_code == 422
    assert command(client, path, {**body, "reason": " "}, headers).status_code == 422
    assert command(client, path, {**body, "reason": "test"}, auth(client, "hr_other")).status_code == 404
    assert command(client, path, {**body, "reason": "test"}, auth(client, "department")).status_code == 403
    assert intake(client, headers)["status"] == "needs_review"


def test_review_checks_assignment_revision_and_rolls_back(app, client):
    headers, first, _, pending = corrected(app, client)
    response = command(
        client,
        f"/assignments/{first['assignment']['id']}/correct",
        {
            "expected_revision": 1,
            "starts_on": "2026-11-25",
            "reason": "Local correction",
            "basis": {"reference": "LOCAL", "issued_on": "2026-11-21"},
        },
        headers,
    )
    assert response.status_code == 200
    result = command(
        client,
        f"/intakes/{pending['id']}/review",
        {
            "expected_revision": pending["revision"],
            "expected_assignment_revision": 1,
            "decision": "apply",
        },
        headers,
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "STALE_REVISION"
    assert intake(client, headers)["status"] == "needs_review"
    with Session(app.state.engine) as session:
        assert session.get(Assignment, first["assignment"]["id"]).basis["reference"] == "LOCAL"
        assert (
            session.scalar(
                select(func.count()).select_from(Outbox).where(Outbox.event_type == "assignment.reviewed")
            )
            == 0
        )


def test_review_rejects_superseded_intake_revision(app, client):
    headers, _, correction, pending = corrected(app, client)
    correction.update(event_id=str(uuid4()), aggregate_revision=6)
    correction["payload"]["starts_on"] = "2026-11-26"
    receive(app, correction)
    result = command(
        client,
        f"/intakes/{pending['id']}/review",
        {
            "expected_revision": pending["revision"],
            "expected_assignment_revision": 1,
            "decision": "apply",
        },
        headers,
    )
    assert result.status_code == 409


def test_parallel_review_creates_one_outcome(app, client):
    headers, _, _, pending = corrected(app, client)

    def send(_):
        with TestClient(app) as http:
            return command(
                http,
                f"/intakes/{pending['id']}/review",
                {
                    "expected_revision": pending["revision"],
                    "expected_assignment_revision": 1,
                    "decision": "apply",
                },
                headers,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    with Session(app.state.engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Outbox).where(Outbox.event_type == "assignment.reviewed")
            )
            == 1
        )


def test_correction_cannot_silently_transfer_employee(app, client):
    headers, first, event, pending = corrected(app, client)
    event.update(event_id=str(uuid4()), aggregate_revision=6)
    event["payload"]["position_code"] = "different-position"
    receive(app, event)
    pending = intake(client, headers)
    body = {"expected_revision": pending["revision"], "expected_assignment_revision": 1, "decision": "apply"}
    path = f"/intakes/{pending['id']}/review"
    assert command(client, path, body, headers).status_code == 409
    kept = command(
        client, path, {**body, "decision": "keep", "reason": "A separate transfer is needed"}, headers
    )
    assert kept.status_code == 200
    assert kept.json()["assignment"]["position_code"] == "economist-training"
    assert kept.json()["assignment"]["id"] == first["assignment"]["id"]


def test_review_date_cannot_invalidate_existing_end(app, client):
    headers, first, _, pending = corrected(app, client)
    ended = command(
        client,
        f"/assignments/{first['assignment']['id']}/end",
        {
            "expected_revision": 1,
            "ends_on": "2026-11-23",
            "reason": "Confirmed end",
        },
        headers,
    )
    assert ended.status_code == 200
    result = command(
        client,
        f"/intakes/{pending['id']}/review",
        {
            "expected_revision": pending["revision"],
            "expected_assignment_revision": 2,
            "decision": "apply",
        },
        headers,
    )
    assert result.status_code == 422
    assert intake(client, headers)["status"] == "needs_review"
