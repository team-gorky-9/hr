"""Сквозные и конкурентные тесты workflow-01: сводка без ПДн, передача, ожидания,
кабинет двух получателей и версионные ответы департамента на настоящей PostgreSQL.
"""
import threading
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api import handoff as handoff_api
from app.config import settings
from app.db import repository as repo
from app.db.enums import (
    ApplicationSource,
    FeedbackOutcome,
    AnswerSource,
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
    HandoffDeadlineExtension,
    ProductionCalendarDay,
    ReserveEntry,
    SourceDocument,
    User,
)
from app.db.session import get_session
from app.main import create_app
from tests import factories as f
from tests.posting_helpers import posting_registry  # noqa: F401
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

    # Встреча, гайд и ответы — через хранение interview-01: вопросы версии гайда, ответы ревизиями.
    interview = repo.open_interview(session, app_id, InterviewKind.PHONE)
    interview.summary = f"Связались по почте {PII['email']}"
    guide, _ = repo.save_interview_guide(
        session, interview=interview, base_assessment_id=built["assessment_id"], profile_id=built["profile_id"],
        rubric_version=None, prompt_version="guide-v1", model_calls=1, uncovered_gaps=[], request_id=uuid.uuid4(),
        created_by_user_id=_user(session, "hr_demo").id,
        questions=[
            {"kind": "clarification", "sort_order": 1, "gap": "длительность коммерческого опыта",
             "gap_ref_id": "gap:experience01",
             "question": "С какого по какой месяц длился проект и в каком качестве вы работали?",
             "author": QuestionAuthor.MODEL, "sources": []},
            {"kind": "clarification", "sort_order": 2, "gap": "связь", "gap_ref_id": "gap:contact0001",
             "question": "Удобный способ связи?", "author": QuestionAuthor.HUMAN, "sources": []},
        ],
    )
    first_q, second_q = repo.guide_questions(session, guide.id)
    for question, text in ((first_q, "С 03.2023 по 12.2024 по договору, писал API-тесты"),
                           (second_q, f"Тг: @ivanov_test, {PII['full_name']}")):
        repo.add_interview_answer(session, interview_id=interview.id, question_id=question.id, text=text,
                                  source=AnswerSource.PHONE, expected_revision=0, request_id=uuid.uuid4(),
                                  author_user_id=_user(session, "hr_demo").id)
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


def test_stale_assessment_is_strictly_blocked_even_with_allow_stale(session, client):
    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    for stage in ("screening", "phone_interview"):
        assert move(client, app_id, stage).status_code == 201
    repo.add_candidate_text(session, built["candidate_id"], text="Переочищенный текст резюме.", redaction_method="v2")

    blocked = move(client, app_id, "sent_to_department")
    assert (blocked.status_code, error_code(blocked)) == (409, "ASSESSMENT_STALE")

    summary = _summary(client, app_id)
    assert summary["summary"]["assessment_status"] == "stale"
    still_blocked = move(client, app_id, "sent_to_department", handoff={
        "recipient_name": "Внешний руководитель",
        "recipient_department": "Юридический отдел",
        "channel": "email",
        "summary_revision": summary["summary_revision"],
        "request_id": str(uuid.uuid4()),
        "allow_stale": True,
    })
    assert (still_blocked.status_code, error_code(still_blocked)) == (409, "ASSESSMENT_STALE")


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


# --- 7. Срок ответа (10/7 рабочих дней), календарь РФ, просрочка и перенос ------

