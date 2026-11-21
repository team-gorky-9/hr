"""Permission-filtered, bounded source read for the interaction window.

No Portal.view/history calls: SQL selects only the fields the projection needs.
The request and its append-only events remain the authoritative state.
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from hiring.domain import iso
from hiring.errors import Problem, forbidden
from hiring.models import CandidateRequest as Request, CandidateRequestEvent as Event
from hiring.models import CandidateRequestMessage as Message, now

SOURCE = "hiring.portal"
RELATIONS = {"needs_my_action", "waiting_on_other", "completed", "information"}
TERMINAL = ("closed", "withdrawn")


def _cursor_payload(cursor, context, secret):
    try:
        encoded, signature = cursor.split(".")
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature")
        data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if data["context"] != context:
            raise ValueError("context")
        return datetime.fromisoformat(data["created_at"]), UUID(data["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise Problem(422, "INVALID_CURSOR", "Restart the source page for this session and filter", "cursor") from exc


def _encode_cursor(row, context, secret):
    data = {"context": context, "created_at": iso(row.created_at), "id": str(row.id)}
    encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
    return encoded + "." + hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()


def read_portal_source(session, actor, settings, *, relation=None, subject_id=None, cursor=None, page_size=25):
    if not actor.is_candidate() and not actor.is_hr():
        raise forbidden()
    if relation is not None and relation not in RELATIONS:
        raise Problem(422, "VALIDATION_ERROR", "Unknown interaction relation", "relation")
    if not 1 <= page_size <= 100:
        raise Problem(422, "VALIDATION_ERROR", "page_size must be between 1 and 100", "page_size")
    if subject_id is not None:
        try:
            subject_id = UUID(str(subject_id))
        except ValueError as exc:
            raise Problem(422, "VALIDATION_ERROR", "subject_id must be a UUID", "subject_id") from exc
    secret = settings.interaction_cursor_secret
    if not secret:
        raise Problem(503, "SOURCE_UNAVAILABLE", "Interaction cursor configuration is unavailable")
    hr = actor.is_hr()
    context = {"source": SOURCE, "issuer": getattr(settings, "auth_mode", "fixture"),
               "actor": str(actor.actor_id), "org": str(actor.organization_id),
               "grants": sorted((g.role, g.scope_type, str(g.scope_id)) for g in actor.grants),
               "relation": relation, "subject": str(subject_id) if subject_id else None,
               "order": "created_at,id:asc:v1", "page_size": page_size, "contour": "training"}
    # JSON converts tuples to lists; normalize before comparing the signed context.
    context = json.loads(json.dumps(context))
    last_sequence = select(func.max(Event.sequence)).where(Event.request_id == Request.id).scalar_subquery()
    occurred = (select(Event.created_at).where(Event.request_id == Request.id, Event.event_type != "message.read")
                .order_by(Event.sequence.desc()).limit(1).scalar_subquery())
    candidate_read = (select(Message.read_at).where(Message.request_id == Request.id,
                                                  Message.kind == "information_request")
                      .order_by(Message.created_at.desc(), Message.id.desc()).limit(1).scalar_subquery())
    fields = [Request.id, Request.status, Request.revision, Request.created_at,
              Request.information_request["event_sequence"].as_integer().label("question_sequence"),
              Request.information_request["answered"].as_boolean().label("answered"),
              Request.information_request["requested_at"].as_string().label("requested_at"),
              last_sequence.label("sequence"), occurred.label("occurred_at")]
    if hr:
        fields += [Request.consideration["application_ref"].label("application_ref"),
                   candidate_read.label("candidate_read_at")]
    query = select(*fields).where(Request.organization_id == actor.organization_id)
    query = query.where(Request.status != "draft" if hr else Request.author_actor_id == actor.actor_id)
    if subject_id:
        query = query.where(Request.id == subject_id)
    mine = ("submitted", "ready") if hr else ("draft", "needs_information")
    waiting = ("needs_information", "forwarded") if hr else ("submitted", "ready", "forwarded")
    if relation:
        statuses = {"needs_my_action": mine, "waiting_on_other": waiting, "completed": TERMINAL,
                    "information": ()}[relation]
        query = query.where(Request.status.in_(statuses))
    if cursor:
        created_at, last_id = _cursor_payload(cursor, context, secret)
        query = query.where(or_(Request.created_at > created_at,
                                and_(Request.created_at == created_at, Request.id > last_id)))
    rows = session.execute(query.order_by(Request.created_at, Request.id).limit(page_size + 1)).all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    observed_at = iso(now())
    return {"source": SOURCE, "status": "ok", "observed_at": observed_at, "source_as_of": None,
            "next_cursor": _encode_cursor(rows[-1], context, secret) if has_more else None,
            "coverage": "page" if has_more or cursor else "complete", "error_code": None,
            "items": [_item(row, actor, hr, observed_at) for row in rows]}


def _item(row, actor, hr, observed_at):
    request_id = str(row.id)
    subject = {"source": SOURCE, "kind": "candidate_request", "id": request_id}
    qref = ({"request_id": request_id, "event_sequence": row.question_sequence}
            if row.question_sequence is not None else None)
    unknown_basis = row.requested_at is not None and qref is None
    version = {"request_revision": row.revision, "sequence": row.sequence}
    required = {"expected_revision": row.revision}
    org_queue = {"kind": "role_scope", "role": "hr", "organization_id": str(actor.organization_id)}
    responsible = org_queue
    reason = row.status
    actions = []

    def action(code, extra=None, available=True):
        actions.append({"code": code, "target": subject, "required_version": required | (extra or {}),
                        "availability": "available" if available else "unavailable",
                        "reason_code": None if available else "basis_unknown"})

    if row.status in TERMINAL:
        relation = "completed"
        title, next_step = "Обращение завершено", "Посмотреть опубликованный результат"
        responsible = {"kind": "self"}
    elif row.status == "draft":
        relation = "needs_my_action"
        title, next_step = "Черновик обращения", "Проверить и подать обращение"
        responsible = {"kind": "self"}
        action("submit")
    elif row.status == "needs_information":
        relation = "waiting_on_other" if hr else "needs_my_action"
        title, next_step = "Нужны дополнительные сведения", "Ждать дополнение кандидата" if hr else "Ответить дополнением"
        reason = "awaiting_candidate_addendum"
        responsible = {"kind": "external", "role": "candidate"} if hr else {"kind": "self"}
        if not hr:
            action("addendum", {"information_request_ref": qref}, available=qref is not None)
    elif row.status == "submitted":
        relation = "needs_my_action" if hr else "waiting_on_other"
        reason = "addendum_requires_review" if row.answered else "submission_requires_review"
        title = "Проверить дополнение" if row.answered else "Проверить обращение"
        next_step = "Проверить достаточность сведений" if hr else "Дождаться проверки HR"
        if hr:
            action("ready")
            action("information_request")
    elif row.status == "ready":
        relation = "needs_my_action" if hr else "waiting_on_other"
        title, next_step = "Обращение готово к рассмотрению", "Зафиксировать регистрацию рассмотрения" if hr else "Дождаться регистрации рассмотрения"
        if hr:
            action("record_consideration")
            action("publish_outcome")
    else:  # forwarded: no inferred progress in the other system
        relation = "waiting_on_other"
        title, next_step = "Обращение на рассмотрении", "Дождаться опубликованного результата"
        responsible = {"kind": "external", "source": "legacy"} if hr else org_queue
        if hr:
            action("publish_outcome")
    if unknown_basis:
        reason = "basis_unknown"
    item = {"key": f"{SOURCE}:{actor.organization_id}:training:candidate_request:{request_id}:q:{row.question_sequence or 'none'}",
            "subject_ref": subject, "related_ref": None, "expectation_ref": qref,
            "relation": relation, "state": row.status, "reason_code": reason, "responsible": responsible,
            "title": title, "next_step": next_step, "due_on": None, "basis_ref": qref,
            "source_version": version, "occurred_at": iso(row.occurred_at), "observed_at": observed_at,
            "actions": actions}
    if hr:
        # Only the explicit manual link is exposed; identity_basis and all private text stay in the owner.
        if row.application_ref:
            item["related_ref"] = {"source": "legacy", "kind": "application",
                                   "id": row.application_ref["id"], "instance": row.application_ref["system"]}
        item["candidate_read_at"] = iso(row.candidate_read_at)
    return item
