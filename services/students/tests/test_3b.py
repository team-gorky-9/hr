from .conftest import MENTOR, MENTOR2, PREFIX, headers, placement, post

TASK = {"title": "Разбор обращений", "description": "Объяснить классификацию", "criteria": [
    {"key": "classification", "text": "Объясняет спорные категории", "required": True}]}


def task(client, placement_id):
    return post(client, f"/placements/{placement_id}/tasks", TASK, "department", expected=201)


def submission(client, placement_id, task_id, text="Учебная работа"):
    return post(client, f"/placements/{placement_id}/submissions",
                {"task_version_id": task_id, "text": text}, "candidate", expected=201)


def review(client, submission_id, result="confirmed", login="department", expected=200):
    return post(client, f"/submissions/{submission_id}/review", {"results": [
        {"criterion_key": "classification", "result": result, "reason": "Учебное основание"}]}, login, expected)


def test_work_attempts_and_mentor_change(client):
    p = placement(client)
    t = task(client, p["id"])
    first = submission(client, p["id"], t["id"], "Первая версия")
    returned = review(client, first["id"], "needs_revision")
    assert review(client, first["id"], "needs_revision")["id"] == returned["id"]
    assert review(client, first["id"], expected=409)["error"]["code"] == "REVIEW_ALREADY_RECORDED"
    assert client.get(PREFIX + f"/placements/{p['id']}/submissions", headers=headers("candidate2")).status_code == 404
    assert post(client, f"/placements/{p['id']}/tasks", TASK, "department", expected=409)["error"]["code"] == "TASK_ALREADY_SUBMITTED"
    second = submission(client, p["id"], t["id"], "Исправлена классификация")
    changed = post(client, f"/placements/{p['id']}/mentor", {"expected_revision": 1,
                   "mentor_actor_id": MENTOR2, "reason": "Учебная замена"})
    assert changed["revision"] == 2
    assert review(client, second["id"], expected=404)["error"]["code"] == "NOT_FOUND"
    confirmed = review(client, second["id"], login="employee")
    saved = client.get(PREFIX + f"/placements/{p['id']}/submissions", headers=headers("candidate")).json()
    assert saved["work_state"] == "confirmed"
    assert len(saved["items"]) == 2
    assert saved["items"][0]["text"] == "Первая версия"
    assert saved["items"][0]["review"]["reviewed_by"] == MENTOR
    assert saved["items"][1]["review"]["reviewed_by"] == MENTOR2
    print({"placement": p["id"], "task": t["id"], "first_review": returned["id"], "confirmed_review": confirmed["id"]})
