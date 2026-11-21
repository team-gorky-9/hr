"""4A: GET /management/overview (wave-4-reporting-stage-1) — воронка и факты телефонных встреч.

Встречи завершаются настоящей операцией POST /interviews/{id}/outcome второй волны; живая модель
не вызывается (встречу открывает repo.open_interview)."""
from sqlalchemy import select

from app.db import repository as repo
from app.db.models import Interview, User
from tests.posting_helpers import posting_registry  # noqa: F401 (фикстура)
from tests.test_api import client  # noqa: F401 (фикстура)
from tests.test_api_interview import HR, case, training_profile

PATH = "/api/v1/management/overview"
PERIOD = {"from": "2026-11-20", "to": "2026-11-21", "contour": "training"}


def phone(session, profile, code):
    data = case(session, profile, code)
    interview = repo.open_interview(session, data["application_id"], "phone")
    session.commit()
    return interview


def finish(client, interview, result, occurred_at):  # noqa: F811
    response = client.post(f"/api/v1/interviews/{interview.id}/outcome", headers=HR, json={
        "expected_revision": 1, "result": result, "occurred_at": occurred_at,
        "summary": "Учебный итог встречи для сводки"})
    assert response.status_code == 200, response.text


def test_overview_separates_held_no_answer_open_and_day_bounds(session, client, posting_registry):  # noqa: F811
    profile = training_profile(session)
    held = phone(session, profile, "py-9501")
    late = phone(session, profile, "py-9502")
    missed = phone(session, profile, "py-9503")
    phone(session, profile, "py-9504")                      # открытая встреча без итога
    legacy = phone(session, profile, "py-9505")
    finish(client, held, "continue", "2026-11-20T23:59:00+03:00")    # последний день периода — входит
    finish(client, late, "stop", "2026-11-21T00:00:00+03:00")        # to исключительно — не входит
    finish(client, missed, "no_answer", "2026-11-20T10:00:00+03:00")
    # Старая строка с итогом, но без даты разговора: в период не попадает и проведённой не считается.
    session.get(Interview, legacy.id).result = "continue"
    session.commit()

    response = client.get(PATH, headers=HR, params=PERIOD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["period"] == {"from": "2026-11-20", "to": "2026-11-21", "timezone": "Europe/Moscow"}
    assert body["source"] == {"system": "legacy-hr", "contour": "training"}
    block = body["interviews"]
    assert (block["status"], block["held_count"], block["held_applications_count"], block["no_answer_count"],
            block["open_count"], block["undated_count"]) == ("available", 1, 1, 1, 1, 1)
    hr = session.scalar(select(User).where(User.login == "hr_demo"))
    [row] = block["by_interviewer"]
    assert (row["interviewer_user_id"], row["login"], row["held_count"], row["no_answer_count"]) == (
        str(hr.id), "hr_demo", 1, 1)
    assert row["outcomes"] == {"continue": 1, "stop": 0, "pending": 0}
    assert set(block["units"]) >= {"held_count", "no_answer_count", "held_applications_count"}

    # Воронка — существующая /analytics/funnel без изменений правил: тот же срез, последний день to-1.
    funnel = client.get("/api/v1/analytics/funnel", headers=HR, params={
        "contour": "training", "period_from": "2026-11-20", "period_to": "2026-11-20"}).json()
    assert {k: v for k, v in body["funnel"].items() if k != "as_of"} == {k: v for k, v in funnel.items() if k != "as_of"}

    sources = {s["key"]: s["status"] for s in body["sources"]}
    assert sources == {"legacy-hr.applications": "available", "legacy-hr.interviews": "available",
                       "workforce": "unavailable", "hiring": "unavailable", "practice": "unavailable"}

    # Следующий день: поздний stop входит, остальные — нет.
    next_day = client.get(PATH, headers=HR, params=PERIOD | {"from": "2026-11-21", "to": "2026-11-22"}).json()
    assert (next_day["interviews"]["held_count"], next_day["interviews"]["no_answer_count"]) == (1, 0)
    assert next_day["interviews"]["by_interviewer"][0]["outcomes"]["stop"] == 1


def test_empty_journal_and_contour(session, client, posting_registry):  # noqa: F811
    profile = training_profile(session)
    finish(client, phone(session, profile, "py-9511"), "continue", "2026-11-20T12:00:00+03:00")
    working = client.get(PATH, headers=HR, params=PERIOD | {"contour": "working"}).json()["interviews"]
    assert (working["held_count"], working["open_count"], working["by_interviewer"]) == (0, 0, [])
    assert working["coverage_note"].startswith("0 зарегистрировано в этом журнале")


def test_access_and_inputs(session, client):  # noqa: F811
    assert client.get(PATH, headers={"X-User-Login": "dept_demo"}, params=PERIOD).status_code == 403
    assert client.get(PATH, params=PERIOD).status_code == 401
    same_day = client.get(PATH, headers=HR, params=PERIOD | {"to": "2026-11-20"})
    assert (same_day.status_code, same_day.json()["error"]["code"]) == (422, "INVALID_PERIOD")
    assert client.get(PATH, headers=HR, params={"from": "2026-11-20", "to": "2026-11-21"}).status_code == 422
    assert client.get(PATH, headers=HR, params=PERIOD | {"from": "20.11.2026"}).status_code == 422