def test_handoff_deadline_calendar_overdue_and_late_feedback(session, client, monkeypatch):
    """Приёмка срока: 1 дек -> 15 дек (напоминание 10 дек), смена настройки не сдвигает старый срок,
    на 16 дек — просрочено и вверху очереди с ссылкой на кросс-оценки, ответ 17 дек закрывает с пометкой опоздания,
    синтетический праздник и рабочая суббота сдвигают срок."""
    clock = [datetime(2026, 12, 1, 7, 0, tzinfo=timezone.utc)]  # 10:00 МСК 01.12.2026 (вторник)
    monkeypatch.setattr(handoff_api, "_now", lambda: clock[0])

    built = build_case(session, "C1-unknown")
    app1_id, cand_id = built["application_id"], built["candidate_id"]
    dept1 = _user(session, "dept_demo")
    for stage in ("screening", "phone_interview"):
        assert move(client, app1_id, stage).status_code == 201
    sent1 = move(client, app1_id, "sent_to_department", handoff=_handoff_to_user(client, app1_id, dept1.id))
    assert sent1.status_code == 201, sent1.text
    att1 = sent1.json()["handoff"]
    att1_id = att1["attempt_id"]
    assert att1["initial_due_date"] == "2026-12-15"
    assert att1["due_date"] == "2026-12-15"
    assert att1["reminder_date"] == "2026-12-10"
    assert (att1["deadline_business_days"], att1["reminder_business_day"], att1["extensions_count"]) == (10, 7, 0)
    assert (att1["deadline_status"], att1["business_days_left"], att1["is_overdue"]) == ("on_track", 10, False)

    # Изменение настройки не сдвигает уже сохранённый срок.
    monkeypatch.setattr(settings, "handoff_feedback_deadline_business_days", 15)
    assert client.get(f"/api/v1/handoffs/{att1_id}", headers=HR).json()["due_date"] == "2026-12-15"
    monkeypatch.setattr(settings, "handoff_feedback_deadline_business_days", 10)

    # 3 декабря: ждёт ответа, 8 рабочих дней в запасе.
    clock[0] = datetime(2026, 12, 3, 9, 0, tzinfo=timezone.utc)
    d_dec3 = client.get(f"/api/v1/handoffs/{att1_id}", headers=HR).json()
    assert (d_dec3["deadline_status"], d_dec3["business_days_left"], d_dec3["is_overdue"]) == ("on_track", 8, False)

    # 10 декабря (рабочий день 7): «скоро срок», осталось 3 рабочих дня.
    clock[0] = datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc)
    d_dec10 = client.get(f"/api/v1/handoffs/{att1_id}", headers=HR).json()
    assert (d_dec10["deadline_status"], d_dec10["business_days_left"], d_dec10["is_overdue"]) == ("due_soon", 3, False)

    # 14 декабря создаём вторую свежую передачу (на ней срок 28 декабря).
    clock[0] = datetime(2026, 12, 14, 9, 0, tzinfo=timezone.utc)
    cand2 = f.make_candidate(session, "py-9020", is_synthetic=True)
    app2_id = application(session, "", position="qa-manual", candidate=cand2).id
    for stage in ("screening", "phone_interview"):
        assert move(client, app2_id, stage).status_code == 201
    sent2 = move(client, app2_id, "sent_to_department", handoff=_handoff_to_user(client, app2_id, _user(session, "dept2_demo").id))
    assert sent2.status_code == 201
    att2_id = sent2.json()["handoff"]["attempt_id"]

    # 16 декабря: первая передача просрочена (-1 раб. день), стоит первой в очереди, этап не изменился.
    clock[0] = datetime(2026, 12, 16, 9, 0, tzinfo=timezone.utc)
    queue = client.get("/api/v1/handoffs", params={"contour": "training"}, headers=HR).json()
    assert [i["attempt_id"] for i in queue["items"]] == [att1_id, att2_id]
    first = queue["items"][0]
    assert first["deadline_status"] == "overdue"
    assert first["business_days_left"] == -1
    assert first["is_overdue"] is True
    assert first["overdue_notice"] == "Департамент не ответил"
    assert first["cross_assessments_url"] == f"/api/v1/candidates/{cand_id}/cross-assessments"
    assert history(client, app1_id)["stage"]["code"] == "sent_to_department"
    assert [i["attempt_id"] for i in client.get(
        "/api/v1/handoffs", params={"contour": "training", "deadline_status": "overdue"}, headers=HR
    ).json()["items"]] == [att1_id]
    dept_queue = client.get("/api/v1/handoffs", params={"contour": "training"}, headers=DEPT).json()
    assert dept_queue["items"][0]["cross_assessments_url"] is None

    funnel = client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()
    assert (funnel["open_waits"]["total"], funnel["open_waits"]["overdue_total"]) == (2, 1)

    # 17 декабря: ответ not_fit закрывает ожидание и отмечает, что ответ пришёл после срока.
    clock[0] = datetime(2026, 12, 17, 9, 0, tzinfo=timezone.utc)
    late_fb = client.post(f"/api/v1/applications/{app1_id}/feedback", headers=HR, json={
        "attempt_id": att1_id,
        "outcome": "not_fit",
        "rejection_reason_code": "experience",
        "response_channel": "sed",
        "reported_by_name": "Руководитель",
        "request_id": str(uuid.uuid4()),
    })
    assert late_fb.status_code == 201, late_fb.text
    assert late_fb.json()["feedback"]["received_after_due"] is True
    closed_detail = client.get(f"/api/v1/handoffs/{att1_id}", headers=HR).json()
    assert closed_detail["status"] == "responded"
    assert closed_detail["deadline_status"] == "responded"
    assert closed_detail["answered_late"] is True
    assert closed_detail["response_business_days"] == 12
    assert closed_detail["business_days_left"] is None
    assert history(client, app1_id)["stage"]["code"] == "sent_to_department"

    # Проверка производственного календаря: синтетический праздник 8 дек сдвигает срок с 15 на 16 дек,
    # а добавление рабочей субботы 5 дек сдвигает на день раньше.
    clock[0] = datetime(2026, 12, 1, 7, 0, tzinfo=timezone.utc)
    session.add(ProductionCalendarDay(day=date(2026, 12, 8), is_working_day=False, title="Синтетический праздник"))
    session.flush()
    cand3 = f.make_candidate(session, "py-9021", is_synthetic=True)
    app3_id = application(session, "", position="frontend-dev", candidate=cand3).id
    for stage in ("screening", "phone_interview"):
        assert move(client, app3_id, stage).status_code == 201
    sent3 = move(client, app3_id, "sent_to_department")
    assert sent3.status_code == 201
    assert sent3.json()["handoff"]["due_date"] == "2026-12-16"
    assert sent3.json()["handoff"]["reminder_date"] == "2026-12-11"

    session.add(ProductionCalendarDay(day=date(2026, 12, 5), is_working_day=True, title="Рабочая суббота"))
    session.flush()
    cand4 = f.make_candidate(session, "py-9022", is_synthetic=True)
    app4_id = application(session, "", position="junior-ux-ui", candidate=cand4).id
    for stage in ("screening", "phone_interview"):
        assert move(client, app4_id, stage).status_code == 201
    sent4 = move(client, app4_id, "sent_to_department")
    assert sent4.status_code == 201
    assert sent4.json()["handoff"]["due_date"] == "2026-12-15"


