"""Сквозные и конкурентные тесты workflow-01: сводка без ПДн, передача, ожидания,
кабинет двух получателей и версионные ответы департамента на настоящей PostgreSQL.
"""
import threading
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import (
    ApplicationSource,
    FeedbackOutcome,
    InterviewKind,
    QuestionAuthor,
    ReserveStatus,
    UserRole,
)
from app.db.models import (
    Application,
    Candidate,
    DepartmentFeedback,
    HandoffAttempt,
    Interview,
    InterviewQuestion,
    ReserveEntry,
    SourceDocument,
    User,
)
from app.db.session import get_session
from app.main import create_app
from tests import factories as f
from tests.test_api import PII, build_case, client  # noqa: F401
from tests.test_api_workflow import ADMIN, DEPT, HR, application, error_code, history, move, no_pii

DEPT2 = {"X-User-Login": "dept2_demo"}


def _user(session: Session, login: str) -> User:
    return session.scalar(select(User).where(User.login == login))


def _summary(client: TestClient, application_id, headers=HR) -> dict:
    response = client.get(f"/api/v1/applications/{application_id}/handoff-summary", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _handoff_to_user(client: TestClient, application_id, user_id: uuid.UUID, **extra) -> dict:
    summary = _summary(client, application_id)
    return {
        "recipient_user_id": str(user_id),
        "channel": "cabinet",
        "summary_revision": summary["summary_revision"],
        "request_id": str(uuid.uuid4()),
        **extra,
    }


# --- 1. Предпросмотр сводки без ожиданий и фильтрация ПДн/контактов ----------------

def test_handoff_summary_preview_creates_zero_waits_and_excludes_pii(session, client):
    """Двойной просмотр сводки оставляет 0 передач и 0 ожиданий; заметки с контактами и ПДн исключаются целиком."""
    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    assert move(client, app_id, "screening", comment="Опыт API подтверждён, уточнить длительность").status_code == 201
    assert move(
        client,
        app_id,
        "phone_interview",
        comment=f"Перезвонить кандидату на {PII['phone']}",
    ).status_code == 201

    interview = Interview(
        application_id=app_id,
        kind=InterviewKind.PHONE,
        summary=f"Связались по почте {PII['email']}",
    )
    session.add(interview)
    session.flush()
    session.add_all(
        [
            InterviewQuestion(
                interview_id=interview.id,
                gap="длительность коммерческого опыта",
                question="С какого по какой месяц длился проект и в каком качестве вы работали?",
                author=QuestionAuthor.MODEL,
                answer_notes="С 03.2023 по 12.2024 по договору, писал API-тесты",
                sort_order=1,
            ),
            InterviewQuestion(
                interview_id=interview.id,
                gap="связь",
                question="Удобный способ связи?",
                author=QuestionAuthor.HUMAN,
                answer_notes=f"Тг: @ivanov_test, {PII['full_name']}",
                sort_order=2,
            ),
        ]
    )
    session.flush()

    first = client.get(f"/api/v1/applications/{app_id}/handoff-summary", headers=HR)
    second = client.get(f"/api/v1/applications/{app_id}/handoff-summary", headers=HR)
    assert first.status_code == 200 and second.status_code == 200
    no_pii(first)
    body = first.json()
    assert body["summary_revision"] == second.json()["summary_revision"]
    assert body["from_snapshot"] is False and body["attempt_id"] is None
    assert body["summary"]["omitted_notes_count"] == 3
    assert [n["text"] for n in body["summary"]["hr_notes"]] == ["Опыт API подтверждён, уточнить длительность"]
    answers = [q["answer_text"] for q in body["summary"]["interview_notes"][0]["questions"]]
    assert answers == ["С 03.2023 по 12.2024 по договору, писал API-тесты", None]
    assert "@ivanov_test" not in first.text
    assert str(built["text_id"]) in body["summary"]["referenced_text_ids"]
    assert "Опыт API подтверждён" in body["markdown"]
    assert "@ivanov_test" not in body["markdown"]
    assert session.scalar(select(func.count()).select_from(HandoffAttempt)) == 0
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()["open_waits"]["total"] == 0


# --- 2. Подтверждение передачи, снимок, ошибки и атомарность -----------------------

def test_stage_requires_handoff_and_atomically_creates_attempt_and_snapshot(session, client, monkeypatch):
    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    dept_user = _user(session, "dept_demo")
    assert move(client, app_id, "screening").status_code == 201
    assert move(client, app_id, "phone_interview").status_code == 201

    no_handoff = move(client, app_id, "sent_to_department", handoff=None)
    assert (no_handoff.status_code, error_code(no_handoff)) == (422, "HANDOFF_REQUIRED")

    extra_handoff = move(client, app_id, "rejected", rejection_reason_code="experience",
                         handoff=_handoff_to_user(client, app_id, dept_user.id))
    assert (extra_handoff.status_code, error_code(extra_handoff)) == (422, "HANDOFF_NOT_ALLOWED")

    stale_rev = move(client, app_id, "sent_to_department",
                     handoff=_handoff_to_user(client, app_id, dept_user.id, summary_revision="outdated"))
    assert (stale_rev.status_code, error_code(stale_rev)) == (409, "SUMMARY_CHANGED")
    assert history(client, app_id)["stage"]["code"] == "phone_interview"
    assert session.scalar(select(func.count()).select_from(HandoffAttempt)) == 0

    def broken_attempt(*args, **kwargs):
        raise RuntimeError("snapshot failure")

    with monkeypatch.context() as mp:
        mp.setattr(repo, "create_handoff_attempt", broken_attempt)
        with pytest.raises(RuntimeError, match="snapshot failure"):
            move(client, app_id, "sent_to_department", handoff=_handoff_to_user(client, app_id, dept_user.id))
    assert history(client, app_id)["stage"]["code"] == "phone_interview"
    assert session.scalar(select(func.count()).select_from(HandoffAttempt)) == 0

    seq_before = history(client, app_id)["last_seq"]
    handoff_body = _handoff_to_user(client, app_id, dept_user.id)
    sent = move(client, app_id, "sent_to_department", expected_seq=seq_before, handoff=handoff_body)
    assert sent.status_code == 201, sent.text
    attempt_id = sent.json()["handoff"]["attempt_id"]
    assert sent.json()["handoff"]["status"] == "awaiting_response"
    assert client.get("/api/v1/handoffs", params={"contour": "training"}, headers=HR).json()["total"] == 1
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()["open_waits"]["total"] == 1

    # Повтор с тем же request_id и прежним expected_seq возвращает исходную попытку (200).
    retry = move(client, app_id, "sent_to_department", expected_seq=seq_before, handoff=handoff_body)
    assert retry.status_code == 200
    assert retry.json()["handoff"]["attempt_id"] == attempt_id
    assert session.scalar(select(func.count()).select_from(HandoffAttempt)) == 1

    reused = move(client, app_id, "sent_to_department", expected_seq=seq_before,
                  handoff={**handoff_body, "channel": "email"})
    assert (reused.status_code, error_code(reused)) == (409, "REQUEST_ID_REUSED")

    # Замороженный снимок читается неизменным после появления новой версии текста (stale).
    repo.add_candidate_text(session, built["candidate_id"], text="Новый текст без старых строк.", redaction_method="v2")
    detail = client.get(f"/api/v1/handoffs/{attempt_id}", headers=HR)
    assert detail.status_code == 200
    assert detail.json()["summary"]["assessment_status"] == "ready"
    assert detail.json()["summary"]["versions"]["candidate_text_id"] == str(built["text_id"])


def test_stale_assessment_requires_allow_stale_flag(session, client):
    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    for stage in ("screening", "phone_interview"):
        assert move(client, app_id, stage).status_code == 201
    repo.add_candidate_text(session, built["candidate_id"], text="Переочищенный текст резюме.", redaction_method="v2")

    blocked = move(client, app_id, "sent_to_department")
    assert (blocked.status_code, error_code(blocked)) == (409, "ASSESSMENT_STALE")

    summary = _summary(client, app_id)
    assert summary["summary"]["assessment_status"] == "stale"
    allowed = move(client, app_id, "sent_to_department", handoff={
        "recipient_name": "Внешний руководитель",
        "recipient_department": "Юридический отдел",
        "channel": "email",
        "summary_revision": summary["summary_revision"],
        "request_id": str(uuid.uuid4()),
        "allow_stale": True,
    })
    assert allowed.status_code == 201


# --- 3. Отзывы департамента, исправления, запоздалый ответ и вторая попытка -------

def test_feedback_pending_external_not_fit_revision_and_late_update(session, client):
    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    candidate = session.get(Candidate, built["candidate_id"])
    second_app_id = application(session, "", position="qa-manual", candidate=candidate).id

    for stage in ("screening", "phone_interview", "sent_to_department"):
        assert move(client, app_id, stage).status_code == 201
    attempt_id = client.get(f"/api/v1/applications/{app_id}/handoffs", headers=HR).json()["items"][0]["attempt_id"]

    # Промежуточный ответ pending сохраняет ожидание открытым.
    pending_req = str(uuid.uuid4())
    pending_payload = {
        "attempt_id": attempt_id,
        "outcome": "pending",
        "contact_status": "yes",
        "interview_status": "no",
        "response_channel": "phone",
        "reported_by_name": "А.С. Руководитель",
        "comment": "Кандидат получил приглашение",
        "request_id": pending_req,
    }
    pending = client.post(f"/api/v1/applications/{app_id}/feedback", headers=HR, json=pending_payload)
    assert pending.status_code == 201, pending.text
    fb1_id = pending.json()["feedback"]["feedback_id"]
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()["open_waits"]["total"] == 1

    # Валидация причины отказа.
    missing_reason = client.post(f"/api/v1/applications/{app_id}/feedback", headers=HR, json={
        "attempt_id": attempt_id,
        "outcome": "not_fit",
        "response_channel": "sed",
        "reported_by_name": "А.С. Руководитель",
        "request_id": str(uuid.uuid4()),
    })
    assert (missing_reason.status_code, error_code(missing_reason)) == (422, "REJECTION_REASON_REQUIRED")

    bad_reason = client.post(f"/api/v1/applications/{app_id}/feedback", headers=HR, json={
        "attempt_id": attempt_id,
        "outcome": "fit",
        "rejection_reason_code": "experience",
        "response_channel": "sed",
        "reported_by_name": "А.С. Руководитель",
        "request_id": str(uuid.uuid4()),
    })
    assert (bad_reason.status_code, error_code(bad_reason)) == (422, "REJECTION_REASON_NOT_ALLOWED")

    # Конечный ответ not_fit как исправление (supersedes_id) закрывает ожидание (1 -> 0), не меняя этап и резерв.
    not_fit_payload = {
        "attempt_id": attempt_id,
        "supersedes_id": fb1_id,
        "outcome": "not_fit",
        "contact_status": "yes",
        "interview_status": "yes",
        "rejection_reason_code": "experience",
        "keep_in_reserve": True,
        "comment": "Хорошее знание API, но мал коммерческий стаж",
        "response_channel": "sed",
        "reported_by_name": "А.С. Руководитель",
        "request_id": str(uuid.uuid4()),
    }
    rev2 = client.post(f"/api/v1/applications/{app_id}/feedback", headers=HR, json=not_fit_payload)
    assert rev2.status_code == 201, rev2.text
    fb2 = rev2.json()["feedback"]
    assert (fb2["revision"], fb2["supersedes_id"], fb2["interview_held"]) == (2, fb1_id, True)
    assert fb2["recorded_by"]["login"] == "hr_demo" and fb2["response_channel"] == "sed"
    assert history(client, app_id)["stage"]["code"] == "sent_to_department"
    assert session.scalar(select(func.count()).select_from(ReserveEntry)) == 0

    funnel = client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()
    assert funnel["open_waits"]["total"] == 0 and funnel["closures"] == []

    # Повтор с тем же request_id -> 200, новой строки нет; повтор устаревшей ревизии сохраняет is_current=False.
    retry = client.post(f"/api/v1/applications/{app_id}/feedback", headers=HR, json=not_fit_payload)
    assert retry.status_code == 200 and retry.json()["created"] is False and retry.json()["feedback"]["is_current"] is True
    retry_old = client.post(f"/api/v1/applications/{app_id}/feedback", headers=HR, json=pending_payload)
    assert retry_old.status_code == 200
    assert retry_old.json()["created"] is False
    assert (retry_old.json()["feedback"]["revision"], retry_old.json()["feedback"]["is_current"]) == (1, False)

    feed = client.get(f"/api/v1/applications/{app_id}/feedback", headers=HR).json()
    assert feed["total"] == 2
    assert [(i["revision"], i["is_current"]) for i in feed["items"]] == [(1, False), (2, True)]

    # Кадровик сам закрывает отклик; второй отклик остаётся на этапе new.
    assert move(client, app_id, "rejected", rejection_reason_code="experience").status_code == 201
    assert history(client, second_app_id)["stage"]["code"] == "new"

    # Запоздалое исправление отзыва на закрытом отклике сохраняется у попытки и не меняет этап/счётчик отказов.
    late = client.post(f"/api/v1/applications/{app_id}/feedback", headers=HR, json={
        "attempt_id": attempt_id,
        "supersedes_id": fb2["feedback_id"],
        "outcome": "not_fit",
        "contact_status": "yes",
        "interview_status": "yes",
        "rejection_reason_code": "competencies",
        "keep_in_reserve": True,
        "response_channel": "email",
        "reported_by_name": "А.С. Руководитель",
        "request_id": str(uuid.uuid4()),
    })
    assert late.status_code == 201 and late.json()["feedback"]["revision"] == 3
    assert history(client, app_id)["stage"]["code"] == "rejected"
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()["closures"][0]["count"] == 1


def test_second_handoff_to_another_recipient_keeps_independent_wait(session, client):
    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    dept1, dept2 = _user(session, "dept_demo"), _user(session, "dept2_demo")

    assert move(client, app_id, "screening").status_code == 201
    assert move(client, app_id, "phone_interview").status_code == 201
    first = move(client, app_id, "sent_to_department", handoff=_handoff_to_user(client, app_id, dept1.id))
    assert first.status_code == 201
    attempt1_id = first.json()["handoff"]["attempt_id"]

    # Ответ по первой попытке закрывает её ожидание (1 -> 0).
    fb1 = client.post(f"/api/v1/applications/{app_id}/feedback", headers=DEPT, json={
        "attempt_id": attempt1_id,
        "outcome": "not_fit",
        "rejection_reason_code": "experience",
        "request_id": str(uuid.uuid4()),
    })
    assert fb1.status_code == 201
    fb1_id = fb1.json()["feedback"]["feedback_id"]
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()["open_waits"]["total"] == 0

    # Вторая передача другому получателю создаёт новое открытое ожидание.
    seq = history(client, app_id)["last_seq"]
    second = client.post(f"/api/v1/applications/{app_id}/handoffs", headers=HR, json={
        "expected_seq": seq,
        "handoff": _handoff_to_user(client, app_id, dept2.id),
    })
    assert second.status_code == 201, second.text
    attempt2_id = second.json()["attempt"]["attempt_id"]
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()["open_waits"]["total"] == 1

    # Позднее исправление первого отзыва НЕ закрывает ожидание второй попытки.
    fix1 = client.post(f"/api/v1/applications/{app_id}/feedback", headers=DEPT, json={
        "attempt_id": attempt1_id,
        "supersedes_id": fb1_id,
        "outcome": "not_fit",
        "rejection_reason_code": "competencies",
        "request_id": str(uuid.uuid4()),
    })
    assert fix1.status_code == 201
    assert client.get(f"/api/v1/handoffs/{attempt2_id}", headers=HR).json()["status"] == "awaiting_response"
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()["open_waits"]["total"] == 1


def test_stage_transitions_close_open_waits_except_department_interview(session, client):
    app1 = application(session, "py-0501").id
    for stage in ("screening", "phone_interview", "sent_to_department"):
        assert move(client, app1, stage).status_code == 201
    attempt1 = client.get(f"/api/v1/applications/{app1}/handoffs", headers=HR).json()["items"][0]["attempt_id"]

    # Переход в department_interview оставляет ожидание открытым.
    assert move(client, app1, "department_interview").status_code == 201
    assert client.get(f"/api/v1/handoffs/{attempt1}", headers=HR).json()["status"] == "awaiting_response"
    assert client.get("/api/v1/analytics/funnel", headers=HR).json()["open_waits"]["total"] == 1

    # Выход в финальный этап (withdrawn) закрывает ожидание без ответа.
    assert move(client, app1, "withdrawn", rejection_reason_code="candidate_declined").status_code == 201
    detail1 = client.get(f"/api/v1/handoffs/{attempt1}", headers=HR).json()
    assert detail1["status"] == "closed_without_response" and detail1["close_reason"] == "stage_moved:withdrawn"
    assert client.get("/api/v1/analytics/funnel", headers=HR).json()["open_waits"]["total"] == 0

    # Запоздалый ответ всё равно принимается по attempt_id, но статус/этап не переоткрываются.
    late = client.post(f"/api/v1/applications/{app1}/feedback", headers=HR, json={
        "attempt_id": attempt1,
        "outcome": "fit",
        "response_channel": "phone",
        "reported_by_name": "Руководитель",
        "request_id": str(uuid.uuid4()),
    })
    assert late.status_code == 201
    assert client.get(f"/api/v1/handoffs/{attempt1}", headers=HR).json()["status"] == "closed_without_response"

    # Возврат на ранний этап также закрывает ожидание.
    app2 = application(session, "py-0502").id
    for stage in ("screening", "phone_interview", "sent_to_department"):
        assert move(client, app2, stage).status_code == 201
    attempt2 = client.get(f"/api/v1/applications/{app2}/handoffs", headers=HR).json()["items"][0]["attempt_id"]
    assert move(client, app2, "phone_interview", confirm_skip=True, comment="Возврат на повторное уточнение").status_code == 201
    assert client.get(f"/api/v1/handoffs/{attempt2}", headers=HR).json()["status"] == "closed_without_response"


# --- 4. Ограниченный кабинет двух получателей и сквозной контроль по прямому ID ---

def test_department_cabinet_two_recipients_isolation_and_direct_id_checks(session, client):
    built = build_case(session, "C5-non-bmp")
    app1_id, text1_id = built["application_id"], built["text_id"]
    dept1, dept2 = _user(session, "dept_demo"), _user(session, "dept2_demo")

    for stage in ("screening", "phone_interview"):
        assert move(client, app1_id, stage).status_code == 201
    sent1 = move(client, app1_id, "sent_to_department", handoff=_handoff_to_user(client, app1_id, dept1.id))
    assert sent1.status_code == 201
    attempt1_id = sent1.json()["handoff"]["attempt_id"]

    # Новая версия текста после передачи — dept1 её видеть не должен.
    text2_id = repo.add_candidate_text(session, built["candidate_id"], text="Новая версия", redaction_method="v2").id

    # Второй отклик на другое лицо передан dept2.
    cand2 = f.make_candidate(session, "py-0510", text="Опыт: SQL, FastAPI, Docker.", is_synthetic=True)
    text3_id = repo.get_current_text(session, cand2.id).id
    app2_id = application(session, "", position="qa-manual", candidate=cand2).id
    for stage in ("screening", "phone_interview"):
        assert move(client, app2_id, stage).status_code == 201
    sent2 = move(client, app2_id, "sent_to_department", handoff=_handoff_to_user(client, app2_id, dept2.id))
    assert sent2.status_code == 201
    attempt2_id = sent2.json()["handoff"]["attempt_id"]

    # dept1 видит только своё и вносит отзыв через кабинет.
    sum1 = client.get(f"/api/v1/applications/{app1_id}/handoff-summary", headers=DEPT)
    assert sum1.status_code == 200 and sum1.json()["from_snapshot"] is True
    no_pii(sum1)
    assert client.get(f"/api/v1/applications/{app1_id}", headers=DEPT).status_code == 200
    assert client.get(f"/api/v1/candidate-texts/{text1_id}", headers=DEPT).status_code == 200
    assert error_code(client.get(f"/api/v1/candidate-texts/{text2_id}", headers=DEPT)) == "FORBIDDEN_SCOPE"
    assert error_code(client.get(f"/api/v1/candidate-texts/{text3_id}", headers=DEPT)) == "FORBIDDEN_SCOPE"
    list1 = client.get("/api/v1/handoffs", params={"contour": "training"}, headers=DEPT).json()
    assert [i["attempt_id"] for i in list1["items"]] == [attempt1_id]

    cab_fb = client.post(f"/api/v1/applications/{app1_id}/feedback", headers=DEPT, json={
        "attempt_id": attempt1_id,
        "outcome": "fit",
        "contact_status": "yes",
        "interview_status": "yes",
        "comment": "Берём на оформление",
        "request_id": str(uuid.uuid4()),
    })
    assert cab_fb.status_code == 201
    assert cab_fb.json()["feedback"]["response_channel"] == "cabinet"
    assert cab_fb.json()["feedback"]["reported_by"]["login"] == "dept_demo"
    assert client.get(f"/api/v1/handoffs/{attempt1_id}", headers=DEPT).json()["close_reason"] == "feedback:fit"

    # Исправление отзыва с fit на not_fit обновляет close_reason попытки.
    cab_fb2 = client.post(f"/api/v1/applications/{app1_id}/feedback", headers=DEPT, json={
        "attempt_id": attempt1_id,
        "supersedes_id": cab_fb.json()["feedback"]["feedback_id"],
        "outcome": "not_fit",
        "rejection_reason_code": "experience",
        "contact_status": "yes",
        "interview_status": "yes",
        "request_id": str(uuid.uuid4()),
    })
    assert cab_fb2.status_code == 201
    assert client.get(f"/api/v1/handoffs/{attempt1_id}", headers=DEPT).json()["close_reason"] == "feedback:not_fit"

    # dept2 не видит ни сводку, ни карточку, ни текст, ни отзывы, ни попытку dept1 (и несуществующий attempt_id -> 403).
    forbidden_for_dept2 = [
        ("get", f"/api/v1/applications/{app1_id}/handoff-summary", None),
        ("get", f"/api/v1/applications/{app1_id}/handoffs", None),
        ("get", f"/api/v1/applications/{app1_id}/feedback", None),
        ("get", f"/api/v1/applications/{app1_id}/feedback?attempt_id={attempt1_id}", None),
        ("get", f"/api/v1/applications/{app1_id}", None),
        ("get", f"/api/v1/candidate-texts/{text1_id}", None),
        ("get", f"/api/v1/handoffs/{attempt1_id}", None),
        ("get", f"/api/v1/handoffs/{uuid.uuid4()}", None),
        ("post", f"/api/v1/applications/{app1_id}/feedback", {
            "attempt_id": attempt1_id, "outcome": "not_fit", "rejection_reason_code": "experience",
            "request_id": str(uuid.uuid4()),
        }),
        ("post", f"/api/v1/applications/{app1_id}/feedback", {
            "attempt_id": attempt2_id, "outcome": "fit",
            "request_id": str(uuid.uuid4()),
        }),
    ]
    for method, url, payload in forbidden_for_dept2:
        res = getattr(client, method)(url, headers=DEPT2, **({"json": payload} if payload else {}))
        assert (res.status_code, error_code(res)) == (403, "FORBIDDEN_SCOPE"), url
    assert [i["attempt_id"] for i in client.get("/api/v1/handoffs", params={"contour": "training"}, headers=DEPT2).json()["items"]] == [attempt2_id]

    # Общие списки, история, воронка, перевод этапа, повторная передача и резерв закрыты для department.
    vac_id = f.vacancy(session).id
    prof_id = built["profile_id"]
    pos_id = f.position(session).id
    role_blocked = [
        ("get", "/api/v1/vacancies", None),
        ("get", f"/api/v1/vacancies/{vac_id}/applications", None),
        ("get", f"/api/v1/applications/{app1_id}/comparison?profile_id={prof_id}", None),
        ("get", f"/api/v1/applications/{app1_id}/history", None),
        ("get", "/api/v1/analytics/funnel", None),
        ("post", f"/api/v1/applications/{app1_id}/stage", {"to_stage_code": "rejected", "expected_seq": 1, "rejection_reason_code": "other"}),
        ("post", f"/api/v1/applications/{app1_id}/handoffs", {"expected_seq": 1, "handoff": {
            "recipient_name": "X", "recipient_department": "Y", "channel": "sed",
            "summary_revision": "r", "request_id": str(uuid.uuid4()),
        }}),
        ("get", f"/api/v1/positions/{pos_id}/reserve", None),
    ]
    for method, url, payload in role_blocked:
        res = getattr(client, method)(url, headers=DEPT, **({"json": payload} if payload else {}))
        assert (res.status_code, error_code(res)) == (403, "FORBIDDEN_ROLE"), url


# --- 5. Прежние записи, фильтры, контуры и ошибки ------------------------------

def test_legacy_feedback_without_attempt_and_error_cases(session, client):
    app_id = application(session, "py-0520").id
    repo.record_department_feedback(session, app_id, outcome=FeedbackOutcome.NOT_FIT,
                                    rejection_reason_code="experience", comment="Старый отзыв")
    feed = client.get(f"/api/v1/applications/{app_id}/feedback", headers=HR)
    assert feed.status_code == 200 and feed.json()["total"] == 1
    assert feed.json()["items"][0]["origin_unrecorded"] is True
    assert feed.json()["items"][0]["attempt_id"] is None

    # history / manual не допускаются к передаче и отзыву.
    ext = application(session, "py-0521", source=ApplicationSource.HISTORY).id
    man = application(session, "py-0522", source=ApplicationSource.MANUAL).id
    for bad_id in (ext, man):
        assert error_code(client.get(f"/api/v1/applications/{bad_id}/handoff-summary", headers=HR)) == "NOT_WORKING_APPLICATION"
        assert error_code(client.post(f"/api/v1/applications/{bad_id}/handoffs", headers=HR, json={
            "expected_seq": 1,
            "handoff": {"recipient_name": "X", "recipient_department": "Y", "channel": "sed",
                        "summary_revision": "r", "request_id": str(uuid.uuid4())},
        })) == "NOT_WORKING_APPLICATION"

    # Неизвестный ID -> 404.
    assert error_code(client.get(f"/api/v1/applications/{uuid.uuid4()}/handoff-summary", headers=HR)) == "APPLICATION_NOT_FOUND"
    assert error_code(client.get(f"/api/v1/handoffs/{uuid.uuid4()}", headers=HR)) == "HANDOFF_NOT_FOUND"

    # Разделение контуров и фильтр по отделу/подборщику.
    train_id = build_case(session, "C1-unknown")["application_id"]
    for stage in ("screening", "phone_interview", "sent_to_department"):
        assert move(client, train_id, stage).status_code == 201
    assert client.get("/api/v1/handoffs", headers=HR).json()["total"] == 0
    assert client.get("/api/v1/handoffs", params={"contour": "training", "actor_login": "hr_demo",
                                                    "department": "Департамент-заказчик (учебный)"}, headers=HR).json()["total"] == 1
    assert client.get("/api/v1/handoffs", params={"contour": "training", "department": "Другой"}, headers=HR).json()["total"] == 0
    assert client.get("/api/v1/analytics/funnel", params={"contour": "training", "department": "Другой"},
                      headers=HR).json()["open_waits"]["total"] == 0


# --- 6. Реальная конкурентная гонка исправлений отзыва на PostgreSQL -------------

@pytest.fixture
def committed_feedback(engine) -> Iterator[dict]:
    """Отклик, передача и первая версия отзыва, зафиксированные commit для двух параллельных потоков."""
    code = f"race-wf-{uuid.uuid4().hex[:8]}"
    with Session(engine) as session:
        app_row = application(session, code)
        for stage in ("screening", "phone_interview", "sent_to_department"):
            repo.move_application(session, app_row.id, stage, actor_user_id=_user(session, "hr_demo").id)
        attempt, _ = repo.create_handoff_attempt(
            session,
            application_id=app_row.id,
            stage_event_id=None,
            recipient_user_id=_user(session, "dept_demo").id,
            recipient_name="Руководитель",
            recipient_department="Департамент-заказчик (учебный)",
            channel="cabinet",
            handed_off_at=repo.stage_history(session, app_row.id)[-1].created_at,
            created_by_user_id=_user(session, "hr_demo").id,
            summary_revision="race-rev",
            summary_snapshot={"summary": {}, "markdown": "", "referenced_text_ids": []},
            request_id=uuid.uuid4(),
        )
        fb, _ = repo.record_handoff_feedback(
            session,
            application_id=app_row.id,
            attempt_id=attempt.id,
            outcome=FeedbackOutcome.PENDING,
            contact_status="yes",
            interview_status="not_reported",
            response_channel="cabinet",
            reported_by_user_id=_user(session, "dept_demo").id,
            reported_by_name="Руководитель",
            author_user_id=_user(session, "dept_demo").id,
            request_id=uuid.uuid4(),
        )
        ids = {
            "application_id": app_row.id,
            "candidate_id": app_row.candidate_id,
            "document_id": session.get(Candidate, app_row.candidate_id).source_document_id,
            "attempt_id": attempt.id,
            "fb1_id": fb.id,
        }
        session.commit()
    yield ids
    with Session(engine) as session:
        session.execute(delete(Candidate).where(Candidate.id == ids["candidate_id"]))
        session.execute(delete(SourceDocument).where(SourceDocument.id == ids["document_id"]))
        session.commit()


def test_concurrent_feedback_edits_on_same_supersedes_id_give_409_conflict(engine, committed_feedback):
    """Две одновременные правки одной версии отзыва: побеждает ровно одна, вторая получает 409 FEEDBACK_CONFLICT."""
    app = create_app()

    def own_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = own_session
    url = f"/api/v1/applications/{committed_feedback['application_id']}/feedback"
    barrier = threading.Barrier(2)
    results: list = [None, None]

    def send_edit(idx: int, reason_code: str):
        with TestClient(app) as http:
            barrier.wait()
            results[idx] = http.post(url, headers=DEPT, json={
                "attempt_id": str(committed_feedback["attempt_id"]),
                "supersedes_id": str(committed_feedback["fb1_id"]),
                "outcome": "not_fit",
                "rejection_reason_code": reason_code,
                "request_id": str(uuid.uuid4()),
            })

    threads = [
        threading.Thread(target=send_edit, args=(0, "experience")),
        threading.Thread(target=send_edit, args=(1, "competencies")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    loser = next(r for r in results if r.status_code == 409)
    assert error_code(loser) == "FEEDBACK_CONFLICT"
    assert loser.json()["error"]["details"]["current_revision"] == 2
    with Session(engine) as session:
        total = session.scalar(
            select(func.count()).select_from(DepartmentFeedback)
            .where(DepartmentFeedback.attempt_id == committed_feedback["attempt_id"])
        )
    assert total == 2
