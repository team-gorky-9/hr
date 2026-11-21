from fastapi.testclient import TestClient

from recognition.api import create_app
from recognition.store import seed_demo
from tests.test_thanks import call


def test_family_queue_and_reschedule(tmp_path):
    db = tmp_path / "recognition.db"
    seed_demo(db)
    with TestClient(create_app(db)) as client:
        event_path(client)


def event_path(client):
    event = call(
        client,
        "POST",
        "/events",
        "organizer",
        {
            "title": "Family day",
            "description": "Synthetic family gathering",
            "starts_at": "2026-12-01T12:00:00+03:00",
            "ends_at": "2026-12-01T14:00:00+03:00",
            "location": "Demo hall",
            "capacity": 3,
        },
        201,
    )
    ep = "/events/" + event["id"]
    event = call(client, "POST", ep + "/open", "organizer", {"expected_revision": 1})
    first = call(
        client,
        "POST",
        ep + "/registrations",
        "alice",
        {"participants_count": 3, "child_age_bands": ["7-12"]},
        201,
    )
    second = call(client, "POST", ep + "/registrations", "bob", {"participants_count": 2}, 201)
    assert first["status"] == "confirmed" and second["status"] == "waiting"
    call(client, "POST", ep + "/registrations", "alice", {"participants_count": 1}, 409)
    call(
        client,
        "POST",
        "/registrations/" + second["id"] + "/offer",
        "organizer",
        {"expected_revision": second["revision"]},
        409,
    )
    call(client, "POST", "/registrations/" + first["id"] + "/cancel", "alice", {"expected_revision": 1})
    rp = "/registrations/" + second["id"]
    second = call(client, "POST", rp + "/offer", "organizer", {"expected_revision": 1})
    assert call(client, "GET", ep, "reader")["available_places"] == 1
    second = call(
        client, "POST", rp + "/reconfirm", "bob", {"expected_revision": second["revision"], "accepted": True}
    )
    event = call(
        client,
        "PATCH",
        ep,
        "organizer",
        {
            "expected_revision": event["revision"],
            "starts_at": "2026-12-02T12:00:00+03:00",
            "ends_at": "2026-12-02T14:00:00+03:00",
            "reason": "Weather",
        },
    )
    assert event["available_places"] == 1
    second = call(client, "GET", rp, "bob")
    assert second["status"] == "awaiting_reconfirmation"
    assert second["agreed_event_revision"] < event["revision"]
    call(client, "GET", rp, "manager", status=404)
    assert call(client, "GET", ep + "/registrations", "manager")["items"] == []
    second = call(
        client, "POST", rp + "/reconfirm", "bob", {"expected_revision": second["revision"], "accepted": True}
    )
    assert second["agreed_event_revision"] == event["revision"]
    assert call(client, "GET", ep, "reader")["available_places"] == 1
    return {
        "event_id": event["id"],
        "registration_id": second["id"],
        "registration": second,
        "available_places": 1,
    }
