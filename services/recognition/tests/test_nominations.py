from datetime import date, timedelta

from fastapi.testclient import TestClient

from recognition.api import create_app
from recognition.store import DEMO_IDS, seed_demo
from tests.test_thanks import call


def test_nomination_path(tmp_path):
    db = tmp_path / "recognition.db"
    seed_demo(db)
    with TestClient(create_app(db)) as client:
        nomination_path(client)


def nomination_path(client):
    today = date.today()
    campaign = call(
        client,
        "POST",
        "/campaigns",
        "organizer",
        {
            "title": "Shared work",
            "criteria": "Describe a concrete contribution",
            "starts_on": str(today - timedelta(days=1)),
            "ends_on": str(today + timedelta(days=1)),
            "reviewer_actor_id": DEMO_IDS["alice"],
        },
        201,
    )
    cp = "/campaigns/" + campaign["id"]
    call(client, "GET", cp, "reader", status=404)
    campaign = call(client, "POST", cp + "/open", "organizer", {"expected_revision": 1})
    nomination = call(
        client,
        "POST",
        cp + "/nominations",
        "alice",
        {"nominee_id": DEMO_IDS["bob"], "statement": "Verified the shared report totals"},
        201,
    )
    np = "/nominations/" + nomination["id"]
    call(client, "GET", np, "manager", status=404)
    nomination = call(client, "POST", np + "/consent", "bob", {"expected_revision": 1, "accepted": True})
    call(
        client,
        "POST",
        np + "/decision",
        "alice",
        {"expected_revision": 2, "result": "selected", "reason": "Concrete contribution"},
        409,
    )
    campaign = call(
        client,
        "PATCH",
        cp,
        "organizer",
        {
            "expected_revision": campaign["revision"],
            "reviewer_actor_id": DEMO_IDS["reviewer"],
            "reason": "Replace conflicted reviewer",
        },
    )
    nomination = call(
        client,
        "POST",
        np + "/decision",
        "reviewer",
        {"expected_revision": 2, "result": "selected", "reason": "Concrete contribution"},
    )
    assert call(client, "GET", cp + "/results", "reader")["items"] == []
    nomination = call(client, "POST", np + "/publication", "bob", {"expected_revision": 3, "allowed": True})
    declined = call(
        client,
        "POST",
        cp + "/nominations",
        "alice",
        {"nominee_id": DEMO_IDS["reader"], "statement": "Shared contribution"},
        201,
    )
    call(
        client,
        "POST",
        "/nominations/" + declined["id"] + "/consent",
        "reader",
        {"expected_revision": 1, "accepted": False},
    )
    results = call(client, "GET", cp + "/results", "reader")["items"]
    assert len(results) == 1 and results[0]["nominee_id"] == DEMO_IDS["bob"]
    assert "statement" not in results[0] and "history" not in results[0]
    assert call(client, "GET", np, "bob")["status"] == "selected"
    assert call(client, "GET", cp, "organizer")["history"][-1]["actor_id"] == DEMO_IDS["organizer"]
    return {"campaign_id": campaign["id"], "nomination_id": nomination["id"], "results": results}
