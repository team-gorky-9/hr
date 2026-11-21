"""Synthetic actors; catches stale consent, disclosure and self-approval."""

import importlib.util


def test_thanks_path(tmp_path):
    assert importlib.util.find_spec("recognition"), "recognition package is not implemented"
    from fastapi.testclient import TestClient

    from recognition.api import create_app
    from recognition.store import seed_demo

    db = tmp_path / "recognition.db"
    seed_demo(db)
    with TestClient(create_app(db)) as client:
        thanks_path(client, db)


def call(client, method, path, actor="alice", body=None, status=200):
    response = client.request(
        method, "/api/v1/recognition" + path, headers={"Authorization": f"Bearer demo-{actor}"}, json=body
    )
    assert response.status_code == status, response.text
    return response.json()


def thanks_path(client, db=None):
    from recognition.store import DEMO_IDS

    t = call(
        client,
        "POST",
        "/thanks",
        body={
            "recipient_id": DEMO_IDS["bob"],
            "text": "Thanks for the shared report",
            "requested_visibility": "organization",
        },
        status=201,
    )
    path = "/thanks/" + t["id"]
    call(client, "GET", path, "manager", status=404)
    call(client, "GET", path, "moderator", status=404)
    t = call(
        client,
        "POST",
        path + "/visibility",
        "bob",
        {"expected_revision": t["revision"], "choice": "organization"},
    )
    t = call(
        client,
        "POST",
        path + "/moderation",
        "moderator",
        {"expected_revision": t["revision"], "result": "returned", "reason": "Clarify contribution"},
    )
    t = call(
        client,
        "PATCH",
        path,
        body={"expected_revision": t["revision"], "text": "Thanks for checking the totals"},
    )
    call(client, "POST", path + "/visibility", "bob", {"expected_revision": 1, "choice": "organization"}, 409)
    assert call(client, "GET", "/thanks?view=wall", "reader")["items"] == []
    t = call(
        client,
        "POST",
        path + "/visibility",
        "bob",
        {"expected_revision": t["revision"], "choice": "organization"},
    )
    t = call(
        client,
        "POST",
        path + "/moderation",
        "moderator",
        {"expected_revision": t["revision"], "result": "approved"},
    )
    public = call(client, "GET", path, "reader")
    assert public["text"] == "Thanks for checking the totals"
    assert "history" not in public
    assert "recipient_choice" not in call(client, "GET", "/thanks?view=wall", "reader")["items"][0]
    assert len(call(client, "GET", path)["history"]) == 6
    own = call(
        client,
        "POST",
        "/thanks",
        "moderator",
        {"recipient_id": DEMO_IDS["bob"], "text": "Own contribution", "requested_visibility": "organization"},
        201,
    )
    own = call(
        client,
        "POST",
        "/thanks/" + own["id"] + "/visibility",
        "bob",
        {"expected_revision": 1, "choice": "organization"},
    )
    call(
        client,
        "POST",
        "/thanks/" + own["id"] + "/moderation",
        "moderator",
        {"expected_revision": own["revision"], "result": "approved"},
        409,
    )
    if db:
        from fastapi.testclient import TestClient

        from recognition.api import create_app

        with TestClient(create_app(db)) as reopened:
            assert call(reopened, "GET", path, "reader")["status"] == "published"
    t = call(
        client,
        "POST",
        path + "/withdraw",
        "bob",
        {"expected_revision": t["revision"], "reason": "Keep private"},
    )
    assert t["status"] == "withdrawn"
    assert call(client, "GET", "/thanks?view=wall", "reader")["items"] == []
    return {"thanks_id": t["id"], "status": t["status"], "public_before_withdrawal": public}
