from fastapi.testclient import TestClient

from recognition.api import create_app
from recognition.store import DEMO_IDS, seed_demo
from tests.test_thanks import call


def test_session_privacy_and_material_withdrawal(tmp_path):
    db = tmp_path / "recognition.db"
    seed_demo(db)
    with TestClient(create_app(db)) as client:
        session_path(client)


def session_path(client):
    event = call(
        client,
        "POST",
        "/events",
        "organizer",
        {
            "title": "Group discussion",
            "description": "Synthetic group session",
            "starts_at": "2026-12-01T12:00:00+03:00",
            "ends_at": "2026-12-01T14:00:00+03:00",
            "location": "Demo hall",
            "capacity": 3,
            "type": "confidential_session",
            "facilitator_actor_id": DEMO_IDS["facilitator"],
        },
        201,
    )
    ep = "/events/" + event["id"]
    event = call(client, "POST", ep + "/open", "organizer", {"expected_revision": 1})
    call(client, "POST", ep + "/registrations", "alice", {"participants_count": 2}, 422)
    reg = call(client, "POST", ep + "/registrations", "alice", {"participants_count": 1}, 201)
    rp = "/registrations/" + reg["id"]
    call(client, "GET", rp, "manager", status=404)
    assert call(client, "GET", ep + "/registrations", "manager")["items"] == []
    assert (
        call(client, "GET", ep + "/registrations", "facilitator")["items"][0]["actor_id"] == DEMO_IDS["alice"]
    )
    call(
        client,
        "POST",
        rp + "/cancel",
        "facilitator",
        {"expected_revision": 1, "reason": "Not authorized"},
        404,
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
            "reason": "Rescheduled",
        },
    )
    assert event["available_places"] == 2
    reg = call(client, "GET", rp)
    reg = call(
        client, "POST", rp + "/reconfirm", body={"expected_revision": reg["revision"], "accepted": True}
    )
    call(
        client,
        "POST",
        ep + "/finish",
        "organizer",
        {"expected_revision": event["revision"], "outcome": "cancelled", "reason": "Facilitator unavailable"},
    )
    assert call(client, "GET", rp)["status"] == "cancelled"
    material = call(
        client,
        "POST",
        "/materials",
        "organizer",
        {
            "title": "Training course",
            "description": "Synthetic link, no real course content",
            "url": "https://example.org/training-v1",
            "version": 1,
            "audience_scope": {"kind": "actors", "actor_ids": [DEMO_IDS["alice"]]},
            "distribution_basis": "Synthetic demo permission",
        },
        201,
    )
    mp = "/materials/" + material["id"]
    call(client, "GET", mp, status=404)
    material = call(client, "POST", mp + "/publish", "organizer", {"expected_revision": 1})
    assert call(client, "GET", mp)["url"] == "https://example.org/training-v1"
    call(client, "GET", mp, "bob", status=404)
    assert call(client, "GET", "/materials", "bob")["items"] == []
    material = call(
        client,
        "POST",
        mp + "/withdraw",
        "organizer",
        {"expected_revision": material["revision"], "reason": "Distribution permission withdrawn"},
    )
    withdrawn = call(client, "GET", mp)
    assert withdrawn["status"] == "withdrawn" and "url" not in withdrawn and "history" not in withdrawn
    assert withdrawn["withdrawal_reason"] == "Distribution permission withdrawn"
    assert call(client, "GET", "/materials")["items"] == []
    successor = call(
        client,
        "POST",
        "/materials",
        "organizer",
        {
            "title": "Training course",
            "description": "Synthetic second version",
            "url": "https://example.org/training-v2",
            "version": 2,
            "supersedes_id": material["id"],
            "audience_scope": {"kind": "organization"},
            "distribution_basis": "New demo permission",
        },
        201,
    )
    assert successor["version"] == 2 and successor["id"] != material["id"]
    original = call(client, "GET", mp, "organizer")
    assert original["version"] == 1 and original["url"] == "https://example.org/training-v1"
    assert len(original["history"]) == 3
    return {
        "event_id": event["id"],
        "registration_id": reg["id"],
        "material_id": material["id"],
        "withdrawn_material": withdrawn,
        "successor_id": successor["id"],
    }
