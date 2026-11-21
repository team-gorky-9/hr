"""Detect direct-ID/list/history leaks and mutation by anyone except the two participants."""

import sqlite3

from fastapi.testclient import TestClient

from feedback.api import create_app
from feedback.store import DEMO_IDS, seed_demo
from tests.test_cycle import call


def confidential_path(client, database=None):
    recipients = call(client, "GET", "/confidential-recipients", "alice")
    assert recipients["items"][0]["id"] == DEMO_IDS["recipient"]
    assert "response_terms" in recipients and "notice" in recipients
    body = {
        "recipient_actor_id": DEMO_IDS["recipient"],
        "subject": "Training question",
        "text": "Please clarify the route for an individual workplace question",
    }
    call(client, "POST", "/confidential-cases", "alice", body | {"recipient_actor_id": DEMO_IDS["hr"]}, 422)
    call(client, "POST", "/confidential-cases", "alice", body | {"response_id": "forbidden-link"}, 422)
    case = call(client, "POST", "/confidential-cases", "alice", body, 201)
    assert case["author_actor_id"] == DEMO_IDS["alice"]
    path = f"/confidential-cases/{case['id']}"
    for actor in ("manager", "hr", "organizer", "bob", "outsider"):
        call(client, "GET", path, actor, status=404)
        assert call(client, "GET", "/confidential-cases", actor)["items"] == []
    call(client, "POST", path + "/reply", "alice", {"expected_revision": 1, "text": "Not recipient"}, 404)
    case = call(
        client,
        "POST",
        path + "/reply",
        "recipient",
        {"expected_revision": 1, "text": "Training response: contact the assigned HR recipient"},
    )
    saved = call(client, "GET", path, "alice")
    assert saved["reply"] == case["reply"] and len(saved["history"]) == 2
    assert saved["history"][0]["snapshot"]["status"] == "submitted"
    call(client, "POST", path + "/close", "alice", {"expected_revision": 2, "reason": " "}, 422)
    call(client, "POST", path + "/close", "alice", {"expected_revision": 1, "reason": "Resolved"}, 409)
    case = call(
        client, "POST", path + "/close", "alice", {"expected_revision": 2, "reason": "Explanation received"}
    )
    call(client, "POST", path + "/reply", "recipient", {"expected_revision": 3, "text": "Too late"}, 409)
    saved = call(client, "GET", path, "recipient")
    assert saved["status"] == "closed" and saved["close_reason"] == "Explanation received"
    assert len(saved["history"]) == 3
    if database:
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT count(*) FROM responses").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 0
    return {"case_id": case["id"], "case": saved, "recipient_id": DEMO_IDS["recipient"]}


def test_confidential_path(tmp_path):
    database = tmp_path / "feedback.db"
    seed_demo(database)
    with TestClient(create_app(database)) as client:
        result = confidential_path(client, database)
    with TestClient(create_app(database)) as client:
        assert call(client, "GET", f"/confidential-cases/{result['case_id']}", "alice") == result["case"]
