"""Short synthetic HTTP scenarios; real sessions, migrations and disk SQLite."""

from tests.conftest import auth

PREFIX = "/api/v1/development"
MANAGER = "00000000-0000-4000-8000-000000000103"
OWNER = "00000000-0000-4000-8000-000000000104"


def call(client, method, path, headers, body=None, status=200):
    response = client.request(method, PREFIX + path, headers=headers, json=body)
    assert response.status_code == status, response.text
    return response.json()


def propose(client):
    owner, manager = auth(client, "employee"), auth(client, "department")
    goal = call(
        client,
        "POST",
        "/goals",
        owner,
        {
            "title": "Аналитическая сводка",
            "description": "Источник: ДИ экономиста, версия 2",
        },
        201,
    )
    goal = call(
        client,
        "POST",
        f"/goals/{goal['id']}/share",
        owner,
        {
            "expected_revision": goal["revision"],
            "recipient_actor_id": MANAGER,
        },
    )
    plan = call(
        client,
        "POST",
        "/plans",
        manager,
        {
            "goal_id": goal["id"],
            "goal_revision": goal["revision"],
            "reviewer_actor_id": MANAGER,
            "title": "Проба сводки",
            "criteria": [
                {"key": "sources", "text": "Указаны источники", "required": True},
                {"key": "conclusion", "text": "Обоснован вывод", "required": True},
            ],
            "activities": [
                {
                    "key": "draft",
                    "title": "Подготовить текст",
                    "criterion_keys": ["sources"],
                    "resource_note": "Час рабочего времени",
                },
                {
                    "key": "summary",
                    "title": "Сформулировать вывод",
                    "criterion_keys": ["conclusion"],
                    "resource_note": "Обсудить с руководителем",
                },
            ],
        },
        201,
    )
    return owner, manager, goal, plan


def activate(client):
    owner, manager, goal, plan = propose(client)
    plan = call(
        client,
        "POST",
        f"/plans/{plan['id']}/respond",
        owner,
        {
            "expected_revision": plan["revision"],
            "decision": "accept",
            "note": "Согласовано",
        },
    )
    return owner, manager, goal, plan


def test_goal_privacy_and_agreement(client):
    owner, manager, goal, plan = propose(client)
    outsider = auth(client, "hr")
    call(client, "GET", f"/goals/{goal['id']}", outsider, status=404)
    assert call(client, "GET", "/goals", outsider)["items"] == []
    returned = call(
        client,
        "POST",
        f"/plans/{plan['id']}/respond",
        owner,
        {
            "expected_revision": 1,
            "decision": "return",
            "note": "Уточните время",
        },
    )
    assert returned["status"] == "returned"
    corrected = call(
        client,
        "PATCH",
        f"/plans/{plan['id']}",
        manager,
        {
            "expected_revision": returned["revision"],
            "title": "Сводка за два часа",
        },
    )
    accepted = call(
        client,
        "POST",
        f"/plans/{plan['id']}/respond",
        owner,
        {
            "expected_revision": corrected["revision"],
            "decision": "accept",
            "note": "Согласовано",
        },
    )
    assert accepted["status"] == "active"
    call(
        client,
        "PATCH",
        f"/plans/{plan['id']}",
        manager,
        {
            "expected_revision": accepted["revision"],
            "title": "Подмена",
        },
        409,
    )
    changed = call(
        client,
        "PATCH",
        f"/goals/{goal['id']}",
        owner,
        {
            "expected_revision": goal["revision"],
            "description": "Новый личный интерес",
        },
    )
    assert changed["status"] == "private"
    call(client, "GET", f"/goals/{goal['id']}", manager, status=404)
    saved = call(client, "GET", f"/plans/{plan['id']}", owner)
    assert saved["goal_snapshot"]["description"] == "Источник: ДИ экономиста, версия 2"
    assert saved["goal_revision"] == goal["revision"]
    assert saved["agreed_revision"] == accepted["revision"]
    assert len(call(client, "GET", "/plans", manager)["items"]) == 1


def submit(client, plan, owner, activity="draft", criterion="sources", url=False):
    return call(
        client,
        "POST",
        f"/plans/{plan['id']}/submissions",
        owner,
        {
            "activity_key": activity,
            "criterion_keys": [criterion],
            "statement": "Подготовила сводку",
            "artifact": {
                "kind": "url" if url else "text",
                "value": "https://example.org/report" if url else "Источники: учебный реестр, версия 2",
                "mutable_source": False,
            },
        },
        201,
    )


def review(client, submission, manager, result="confirmed"):
    return call(
        client,
        "POST",
        f"/submissions/{submission['id']}/review",
        manager,
        {
            "results": [
                {"criterion_key": key, "result": result, "reason": "Проверен учебный материал"}
                for key in submission["criterion_keys"]
            ],
        },
        201,
    )


def test_attempts_keep_history_and_use_latest_evidence(client):
    owner, manager, _, plan = activate(client)
    first = submit(client, plan, owner)
    returned = review(client, first, manager, "needs_revision")
    second = submit(client, plan, owner, url=True)
    assert second["attempt_no"] == 2
    assert second["artifact"]["mutable_source"] is True
    progress = call(client, "GET", f"/plans/{plan['id']}/progress", owner)
    assert progress["criteria"][0]["state"] == "waiting"
    assert progress["criteria"][0]["submission_id"] == second["id"]
    assert progress["criteria"][1]["state"] == "unsubmitted"
    data = {"results": [{"criterion_key": "sources", "result": "confirmed", "reason": "Источник указан"}]}
    call(client, "POST", f"/submissions/{second['id']}/review", owner, data, 404)
    call(client, "POST", f"/submissions/{second['id']}/review", auth(client, "hr"), data, 404)
    approved = call(client, "POST", f"/submissions/{second['id']}/review", manager, data, 201)
    assert call(client, "POST", f"/submissions/{second['id']}/review", manager, data, 200) == approved
    data["results"][0]["reason"] = "Другое решение"
    conflict = call(client, "POST", f"/submissions/{second['id']}/review", manager, data, 409)
    assert conflict["error"]["code"] == "REVIEW_EXISTS"
    history = call(client, "GET", f"/plans/{plan['id']}/submissions", owner)["items"]
    assert history[0]["id"] == first["id"] and history[0]["review"]["id"] == returned["id"]
    assert history[0]["artifact"]["value"] == "Источники: учебный реестр, версия 2"
    assert history[1]["review"]["id"] == approved["id"]
    assert call(client, "GET", f"/plans/{plan['id']}/progress", owner)["completed_count"] == 1
    third = submit(client, plan, owner)
    latest = call(client, "GET", f"/plans/{plan['id']}/progress", owner)
    assert latest["completed_count"] == 0
    assert latest["criteria"][0]["submission_id"] == third["id"]
    assert latest["criteria"][0]["state"] == "waiting"
