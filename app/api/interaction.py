"""Legacy-owned interaction expectations and commands (training contour only).

The gateway authenticates the upstream actor; this service still resolves the
active legacy user and enforces assignment and role permissions independently.
"""
import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import String, and_, case, cast, exists, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.api import workflow
from app.api.auth import AuthenticatedUser, StaffUser
from app.api.errors import ApiError, error_body
from app.api.schemas import StageMoveIn
from app.db.enums import ApplicationSource, HandoffStatus, UserRole
from app.db import repository as repo
from app.db.models import (
    Application, Candidate, CandidateText, DepartmentFeedback, FeedbackReview, FeedbackReviewItem,
    HandoffAttempt, StageEvent, User,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["interaction"])
SessionDep = Annotated[Session, Depends(get_session)]
Relation = Literal["needs_my_action", "waiting_on_other", "completed", "information"]


def install_gateway(app: FastAPI) -> None:
    """Protect the whole legacy listener, including old optional-user routes."""
    key = os.getenv("INTERACTION_GATEWAY_KEY", "")
    app.state.interaction_gateway_key = key

    @app.middleware("http")
    async def gateway_guard(request: Request, call_next):
        if key and not hmac.compare_digest(request.headers.get("x-interaction-gateway-key", ""), key):
            return JSONResponse(error_body("GATEWAY_REQUIRED", "Доступ разрешён через шлюз взаимодействия"), status_code=403)
        return await call_next(request)


def _scope(request: Request, user: User) -> dict:
    key = getattr(request.app.state, "interaction_gateway_key", "")
    organization_id = os.getenv("INTERACTION_ORGANIZATION_ID", "").strip()
    if not key or not organization_id:
        raise ApiError(503, "INTERACTION_NOT_CONFIGURED", "Источник взаимодействия не настроен")
    if not hmac.compare_digest(request.headers.get("x-interaction-gateway-key", ""), key):
        raise ApiError(403, "GATEWAY_REQUIRED", "Доступ разрешён через шлюз взаимодействия")
    return {"source": "legacy", "actor": {"user_id": str(user.id), "login": user.login, "role": str(user.role)},
            "organization_id": organization_id,
            "instance_id": os.getenv("INTERACTION_INSTANCE_ID", "training-legacy"),
            "contour": "training", "gateway_enforced": True}


@router.get("/interaction-session")
def interaction_session(request: Request, session: SessionDep, user: AuthenticatedUser,
                        target_kind: Literal["application", "handoff", "candidate_text"] | None = None,
                        target_id: uuid.UUID | None = None):
    scope = _scope(request, user)
    if (target_kind is None) != (target_id is None):
        raise ApiError(422, "TARGET_REQUIRED", "Укажите вид и идентификатор объекта")
    if target_kind:
        allowed = False
        if target_kind == "candidate_text":
            allowed = session.scalar(select(CandidateText.id).join(Candidate, Candidate.id == CandidateText.candidate_id)
                .where(CandidateText.id == target_id, Candidate.is_synthetic.is_(True))) is not None
            if user.role == UserRole.DEPARTMENT:
                allowed = allowed and repo.has_department_text_access(session, user.id, target_id)
        else:
            application_id = target_id
            if target_kind == "handoff":
                attempt = session.get(HandoffAttempt, target_id)
                application_id = attempt.application_id if attempt else None
                if user.role == UserRole.DEPARTMENT and (attempt is None or attempt.recipient_user_id != user.id or attempt.access_revoked_at):
                    application_id = None
            if application_id:
                allowed = session.scalar(select(Application.id).join(Candidate, Candidate.id == Application.candidate_id)
                    .where(Application.id == application_id, Candidate.is_synthetic.is_(True),
                           Application.source == ApplicationSource.RESPONSE)) is not None
                if user.role == UserRole.DEPARTMENT:
                    allowed = allowed and repo.has_department_application_access(session, user.id, application_id)
        if not allowed:
            raise ApiError(403, "FORBIDDEN_SCOPE", "Объект недоступен в учебном контуре")
    return scope


class FeedbackReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: uuid.UUID
    feedback_id: uuid.UUID
    revision: int = Field(ge=1)


class FeedbackReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedbacks: list[FeedbackReference] = Field(min_length=1, max_length=100)
    expected_seq: int = Field(ge=0)
    request_id: uuid.UUID
    basis: str | None = Field(default=None, max_length=4000)
    result: Literal["continue_waiting", "stage_changed"]
    stage: StageMoveIn | None = None

    @model_validator(mode="after")
    def validate_result(self):
        if (self.result == "stage_changed") != (self.stage is not None):
            raise ValueError("stage is required only for stage_changed")
        if self.stage and self.stage.expected_seq != self.expected_seq:
            raise ValueError("stage.expected_seq must match expected_seq")
        if len({ref.attempt_id for ref in self.feedbacks}) != len(self.feedbacks):
            raise ValueError("select one current revision per attempt")
        return self


class RevokeAccessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_assignment_revision: int = Field(ge=1)
    request_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=4000)


def _training_application(session: Session, application_id: uuid.UUID) -> Application:
    application = session.scalar(select(Application).join(Candidate, Candidate.id == Application.candidate_id)
        .where(Application.id == application_id, Candidate.is_synthetic.is_(True),
               Application.source == ApplicationSource.RESPONSE).with_for_update(of=Application))
    if application is None:
        raise ApiError(404, "APPLICATION_NOT_FOUND", "Учебный отклик не найден")
    # A long-lived Session may already contain the unlocked object.
    session.refresh(application, with_for_update=True)
    return application


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _review_out(review: FeedbackReview) -> dict:
    return {"review_id": str(review.id), "application_id": str(review.application_id),
            "feedbacks": review.request_payload["feedbacks"], "reviewer_user_id": str(review.reviewer_user_id),
            "created_at": _utc(review.created_at), "basis": review.basis, "request_id": str(review.request_id),
            "result": review.result, "checked_seq": review.checked_seq,
            "stage_event_id": str(review.stage_event_id) if review.stage_event_id else None}


@router.post("/applications/{application_id}/feedback-reviews")
def review_feedback(application_id: uuid.UUID, body: FeedbackReviewIn, request: Request,
                    session: SessionDep, user: StaffUser):
    _scope(request, user)
    application = _training_application(session, application_id)
    payload = body.model_dump(mode="json")
    previous = session.scalar(select(FeedbackReview).where(FeedbackReview.request_id == body.request_id))
    if previous is not None:
        if previous.application_id != application.id or previous.reviewer_user_id != user.id or previous.request_payload != payload:
            raise ApiError(409, "REQUEST_ID_REUSED", "request_id уже использован для другого решения")
        return _review_out(previous)
    seq = workflow.last_seq(session, application.id) or 0
    if seq != body.expected_seq:
        raise ApiError(409, "STALE_STAGE_FORM", "Этап отклика изменился", {"last_seq": seq})
    # Serialize against writes and revocations, with one stable lock order.
    for ref in sorted(body.feedbacks, key=lambda ref: str(ref.attempt_id)):
        attempt = session.get(HandoffAttempt, ref.attempt_id, with_for_update=True, populate_existing=True)
        if attempt is None or attempt.application_id != application.id:
            raise ApiError(422, "ATTEMPT_OF_OTHER_APPLICATION", "Передача не относится к отклику")
        current = session.scalar(select(DepartmentFeedback).where(DepartmentFeedback.attempt_id == attempt.id)
                                 .order_by(DepartmentFeedback.revision.desc()).limit(1))
        if current is None or current.id != ref.feedback_id or current.revision != ref.revision:
            raise ApiError(409, "STALE_FEEDBACK_REVIEW", "Отзыв изменился: откройте актуальную версию")
    stage_event_id = None
    if body.stage:
        moved, _ = workflow.move_stage(session, application.id, body.stage, user, commit=False)
        stage_event_id = session.scalar(select(StageEvent.id).where(
            StageEvent.application_id == application.id, StageEvent.seq == moved.event.seq))
    review = FeedbackReview(application_id=application.id, reviewer_user_id=user.id, basis=body.basis,
        request_id=body.request_id, request_payload=payload, result=body.result,
        checked_seq=seq, stage_event_id=stage_event_id)
    try:
        session.add(review)
        session.flush()
        session.add_all([FeedbackReviewItem(review_id=review.id, feedback_id=ref.feedback_id,
            attempt_id=ref.attempt_id, revision=ref.revision) for ref in body.feedbacks])
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(409, "REQUEST_ID_REUSED", "request_id уже использован") from exc
    return _review_out(review)


