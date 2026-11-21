"""Short synthetic HTTP acceptance: progress, ownership and ended assignments."""

from datetime import date, datetime, timedelta

from tests.conftest import assignment, auth, command, employee

PREFIX = "/api/v1/onboarding"
EMPLOYEE_ACTOR = "00000000-0000-4000-8000-000000000104"


def assign_program(client, headers, assignment_id):
    return client.post(
        PREFIX + "/programs",
        headers=headers,
        json={"workforce_assignment_id": assignment_id, "template_code": "intro-v1", "template_version": 1},
    )


def test_intro_progress_is_persisted_and_private(client):
    hr, own = auth(client), auth(client, "employee")
    templates = client.get(PREFIX + "/templates", headers=hr)
    assert templates.status_code == 200, templates.text
    template = templates.json()["items"][0]
    assert template["code"] == "intro-v1" and len(template["steps"]) == 3
    person = employee(client, hr, account_actor_id=EMPLOYEE_ACTOR)
    job = assignment(client, person, hr, starts_on="2026-01-01")
    created = assign_program(client, hr, job["id"])
    assert created.status_code == 201, created.text
    program = created.json()
    assert (program["completed_count"], program["total_count"], program["revision"]) == (0, 3, 1)
    path = PREFIX + "/programs/" + program["id"]
    duplicate = assign_program(client, hr, job["id"])
    assert duplicate.status_code == 200 and duplicate.json()["id"] == program["id"]
    assert client.get(PREFIX + "/programs", headers=own).json()["items"][0]["id"] == program["id"]
    assert client.get(path, headers=auth(client, "hr_other")).status_code == 404
    first_path = path + "/steps/" + program["steps"][0]["key"] + "/acknowledge"
    assert client.post(first_path, headers=hr, json={"expected_revision": 1}).status_code == 403
    for count, step in enumerate(program["steps"], 1):
        result = client.post(
            path + "/steps/" + step["key"] + "/acknowledge",
            headers=own,
            json={"expected_revision": count},
        )
        assert result.status_code == 200, result.text
        assert result.json()["completed_count"] == count
    saved = client.get(path, headers=hr).json()
    assert saved["status"] == "intro_completed" and saved["revision"] == 4
    assert all(s["acknowledged_by"] == EMPLOYEE_ACTOR and s["acknowledged_at"] for s in saved["steps"])
    replay = client.post(first_path, headers=own, json={"expected_revision": 1})
    assert replay.status_code == 200 and replay.json() == saved
    # A different employee record has no actor link: the employee account must not see it.
    unlinked = employee(client, hr, name="Другой учебный сотрудник")
    other_job = assignment(client, unlinked, hr, starts_on="2026-01-01")
    other_program = assign_program(client, hr, other_job["id"]).json()
    assert other_program["account_link_required"] is True
    assert client.get(PREFIX + "/programs/" + other_program["id"], headers=own).status_code == 404
    assert len(client.get(PREFIX + "/programs", headers=own).json()["items"]) == 1
    print(
        {
            "employee_id": person["id"],
            "assignment_id": job["id"],
            "program_id": saved["id"],
            "progress": "3/3",
            "status": saved["status"],
        }
    )


def test_inactive_assignment_blocks_new_marks_and_cancel_keeps_history(client):
    hr, own = auth(client), auth(client, "employee")
    person = employee(client, hr, account_actor_id=EMPLOYEE_ACTOR)
    future_person = employee(client, hr)
    future = assignment(client, future_person, hr, starts_on=(date.today() + timedelta(days=10)).isoformat())
    refused = assign_program(client, hr, future["id"])
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "ASSIGNMENT_NOT_ACTIVE"
    job = assignment(client, person, hr, starts_on="2026-01-01")
    program = assign_program(client, hr, job["id"]).json()
    path = PREFIX + "/programs/" + program["id"]
    first = path + "/steps/" + program["steps"][0]["key"] + "/acknowledge"
    assert client.post(first, headers=own, json={"expected_revision": 1}).status_code == 200
    ended = command(
        client,
        "/assignments/" + job["id"] + "/end",
        {
            "expected_revision": 1,
            "ends_on": (date.today() - timedelta(days=1)).isoformat(),
            "reason": "Учебное завершение назначения",
        },
        hr,
    )
    assert ended.status_code == 200, ended.text
    second = path + "/steps/" + program["steps"][1]["key"] + "/acknowledge"
    refused = client.post(second, headers=own, json={"expected_revision": 2})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "ASSIGNMENT_NOT_ACTIVE"
    assert client.get(path, headers=own).json()["assignment_state"] == "inactive"
    assert (
        client.post(path + "/cancel", headers=hr, json={"expected_revision": 1, "reason": "end"}).json()[
            "error"
        ]["code"]
        == "STALE_REVISION"
    )
    cancelled = client.post(
        path + "/cancel",
        headers=hr,
        json={
            "expected_revision": 2,
            "reason": "Назначение завершено",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    saved = client.get(path, headers=hr).json()
    assert saved["status"] == "cancelled" and saved["completed_count"] == 1
    assert saved["cancel_reason"] == "Назначение завершено"
    history = client.get("/api/v1/employees/" + person["id"] + "/history", headers=hr).json()["items"]
    cancellation = next(row for row in history if row["action"] == "onboarding.cancel")
    assert datetime.fromisoformat(
        cancellation["before"]["steps"][0]["acknowledged_at"]
    ) == datetime.fromisoformat(saved["steps"][0]["acknowledged_at"])
    assert cancellation["after"]["status"] == "cancelled"
