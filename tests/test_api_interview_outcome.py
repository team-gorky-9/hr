"""Итог телефонной встречи (wave-2-stage-1, раздел «Илья»; задача wave-2-ilya-interview-outcome).

Учебная pending-встреча создаётся существующим repo.open_interview либо POST гайда с FakeLLMClient —
живая модель не вызывается. Проверяется короткий путь контракта и ключевые отказы."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.ai import FakeLLMClient
from app.db import repository as repo
from app.db.models import Application, AuditLog, Interview, User
from tests.posting_helpers import posting_registry  # noqa: F401 (фикстура)
from tests.test_api import client  # noqa: F401 (фикстура)
from tests.test_api_interview import (  # noqa: F401 (фикстура use_llm)
    ADMIN,
    DEPT,
    HR,
    answer,
    case,
    guide_model,
    post_guide,
    training_profile,
    use_llm,
)

MSK = timezone(timedelta(hours=3))
HELD = datetime(2026, 11, 20, 11, 30, tzinfo=MSK)


def outcome(client, interview_id, *, result="continue", occurred_at=HELD, summary="Опыт подтвердил, зовём в департамент",
            expected_revision=1, headers=HR, **extra):  # noqa: F811
    body = {"expected_revision": expected_revision, "result": result,
            "occurred_at": occurred_at if isinstance(occurred_at, str) else occurred_at.isoformat(),
            "summary": summary, **extra}
    return client.post(f"/api/v1/interviews/{interview_id}/outcome", headers=headers, json=body)


def pending(session, posting_registry, code="py-9101", kind="phone"):  # noqa: F811
    data = case(session, training_profile(session), code)
    interview = repo.open_interview(session, data["application_id"], kind)
    session.commit()
    return data, interview


def error(response):
    return response.status_code, response.json()["error"]["code"]


def test_continue_is_recorded_and_read_back(session, client, posting_registry):  # noqa: F811
    data, interview = pending(session, posting_registry)
    stage_before = session.get(Application, data["application_id"]).current_stage_code
    hr = session.scalar(select(User).where(User.login == "hr_demo"))

    done = outcome(client, interview.id)
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["result"], body["revision"], body["interviewer_user_id"]) == ("continue", 2, str(hr.id))
    assert body["held_at"] == body["attempt_at"] and datetime.fromisoformat(body["held_at"]) == HELD
    assert body["summary"] == "Опыт подтвердил, зовём в департамент" and body["outcome_recorded_at"]

    listed = client.get(f"/api/v1/applications/{data['application_id']}/interviews", headers=HR).json()["items"]
    assert listed == [body]
    session.expire_all()
    # Итог встречи не меняет этап отклика и не создаёт отказ или резерв.
    assert session.get(Application, data["application_id"]).current_stage_code == stage_before
    audit = session.scalars(select(AuditLog).where(AuditLog.entity_id == str(interview.id))).all()
    assert [a.details["event"] for a in audit] == ["interview.outcome_recorded"]

    # Повтор той же команды — прежний результат без нового факта.
    replay = outcome(client, interview.id)
    assert (replay.status_code, replay.json()) == (200, body)
    assert session.scalar(select(func.count()).select_from(AuditLog)
                          .where(AuditLog.entity_id == str(interview.id))) == 1
    # Иной итог или другой актор — понятный конфликт; итог не перезаписан.
    assert error(outcome(client, interview.id, result="stop", expected_revision=2)) == (
        409, "INTERVIEW_ALREADY_COMPLETED")
    assert error(outcome(client, interview.id, headers=ADMIN)) == (409, "INTERVIEW_ALREADY_COMPLETED")
    session.expire_all()
    assert session.get(Interview, interview.id).result == "continue"


def test_no_answer_is_an_attempt_not_a_held_interview(session, client, posting_registry):  # noqa: F811
    _, interview = pending(session, posting_registry, "py-9102")
    body = outcome(client, interview.id, result="no_answer", summary="Не взял трубку, перезвонить завтра").json()
    assert body["result"] == "no_answer" and body["held_at"] is None
    assert datetime.fromisoformat(body["attempt_at"]) == HELD


def test_rejected_inputs_and_states(session, client, posting_registry):  # noqa: F811
    data, interview = pending(session, posting_registry, "py-9103")
    assert client.post(f"/api/v1/interviews/{interview.id}/outcome", headers=DEPT,
                       json={}).status_code == 403  # право — до разбора тела и до результата
    assert outcome(client, interview.id, headers={}).status_code == 401
    assert outcome(client, interview.id, summary="   ").status_code == 422
    assert outcome(client, interview.id, occurred_at="2026-11-20T11:30:00").status_code == 422  # без зоны
    assert error(outcome(client, interview.id, occurred_at=datetime.now(MSK) + timedelta(days=1))) == (
        422, "INVALID_OCCURRED_AT")
    assert outcome(client, interview.id, result="pending").status_code == 422
    assert outcome(client, interview.id, extra_field=True).status_code == 422
    assert error(outcome(client, interview.id, expected_revision=5)) == (409, "STALE_REVISION")
    assert error(outcome(client, uuid.uuid4())) == (404, "INTERVIEW_NOT_FOUND")
    department = repo.open_interview(session, data["application_id"], "department")
    session.commit()
    assert error(outcome(client, department.id)) == (409, "UNSUPPORTED_INTERVIEW_KIND")
    # После всех отказов встреча по-прежнему открыта.
    session.expire_all()
    assert (session.get(Interview, interview.id).result, session.get(Interview, interview.id).revision) == (
        "pending", 1)
    assert client.get(f"/api/v1/applications/{uuid.uuid4()}/interviews", headers=HR).status_code == 404
    assert client.get(f"/api/v1/applications/{data['application_id']}/interviews", headers=DEPT).status_code == 403


def test_guide_after_completed_interview_opens_next_pending(session, client, posting_registry, use_llm):  # noqa: F811
    data = case(session, training_profile(session), "py-9104")
    use_llm(FakeLLMClient(guide_model([])))
    first = post_guide(client, data["application_id"]).json()
    question = first["clarifications"][0]
    saved = answer(client, first, question)
    assert saved.status_code == 201, saved.text
    assert outcome(client, first["interview_id"]).status_code == 200

    second = post_guide(client, data["application_id"])
    assert second.status_code == 201, second.text
    assert second.json()["interview_id"] != first["interview_id"]
    items = client.get(f"/api/v1/applications/{data['application_id']}/interviews", headers=HR).json()["items"]
    assert [(i["id"], i["result"]) for i in items] == [(first["interview_id"], "continue"),
                                                       (second.json()["interview_id"], "pending")]
    # Ответ прежней встречи остаётся доступен.
    old = client.get(f"/api/v1/interviews/{first['interview_id']}/questions/{question['question_id']}/answers",
                     headers=HR).json()["items"]
    assert [a["answer_id"] for a in old] == [saved.json()["answer_id"]]
