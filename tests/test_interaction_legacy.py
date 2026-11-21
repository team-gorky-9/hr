"""One isolated interaction scenario; no services or destructive database fixture."""
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


@compiles(UUID, "sqlite")
def _uuid_sqlite(_type, _compiler, **_kw):
    # SQLite's UUID affinity is numeric: digit-only fixture UUIDs otherwise become floats.
    return "CHAR(32)"


@contextmanager
def legacy_scenario(monkeypatch):
    """Reusable real legacy routes over an isolated synthetic in-memory database."""
    from app.api.errors import install_error_handlers
    from app.api.interaction import install_gateway, router
    from app.api.routes import router as legacy_router
    from app.db.models import (
        Application, Candidate, DepartmentFeedback, FeedbackReview, FeedbackReviewItem,
        HandoffAttempt, SelectionStage, StageEvent, User, RejectionReason, CandidateText,
    )
    from app.db.session import get_session

    monkeypatch.setenv("INTERACTION_GATEWAY_KEY", "test-gateway-secret")
    monkeypatch.setenv("INTERACTION_ORGANIZATION_ID", "training-org")
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (User, Candidate, CandidateText, SelectionStage, RejectionReason, Application, StageEvent, HandoffAttempt,
                  DepartmentFeedback, FeedbackReview, FeedbackReviewItem):
        model.__table__.create(engine)

    def sqlite_identity(_mapper, connection, target):
        if target.seq is None:
            target.seq = (connection.scalar(select(func.max(StageEvent.seq))) or 0) + 1

    # Only substitutes PostgreSQL's Identity sequence; domain operations stay real.
    event.listen(StageEvent, "before_insert", sqlite_identity)
    with Session(engine, expire_on_commit=False) as session:
        hr = User(login="hr", full_name="HR", role="hr")
        dept = User(login="dept", full_name="Dept", role="department")
        candidate = Candidate(code="synthetic-1", source_document_id=uuid.uuid4(), is_synthetic=True)
        session.add_all([hr, dept, candidate,
            SelectionStage(code="sent_to_department", title="Sent", sort_order=3, is_final=False),
            SelectionStage(code="department_interview", title="Interview", sort_order=4, is_final=False)])
        session.flush()
        application = Application(candidate_id=candidate.id, external_position_title="Test", source="response", current_stage_code="sent_to_department")
        session.add(application)
        session.flush()
        session.add(StageEvent(seq=1, application_id=application.id, to_stage_code="sent_to_department"))
        text_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        attempts = [HandoffAttempt(application_id=application.id, recipient_user_id=dept.id,
            recipient_name="Dept", recipient_department="Unit", channel="cabinet", handed_off_at=now,
            initial_due_date=date.today(), due_date=date.today(), reminder_date=date.today(),
            summary_revision="1", summary_snapshot={"referenced_text_ids": [str(text_id)]}) for _ in range(2)]
        session.add_all(attempts)
        session.flush()
        session.add(CandidateText(id=text_id, candidate_id=candidate.id, version=1, is_current=True,
                                  redaction_method="synthetic", text="Synthetic candidate text"))
        session.commit()
        app = FastAPI()
        install_error_handlers(app)
        install_gateway(app)
        app.include_router(router)
        app.include_router(legacy_router)
        app.dependency_overrides[get_session] = lambda: session
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, app=app, session=session, hr=hr, dept=dept,
                                  application=application, attempts=attempts, text_id=text_id)
    event.remove(StageEvent, "before_insert", sqlite_identity)
    engine.dispose()