def _revocation_out(attempt: HandoffAttempt) -> dict:
    return {"attempt_id": str(attempt.id), "application_id": str(attempt.application_id),
            "assignment_revision": attempt.assignment_revision, "access_revoked_at": _utc(attempt.access_revoked_at),
            "access_revoked_by_user_id": str(attempt.access_revoked_by_user_id),
            "access_revocation_reason": attempt.access_revocation_reason,
            "request_id": str(attempt.revoke_request_id)}


@router.post("/handoffs/{attempt_id}/revoke-access")
def revoke_access(attempt_id: uuid.UUID, body: RevokeAccessIn, request: Request,
                  session: SessionDep, user: StaffUser):
    _scope(request, user)
    attempt = session.get(HandoffAttempt, attempt_id)
    if attempt is None:
        raise ApiError(404, "HANDOFF_NOT_FOUND", "Передача не найдена")
    _training_application(session, attempt.application_id)
    session.refresh(attempt, with_for_update=True)
    payload = body.model_dump(mode="json")
    previous = session.scalar(select(HandoffAttempt).where(HandoffAttempt.revoke_request_id == body.request_id))
    if previous is not None:
        if previous.id != attempt.id or previous.access_revoked_by_user_id != user.id or previous.revoke_request_payload != payload:
            raise ApiError(409, "REQUEST_ID_REUSED", "request_id уже использован для другого отзыва доступа")
        return _revocation_out(previous)
    if attempt.assignment_revision != body.expected_assignment_revision or attempt.access_revoked_at is not None:
        raise ApiError(409, "STALE_ASSIGNMENT", "Назначение изменилось", {"assignment_revision": attempt.assignment_revision})
    if not body.reason.strip():
        raise ApiError(422, "REASON_REQUIRED", "Укажите причину отзыва доступа")
    attempt.access_revoked_at = datetime.now(timezone.utc)
    attempt.access_revoked_by_user_id = user.id
    attempt.access_revocation_reason = body.reason.strip()
    attempt.revoke_request_id = body.request_id
    attempt.revoke_request_payload = payload
    attempt.assignment_revision += 1
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(409, "REQUEST_ID_REUSED", "request_id уже использован") from exc
    return _revocation_out(attempt)


def _cursor_encode(payload: dict, key: str) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + "." + signature


