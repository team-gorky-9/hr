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