def test_handoff_deadline_extension_history_overdue_recovery_and_race(session, engine, client, monkeypatch):
    """Перенос срока HR с причиной и историей: 9 дек -> 22 дек (напоминание 17 дек), перенос просрочки,
    запреты ввода и гонка на PostgreSQL."""
    clock = [datetime(2026, 12, 1, 7, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(handoff_api, "_now", lambda: clock[0])

    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    dept1 = _user(session, "dept_demo")
    for stage in ("screening", "phone_interview"):
        assert move(client, app_id, stage).status_code == 201
    sent = move(client, app_id, "sent_to_department", handoff=_handoff_to_user(client, app_id, dept1.id))
    assert sent.status_code == 201
    att_id = sent.json()["handoff"]["attempt_id"]
    url = f"/api/v1/applications/{app_id}/handoffs/{att_id}/deadline"

    # 9 декабря: проверка прав, валидации причины/даты и успешный перенос на 22 декабря.
    clock[0] = datetime(2026, 12, 9, 9, 0, tzinfo=timezone.utc)
    req_forbidden = client.post(url, headers=DEPT, json={
        "expected_due_date": "2026-12-15", "new_due_date": "2026-12-22",
        "reason_code": "illness", "request_id": str(uuid.uuid4()),
    })
    assert (req_forbidden.status_code, error_code(req_forbidden)) == (403, "FORBIDDEN_ROLE")

    no_comment = client.post(url, headers=HR, json={
        "expected_due_date": "2026-12-15", "new_due_date": "2026-12-22",
        "reason_code": "other", "comment": "   ", "request_id": str(uuid.uuid4()),
    })
    assert (no_comment.status_code, error_code(no_comment)) == (422, "EXTENSION_COMMENT_REQUIRED")

    earlier = client.post(url, headers=HR, json={
        "expected_due_date": "2026-12-15", "new_due_date": "2026-12-14",
        "reason_code": "illness", "request_id": str(uuid.uuid4()),
    })
    assert (earlier.status_code, error_code(earlier)) == (422, "INVALID_DEADLINE_DATE")

    ext_req_id = str(uuid.uuid4())
    ext_body = {
        "expected_due_date": "2026-12-15",
        "new_due_date": "2026-12-22",
        "reason_code": "illness",
        "comment": "Руководитель на больничном",
        "request_id": ext_req_id,
    }
    ext1 = client.post(url, headers=HR, json=ext_body)
    assert ext1.status_code == 201, ext1.text
    d1 = ext1.json()
    assert d1["created"] is True
    assert d1["attempt"]["initial_due_date"] == "2026-12-15"
    assert d1["attempt"]["due_date"] == "2026-12-22"
    assert d1["attempt"]["reminder_date"] == "2026-12-17"
    assert d1["attempt"]["extensions_count"] == 1
    assert (d1["extension"]["seq"], d1["extension"]["was_overdue"], d1["extension"]["reason_title"]) == (1, False, "Болезнь")

    # Идемпотентный повтор и конфликт повторного request_id.
    retry = client.post(url, headers=HR, json=ext_body)
    assert retry.status_code == 200 and retry.json()["created"] is False
    reused = client.post(url, headers=HR, json={**ext_body, "new_due_date": "2026-12-23"})
    assert (reused.status_code, error_code(reused)) == (409, "REQUEST_ID_REUSED")

    # 17 декабря: снова «скоро срок» за 3 рабочих дня до нового срока.
    clock[0] = datetime(2026, 12, 17, 9, 0, tzinfo=timezone.utc)
    assert (
        client.get(f"/api/v1/handoffs/{att_id}", headers=HR).json()["deadline_status"],
        client.get(f"/api/v1/handoffs/{att_id}", headers=HR).json()["business_days_left"],
    ) == ("due_soon", 3)

    # 23 декабря: после истечения перенесённого срока — просрочка; второй перенос на 30 декабря
    # возвращает ожидание в on_track, сохраняя was_overdue=True в истории.
    clock[0] = datetime(2026, 12, 23, 9, 0, tzinfo=timezone.utc)
    assert client.get(f"/api/v1/handoffs/{att_id}", headers=HR).json()["deadline_status"] == "overdue"
    ext2 = client.post(url, headers=HR, json={
        "expected_due_date": "2026-12-22",
        "new_due_date": "2026-12-30",
        "reason_code": "vacation",
        "request_id": str(uuid.uuid4()),
    })
    assert ext2.status_code == 201, ext2.text
    assert ext2.json()["attempt"]["deadline_status"] == "on_track"
    assert ext2.json()["attempt"]["extensions_count"] == 2
    assert ext2.json()["extension"]["was_overdue"] is True

    detail = client.get(f"/api/v1/handoffs/{att_id}", headers=HR).json()
    assert len(detail["deadline_extensions"]) == 2
    assert [e["previous_due_date"] for e in detail["deadline_extensions"]] == ["2026-12-15", "2026-12-22"]
    assert history(client, app_id)["stage"]["code"] == "sent_to_department"

    # Время ответа при ответе 24 декабря считается от дня передачи (1 дек -> 24 дек = 17 раб. дней), а опоздания нет.
    clock[0] = datetime(2026, 12, 24, 9, 0, tzinfo=timezone.utc)
    fb = client.post(f"/api/v1/applications/{app_id}/feedback", headers=DEPT, json={
        "attempt_id": att_id, "outcome": "fit", "request_id": str(uuid.uuid4()),
    })
    assert fb.status_code == 201
    final_detail = client.get(f"/api/v1/handoffs/{att_id}", headers=HR).json()
    assert final_detail["answered_late"] is False
    assert final_detail["response_business_days"] == 17

    # Реальная гонка двух параллельных переносов срока на PostgreSQL.
    race_code = f"race-ext-{uuid.uuid4().hex[:8]}"
    with Session(engine) as s_race:
        race_app = application(s_race, race_code)
        for st in ("screening", "phone_interview", "sent_to_department"):
            repo.move_application(s_race, race_app.id, st, actor_user_id=_user(s_race, "hr_demo").id)
        handed_dt = repo.stage_history(s_race, race_app.id)[-1].created_at
        race_att, _ = repo.create_handoff_attempt(
            s_race,
            application_id=race_app.id,
            stage_event_id=None,
            recipient_user_id=_user(s_race, "dept_demo").id,
            recipient_name="Руководитель",
            recipient_department="Департамент-заказчик (учебный)",
            channel="cabinet",
            handed_off_at=handed_dt,
            created_by_user_id=_user(s_race, "hr_demo").id,
            summary_revision="race-ext",
            summary_snapshot={"summary": {}, "markdown": "", "referenced_text_ids": []},
            request_id=uuid.uuid4(),
        )
        race_ids = {
            "application_id": race_app.id,
            "candidate_id": race_app.candidate_id,
            "document_id": s_race.get(Candidate, race_app.candidate_id).source_document_id,
            "attempt_id": race_att.id,
            "due_date": race_att.due_date,
        }
        s_race.commit()

    monkeypatch.setattr(handoff_api, "_now", lambda: handed_dt)
    race_app_http = create_app()

    def own_session():
        with Session(engine) as s_req:
            yield s_req

    race_app_http.dependency_overrides[get_session] = own_session
    barrier = threading.Barrier(2)
    race_results: list = [None, None]
    race_url = f"/api/v1/applications/{race_ids['application_id']}/handoffs/{race_ids['attempt_id']}/deadline"

    def send_ext(idx: int, days_add: int):
        with TestClient(race_app_http) as http:
            barrier.wait()
            race_results[idx] = http.post(race_url, headers=HR, json={
                "expected_due_date": race_ids["due_date"].isoformat(),
                "new_due_date": (race_ids["due_date"] + timedelta(days=days_add)).isoformat(),
                "reason_code": "illness",
                "request_id": str(uuid.uuid4()),
            })

    try:
        threads = [threading.Thread(target=send_ext, args=(0, 3)), threading.Thread(target=send_ext, args=(1, 5))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert sorted(r.status_code for r in race_results) == [201, 409], [r.text for r in race_results]
        loser = next(r for r in race_results if r.status_code == 409)
        assert error_code(loser) == "DEADLINE_CONFLICT"
        with Session(engine) as s_check:
            assert s_check.scalar(
                select(func.count()).select_from(HandoffDeadlineExtension)
                .where(HandoffDeadlineExtension.attempt_id == race_ids["attempt_id"])
            ) == 1
    finally:
        with Session(engine) as s_clean:
            s_clean.execute(delete(Candidate).where(Candidate.id == race_ids["candidate_id"]))
            s_clean.execute(delete(SourceDocument).where(SourceDocument.id == race_ids["document_id"]))
            s_clean.commit()