def _cursor_decode(cursor: str, binding: dict, key: str) -> tuple[str, str]:
    try:
        encoded, signature = cursor.split(".")
        expected = hmac.new(key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["binding"] != binding:
            raise ValueError("scope")
        return payload["kind"], payload["id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiError(422, "INVALID_CURSOR", "Курсор не соответствует пользователю или фильтрам") from exc


@router.get("/interaction-source")
def interaction_source(request: Request, session: SessionDep, user: AuthenticatedUser,
                       relation: Relation | None = None, subject_id: uuid.UUID | None = None,
                       cursor: str | None = Query(default=None, max_length=4096),
                       page_size: int = Query(default=30, ge=1, le=100)):
    scope = _scope(request, user)
    is_department = user.role == UserRole.DEPARTMENT
    pending = HandoffAttempt.status == HandoffStatus.AWAITING_RESPONSE
    if is_department:
        attempt_relation = case((pending, "needs_my_action"), else_="completed")
    else:
        attempt_relation = case((and_(pending, HandoffAttempt.access_revoked_at.is_not(None)), "needs_my_action"),
                                (pending, "waiting_on_other"), else_="completed")
    reviewed = exists(select(FeedbackReviewItem.review_id).where(
        FeedbackReviewItem.feedback_id == DepartmentFeedback.id,
        FeedbackReviewItem.revision == DepartmentFeedback.revision))
    feedback_relation = literal("completed") if is_department else case((reviewed, "completed"), else_="needs_my_action")
    newer = aliased(DepartmentFeedback)
    latest_feedback = ~exists(select(newer.id).where(newer.attempt_id == DepartmentFeedback.attempt_id,
                                                    newer.revision > DepartmentFeedback.revision))
    stage_seq = select(func.max(StageEvent.seq)).where(StageEvent.application_id == Application.id).correlate(Application).scalar_subquery()
    review_query = select(FeedbackReview.id).join(FeedbackReviewItem, FeedbackReviewItem.review_id == FeedbackReview.id).where(
        FeedbackReviewItem.feedback_id == DepartmentFeedback.id,
        FeedbackReviewItem.revision == DepartmentFeedback.revision).order_by(FeedbackReview.created_at.desc(), FeedbackReview.id.desc()).limit(1).correlate(DepartmentFeedback)
    review_id = review_query.scalar_subquery()
    review_at = review_query.with_only_columns(FeedbackReview.created_at).scalar_subquery()

    def common(kind, expectation_id, feedback_id, revision, item_relation, *, feedback=False):
        return select(literal(kind).label("kind"), cast(expectation_id, String).label("expectation_id"),
            Application.id.label("application_id"), HandoffAttempt.id.label("attempt_id"),
            feedback_id.label("feedback_id"), revision.label("revision"),
            HandoffAttempt.assignment_revision, item_relation.label("relation"), HandoffAttempt.due_date,
            HandoffAttempt.recipient_user_id, HandoffAttempt.access_revoked_at,
            cast(HandoffAttempt.status, String).label("handoff_status"), HandoffAttempt.close_reason,
            HandoffAttempt.stage_event_id, HandoffAttempt.closed_by_stage_event_id,
            (review_id if feedback else literal(None)).label("review_id"),
            (cast(DepartmentFeedback.outcome, String) if feedback else literal(None)).label("feedback_outcome"),
            (func.coalesce(review_at, DepartmentFeedback.received_at) if feedback else
                func.coalesce(HandoffAttempt.access_revoked_at, HandoffAttempt.closed_at, HandoffAttempt.handed_off_at)).label("occurred_at"),
            stage_seq.label("stage_seq"))

    attempts = common("handoff", HandoffAttempt.id, literal(None), literal(None), attempt_relation).select_from(HandoffAttempt)
    feedbacks = common("feedback", DepartmentFeedback.id, cast(DepartmentFeedback.id, String), DepartmentFeedback.revision,
                       feedback_relation, feedback=True).select_from(DepartmentFeedback).join(HandoffAttempt, HandoffAttempt.id == DepartmentFeedback.attempt_id).where(latest_feedback)

    def restrict(statement):
        statement = statement.join(Application, Application.id == HandoffAttempt.application_id).join(Candidate, Candidate.id == Application.candidate_id)
        statement = statement.where(Candidate.is_synthetic.is_(True), Application.source == ApplicationSource.RESPONSE)
        if is_department:
            statement = statement.where(HandoffAttempt.recipient_user_id == user.id, HandoffAttempt.access_revoked_at.is_(None))
        if subject_id:
            statement = statement.where(Application.id == subject_id)
        return statement

    source = union_all(restrict(attempts), restrict(feedbacks)).subquery()
    query = select(source)
    if relation:
        query = query.where(source.c.relation == relation)
    binding = {"actor": str(user.id), "role": str(user.role), "organization": scope["organization_id"],
               "instance": scope["instance_id"], "contour": "training", "relation": relation,
               "subject_id": str(subject_id) if subject_id else None, "order": "kind-id-v1"}
    key = request.app.state.interaction_gateway_key
    if cursor:
        kind, after_id = _cursor_decode(cursor, binding, key)
        query = query.where(or_(source.c.kind > kind, and_(source.c.kind == kind, source.c.expectation_id > after_id)))
    rows = session.execute(query.order_by(source.c.kind, source.c.expectation_id).limit(page_size + 1)).mappings().all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = _cursor_encode({"binding": binding, "kind": rows[-1]["kind"], "id": rows[-1]["expectation_id"]}, key) if has_more else None
    items = []
    now = datetime.now(timezone.utc)
    for row in rows:
        app_id, attempt_id = str(row["application_id"]), str(row["attempt_id"])
        feedback_id = str(uuid.UUID(row["feedback_id"])) if row["feedback_id"] else None
        current_review_id = str(uuid.UUID(str(row["review_id"]))) if row["review_id"] else None
        expectation = {"source": "legacy", "kind": row["kind"], "type": row["kind"], "id": feedback_id or attempt_id, "attempt_id": attempt_id}
        if feedback_id:
            expectation.update(feedback_id=feedback_id, revision=row["revision"])
        version = {"expected_seq": row["stage_seq"] or 0, "assignment_revision": row["assignment_revision"]}
        if feedback_id:
            version.update(feedback_id=feedback_id, revision=row["revision"])
        version.update(attempt_id=attempt_id, stage_seq=row["stage_seq"] or 0,
                       review_id=current_review_id)
        target = {"source": "legacy", "kind": "application", "id": app_id,
                  "application_id": app_id, "attempt_id": attempt_id}
        actions = []
        if row["relation"] == "needs_my_action":
            code = "record_feedback" if is_department else "review_feedback" if feedback_id else "resolve_revoked_handoff"
            actions.append({"code": code, "target": target, "required_version": version,
                            "availability": "available", "reason_code": None})
        elif not is_department and row["kind"] == "handoff" and row["access_revoked_at"] is None:
            actions.append({"code": "revoke_access", "target": {**target, "kind": "handoff", "id": attempt_id},
                            "required_version": version, "availability": "available", "reason_code": None})
        if feedback_id:
            state = row["feedback_outcome"]
            reason_code = "feedback_review_confirmed" if row["review_id"] else "review_unconfirmed"
            basis_ref = {"source": "legacy", "kind": "feedback_review" if row["review_id"] else "feedback",
                         "id": current_review_id or feedback_id}
        else:
            state = row["handoff_status"]
            reason_code = "assignment_revoked" if row["access_revoked_at"] and state == "awaiting_response" else {
                "awaiting_response": "awaiting_department_response", "responded": "department_response_received",
                "closed_without_response": "handoff_closed_without_response"}.get(state, "handoff_recorded")
            # Only known machine reasons escape the source; never copy a free-text reason.
            close_reason = row["close_reason"] or ""
            if close_reason.startswith("stage_moved:") and row["closed_by_stage_event_id"]:
                reason_code = "handoff_closed_by_stage"
            event_id = row["closed_by_stage_event_id"] or row["stage_event_id"]
            basis_ref = {"source": "legacy", "kind": "stage_event" if event_id else "handoff",
                         "id": str(event_id) if event_id else attempt_id}
        if feedback_id or row["access_revoked_at"]:
            responsible = {"kind": "role_scope", "role": "hr", "organization_id": scope["organization_id"]}
        elif not row["recipient_user_id"]:
            responsible = {"kind": "external", "role": "department"}
        elif row["recipient_user_id"] == user.id:
            responsible = {"kind": "self", "role": "department"}
        else:
            responsible = {"kind": "actor", "role": "department",
                           "actor_ref": {"source": "legacy", "kind": "user", "id": str(row["recipient_user_id"])}}
        key_parts = ["legacy", scope["organization_id"], scope["instance_id"], "training", row["kind"], app_id, expectation["id"]]
        if feedback_id:
            key_parts.append(str(row["revision"]))
        items.append({"key": ":".join(key_parts),
            "source": "legacy", "kind": row["kind"], "relation": row["relation"],
            "state": state, "reason_code": reason_code, "source_version": version,
            "basis_ref": basis_ref, "occurred_at": _utc(row["occurred_at"]), "observed_at": now,
            "subject_ref": {"source": "legacy", "kind": "application", "type": "application", "id": app_id},
            "related_ref": None, "expectation_ref": expectation, "responsible": responsible,
            "title": "Отзыв департамента" if feedback_id else "Передача в департамент",
            "next_step": "Рассмотреть актуальный отзыв" if feedback_id and row["relation"] == "needs_my_action" else
                         "Принять решение по передаче после отзыва доступа" if row["access_revoked_at"] else
                         "Отправить ответ" if is_department and row["relation"] == "needs_my_action" else "Открыть отклик",
            "due_on": row["due_date"], "basis": {"version": version}, "actions": actions,
            "organization_id": scope["organization_id"], "instance_id": scope["instance_id"], "contour": "training"})
    coverage = "page" if cursor or next_cursor else "complete"
    descriptor = {"source": "legacy", "status": "ok", "observed_at": now, "source_as_of": None,
                  "next_cursor": next_cursor, "coverage": coverage, "error": None}
    return {**scope, "items": items, "source": descriptor, "observed_at": now,
            "next_cursor": next_cursor, "coverage": coverage}
