"""Detect measures on hidden themes, unauthorized changes and participation-gated outcomes."""

from fastapi.testclient import TestClient

from feedback.api import create_app
from feedback.store import DEMO_IDS, seed_demo
from tests.test_cycle import call, cycle_body
from tests.test_publication import prepare_closed, publish


def action_path(client, database=None):
    cycle = prepare_closed(client)
    p = publish(client, cycle)
    body = {
        "publication_id": p["id"],
        "group_key": "large",
        "topic_key": "work",
        "text": "Clarify workload planning",
        "owner_actor_id": DEMO_IDS["bob"],
        "due_on": "2026-12-01",
    }
    m = call(client, "POST", "/measures", "manager", body, 201)
    call(client, "POST", "/measures", "small-manager", body, 404)
    call(client, "POST", "/measures", body=body | {"group_key": "small"}, status=409)
    path = f"/measures/{m['id']}"
    call(
        client,
        "PATCH",
        path,
        "alice",
        {"expected_revision": 1, "status": "completed", "outcome_note": "x"},
        404,
    )
    call(client, "PATCH", path, "bob", {"expected_revision": 1, "status": "completed"}, 422)
    m = call(client, "PATCH", path, "bob", {"expected_revision": 1, "status": "in_progress"})
    call(
        client,
        "PATCH",
        path,
        "bob",
        {"expected_revision": 1, "status": "completed", "outcome_note": "x"},
        409,
    )
    m = call(
        client,
        "PATCH",
        path,
        "bob",
        {"expected_revision": 2, "status": "completed", "outcome_note": "Team planning routine agreed"},
    )
    message = call(
        client,
        "POST",
        f"/publications/{p['id']}/participant-message",
        body={"text": "We heard workload concerns and agreed a planning routine", "measure_ids": [m["id"]]},
        status=201,
    )
    # Alice has never submitted a response; audience membership alone grants the outcome.
    outcome = call(client, "GET", f"/cycles/{cycle['id']}/outcome", "alice")
    assert outcome["messages"][0]["id"] == message["id"]
    assert outcome["messages"][0]["measures"][0]["outcome_note"] == "Team planning routine agreed"
    assert call(client, "GET", f"/cycles/{cycle['id']}/outcome", "small-manager")["messages"] == []
    assert call(client, "GET", "/measures", "small-manager")["items"] == []
    assert call(client, "GET", "/measures", "manager")["items"][0]["status"] == "completed"
    assert call(client, "GET", "/measures", "bob")["items"][0]["id"] == m["id"]
    call(client, "GET", f"/cycles/{cycle['id']}/outcome", "outsider", status=404)
    next_cycle = call(client, "POST", "/cycles", body=cycle_body() | {"question_version": "v2"}, status=201)
    next_cycle = call(client, "POST", f"/cycles/{next_cycle['id']}/open", body={"expected_revision": 1})
    next_cycle = call(client, "POST", f"/cycles/{next_cycle['id']}/close", body={"expected_revision": 2})
    publish(client, next_cycle)
    comparison = call(
        client, "GET", f"/cycles/{cycle['id']}/outcome?compare_cycle_id={next_cycle['id']}", "alice"
    )["comparison"]
    assert comparison["comparable"] is False and "QUESTIONS_DIFFER" in comparison["reasons"]
    return {
        "cycle_id": cycle["id"],
        "publication_id": p["id"],
        "measure_id": m["id"],
        "message_id": message["id"],
        "outcome": outcome,
        "comparison": comparison,
    }


def test_action_path(tmp_path):
    database = tmp_path / "feedback.db"
    seed_demo(database)
    with TestClient(create_app(database)) as client:
        result = action_path(client)
    with TestClient(create_app(database)) as client:
        assert call(client, "GET", f"/cycles/{result['cycle_id']}/outcome", "alice") == result["outcome"]
