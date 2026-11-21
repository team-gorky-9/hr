"""Detect code reuse, invalid-input consumption and identity leaking into stored answers."""

import importlib.util
import json
import sqlite3


def call(client, method, path, actor="organizer", body=None, status=200):
    headers = {"Authorization": f"Bearer demo-{actor}"} if actor else {}
    response = client.request(method, "/api/v1/feedback" + path, headers=headers, json=body)
    # Never echo request/response contents: access-code errors must not leak credentials.
    assert response.status_code == status, (method, path, response.status_code, status)
    return response.json()


def cycle_body():
    return {
        "title": "Training pulse",
        "question_version": "v1",
        "questions": [{"key": "load", "text": "Workload", "min": 1, "max": 2}],
        "topic_options": [{"key": "work", "label": "Workload"}, {"key": "learning", "label": "Learning"}],
        "groups": [
            {"key": "large", "label": "Large training group", "eligible_count": 30},
            {"key": "small", "label": "Small training group", "eligible_count": 3},
        ],
    }


def open_cycle(client):
    cycle = call(client, "POST", "/cycles", body=cycle_body(), status=201)
    return call(client, "POST", f"/cycles/{cycle['id']}/open", body={"expected_revision": 1})


def answer(code, value=1, topic="work"):
    return {"access_code": code, "answers": [{"question_key": "load", "value": value}], "topic_key": topic}


def cycle_path(client, database):
    c = open_cycle(client)
    path = f"/cycles/{c['id']}"
    form = call(client, "GET", path + "/form", None)
    assert "privacy_notice" in form and "groups" not in form
    call(client, "POST", path + "/access-codes", "manager", {"group_key": "large", "count": 1}, 404)
    codes = call(client, "POST", path + "/access-codes", body={"group_key": "small", "count": 2})["codes"]
    call(client, "POST", path + "/access-codes", body={"group_key": "small", "count": 2}, status=409)
    call(client, "POST", path + "/responses", None, answer(codes[0], 9), 422)
    malformed = answer(codes[0]) | {"actor_id": "private-marker"}
    error = call(client, "POST", path + "/responses", None, malformed, 422)
    assert codes[0] not in json.dumps(error) and "private-marker" not in json.dumps(error)
    assert call(client, "POST", path + "/responses", None, answer(codes[0]), 201) == {"accepted": True}
    assert (
        call(client, "POST", path + "/responses", None, answer(codes[0]), 409)["detail"]["code"]
        == "CODE_ALREADY_USED"
    )
    call(client, "POST", path + "/close", body={"expected_revision": 1}, status=409)
    c = call(client, "POST", path + "/close", body={"expected_revision": c["revision"]})
    call(client, "POST", path + "/responses", None, answer(codes[1]), 409)
    call(client, "GET", path + "/responses", status=405)
    with sqlite3.connect(database) as db:
        row = db.execute("SELECT * FROM responses").fetchone()
        columns = [x[1] for x in db.execute("PRAGMA table_info(responses)")]
        assert set(columns) == {"id", "cycle_id", "group_key", "answers", "topic_key"}
        assert len(row) == 5
        assert db.execute("SELECT count(*) FROM access_codes WHERE used=1").fetchone()[0] == 1
    return {"cycle_id": c["id"], "status": c["status"], "response_columns": columns}


def test_cycle_path(tmp_path):
    assert importlib.util.find_spec("feedback"), "feedback service is not implemented"
    from fastapi.testclient import TestClient

    from feedback.api import create_app
    from feedback.store import seed_demo

    database = tmp_path / "feedback.db"
    seed_demo(database)
    with TestClient(create_app(database)) as client:
        result = cycle_path(client, database)
    with TestClient(create_app(database)) as client:
        assert call(client, "GET", f"/cycles/{result['cycle_id']}/form", None)["status"] == "closed"