def test_review_revision_revocation_and_bounded_source(monkeypatch):
    from app.api import handoff
    from app.api.errors import ApiError
    from app.db import repository as repo
    from app.db.models import FeedbackReview, StageEvent

    with legacy_scenario(monkeypatch) as scenario:
            client, session = scenario.client, scenario.session
            hr, dept = scenario.hr, scenario.dept
            application, attempts, text_id = scenario.application, scenario.attempts, scenario.text_id
            path = "/api/v1/interaction-source"
            headers = {"X-Interaction-Gateway-Key": "test-gateway-secret", "X-User-Login": "hr", "X-Interaction-User-Id": str(hr.id)}
            dept_headers = {**headers, "X-User-Login": "dept", "X-Interaction-User-Id": str(dept.id)}
            assert client.get(path).status_code == 403
            assert client.get("/api/v1/health").status_code == 403
            feedback_path = f"/api/v1/applications/{application.id}/feedback"
            result = client.post(feedback_path, headers=dept_headers,
                json={"attempt_id": str(attempts[0].id), "outcome": "fit", "request_id": str(uuid.uuid4())})
            assert result.status_code == 201, result.text
            feedback = result.json()["feedback"]
            assert attempts[0].status == "responded" and attempts[1].status == "awaiting_response"
            first = client.get(path, headers=headers, params={"page_size": 1}).json()
            assert len(first["items"]) == 1 and first["next_cursor"]
            assert first["gateway_enforced"] is True
            assert client.get(path, headers={**headers, "X-User-Login": "dept", "X-Interaction-User-Id": str(dept.id)}, params={"cursor": first["next_cursor"]}).status_code == 422
            body = {"feedbacks": [{"attempt_id": str(attempts[0].id), "feedback_id": feedback["feedback_id"], "revision": 1}],
                    "expected_seq": 1, "request_id": str(uuid.uuid4()), "result": "continue_waiting"}
            review_path = f"/api/v1/applications/{application.id}/feedback-reviews"
            reviewed = client.post(review_path, json=body, headers=headers)
            assert reviewed.status_code == 200, reviewed.text
            assert client.post(review_path, json=body, headers=headers).json() == reviewed.json()
            assert client.post(review_path, json={**body, "basis": "different"}, headers=headers).status_code == 409
            correction = client.post(feedback_path, headers=dept_headers, json={"attempt_id": str(attempts[0].id),
                "supersedes_id": feedback["feedback_id"], "outcome": "pending", "request_id": str(uuid.uuid4())})
            assert correction.status_code == 201, correction.text
            assert client.post(review_path, json={**body, "request_id": str(uuid.uuid4())}, headers=headers).status_code == 409
            assert client.get(path, headers=headers, params={"relation": "needs_my_action"}).json()["items"]
            stage_review = {**body, "feedbacks": [{"attempt_id": str(attempts[0].id),
                "feedback_id": correction.json()["feedback"]["feedback_id"], "revision": 2}],
                "request_id": str(uuid.uuid4()), "result": "stage_changed",
                "stage": {"to_stage_code": "department_interview", "expected_seq": 1}}
            stale = {**stage_review, "expected_seq": 0, "stage": {**stage_review["stage"], "expected_seq": 0}}
            assert client.post(review_path, json=stale, headers=headers).status_code == 409
            assert session.scalar(select(func.count()).select_from(FeedbackReview)) == 1
            assert session.scalar(select(func.count()).select_from(StageEvent)) == 1
            moved = client.post(review_path, json=stage_review, headers=headers)
            assert moved.status_code == 200, moved.text
            assert moved.json()["stage_event_id"]
            assert application.current_stage_code == "department_interview"
            assert attempts[1].status == "awaiting_response"
            assert client.post(review_path, json=stage_review, headers=headers).json() == moved.json()
            revoke = {"expected_assignment_revision": 1, "request_id": str(uuid.uuid4()), "reason": "Reassigned"}
            revoke_path = f"/api/v1/handoffs/{attempts[0].id}/revoke-access"
            response = client.post(revoke_path, json=revoke, headers=headers)
            assert response.status_code == 200, response.text
            assert client.post(revoke_path, json=revoke, headers=headers).json() == response.json()
            assert attempts[0].status == "awaiting_response"  # Revocation never closes the wait.
            with pytest.raises(ApiError) as denied:
                handoff.get_handoff_detail(session, attempts[0].id, dept)
            assert denied.value.status_code == 403
            assert client.post(feedback_path, headers=dept_headers, json={"attempt_id": str(attempts[0].id),
                "outcome": "fit", "request_id": str(uuid.uuid4())}).status_code == 403
            assert client.get(feedback_path, headers=dept_headers, params={"attempt_id": str(attempts[0].id)}).status_code == 403
            assert repo.has_department_application_access(session, dept.id, application.id)
            assert repo.has_department_text_access(session, dept.id, text_id)
            client.post(f"/api/v1/handoffs/{attempts[1].id}/revoke-access", json={**revoke, "request_id": str(uuid.uuid4())}, headers=headers)
            assert not repo.has_department_application_access(session, dept.id, application.id)
            assert not repo.has_department_text_access(session, dept.id, text_id)
