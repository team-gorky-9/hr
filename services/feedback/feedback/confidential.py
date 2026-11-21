"""Named requests: explicit recipient and two-party access, independent from pulse data."""

import json
from uuid import UUID

from fastapi import APIRouter, Request

from feedback.dependencies import Context, fixed_view
from feedback.schemas import ConfidentialClose, ConfidentialCreate, ConfidentialReply
from feedback.store import check_revision, check_state, fail, new

router = APIRouter()
NOTICE = "Именное конфиденциальное обращение видят автор и выбранный адресат. Это не канал экстренной помощи."
RESPONSE_TERMS = "Учебный ориентир ответа — три рабочих дня; реальный срок устанавливает организация."


def participant(case, actor):
    return case["author_actor_id"] == actor["id"] or (
        case["recipient_actor_id"] == actor["id"] and "confidential_recipient" in actor["assignments"]
    )


def get_case(db, case_id, actor):
    row = db.execute(
        "SELECT data FROM confidential_cases WHERE id=? AND organization_id=?",
        (str(case_id), actor["organization_id"]),
    ).fetchone()
    if row is None:
        fail(404, "NOT_FOUND")
    case = json.loads(row[0])
    if not participant(case, actor):
        fail(404, "NOT_FOUND")
    return case


def save_case(db, case, actor, action, creating=False):
    if not creating:
        case["revision"] += 1
    payload = json.dumps(case, ensure_ascii=False)
    if creating:
        db.execute(
            "INSERT INTO confidential_cases VALUES(?,?,?,?,?)",
            (
                case["id"],
                case["organization_id"],
                case["author_actor_id"],
                case["recipient_actor_id"],
                payload,
            ),
        )
    else:
        db.execute("UPDATE confidential_cases SET data=? WHERE id=?", (payload, case["id"]))
    db.execute(
        "INSERT INTO confidential_history VALUES(?,?,?,?,?)",
        (case["id"], case["revision"], actor["id"], action, payload),
    )
    return case


@router.get("/confidential-recipients")
def recipients(ctx: Context):
    db, actor = ctx
    if "employee" not in actor["roles"]:
        fail(404, "NOT_FOUND")
    items = [
        {"id": row["id"], "name": row["name"]}
        for row in db.execute(
            "SELECT id,name,assignments FROM actors WHERE organization_id=? ORDER BY id",
            (actor["organization_id"],),
        )
        if "confidential_recipient" in json.loads(row["assignments"])
    ]
    return {"items": items, "notice": NOTICE, "response_terms": RESPONSE_TERMS}


@router.post("/confidential-cases", status_code=201)
def create_case(body: ConfidentialCreate, ctx: Context):
    db, actor = ctx
    if "employee" not in actor["roles"]:
        fail(404, "NOT_FOUND")
    recipient = db.execute(
        "SELECT assignments FROM actors WHERE id=? AND organization_id=?",
        (str(body.recipient_actor_id), actor["organization_id"]),
    ).fetchone()
    if recipient is None or "confidential_recipient" not in json.loads(recipient[0]):
        fail(422, "INVALID_RECIPIENT")
    if str(body.recipient_actor_id) == actor["id"]:
        fail(422, "RECIPIENT_MUST_DIFFER")
    case = new(
        actor,
        **body.model_dump(mode="json"),
        author_actor_id=actor["id"],
        status="submitted",
        reply=None,
        close_reason=None,
        notice=NOTICE,
        response_terms=RESPONSE_TERMS,
    )
    return save_case(db, case, actor, "submit", True)


@router.get("/confidential-cases")
def list_cases(request: Request, ctx: Context):
    fixed_view(request)
    db, actor = ctx
    cases = [
        json.loads(row[0])
        for row in db.execute(
            "SELECT data FROM confidential_cases WHERE organization_id=? "
            "AND (author_actor_id=? OR recipient_actor_id=?) ORDER BY id",
            (actor["organization_id"], actor["id"], actor["id"]),
        )
    ]
    return {"items": [case for case in cases if participant(case, actor)]}


@router.get("/confidential-cases/{case_id}")
def read_case(case_id: UUID, ctx: Context):
    db, actor = ctx
    case = get_case(db, case_id, actor)
    history = [
        {
            "revision": row["revision"],
            "actor_id": row["actor_id"],
            "action": row["action"],
            "snapshot": json.loads(row["snapshot"]),
        }
        for row in db.execute(
            "SELECT * FROM confidential_history WHERE case_id=? ORDER BY revision", (case["id"],)
        )
    ]
    return case | {"history": history}


@router.post("/confidential-cases/{case_id}/reply")
def reply(case_id: UUID, body: ConfidentialReply, ctx: Context):
    db, actor = ctx
    case = get_case(db, case_id, actor)
    if case["recipient_actor_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(case, body.expected_revision)
    check_state(case["status"] != "closed")
    case.update(reply=body.text, status="answered")
    return save_case(db, case, actor, "reply")


@router.post("/confidential-cases/{case_id}/close")
def close(case_id: UUID, body: ConfidentialClose, ctx: Context):
    db, actor = ctx
    case = get_case(db, case_id, actor)
    check_revision(case, body.expected_revision)
    check_state(case["status"] != "closed")
    case.update(status="closed", close_reason=body.reason)
    return save_case(db, case, actor, "close")
