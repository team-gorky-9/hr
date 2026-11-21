from typing import Literal
from uuid import UUID

from fastapi import APIRouter

from recognition import schemas as s
from recognition.dependencies import Context, Cursor, Limit
from recognition.store import (
    check_revision,
    check_state,
    fail,
    get,
    history,
    new,
    page,
    peer,
    require_employee,
    rows,
    save,
)

router = APIRouter()


def public_view(record):
    return {
        key: record[key]
        for key in (
            "id",
            "organization_id",
            "author_id",
            "recipient_id",
            "text",
            "revision",
            "status",
            "created_at",
            "updated_at",
        )
    }


def view(db, record, actor):
    participant = actor["id"] in (record["author_id"], record["recipient_id"])
    if participant:
        return {**record, "history": history(db, record)}
    if record["status"] == "published":
        return public_view(record)
    if (
        record["status"] != "withdrawn"
        and record["recipient_choice"] == "organization"
        and "moderator" in actor["assignments"]
    ):
        # Only the submitted current edition; previous private editions remain private.
        return record
    fail(404, "NOT_FOUND")


@router.post("/thanks", status_code=201, response_model=s.ThanksView, response_model_exclude_none=True)
def create(body: s.ThanksCreate, ctx: Context):
    db, actor = ctx
    require_employee(actor)
    peer(db, actor, body.recipient_id, "employee")
    if str(body.recipient_id) == actor["id"]:
        fail(422, "SELF_THANKS")
    record = new(
        actor,
        **body.model_dump(mode="json"),
        author_id=actor["id"],
        recipient_choice="pending",
        moderation_status="pending",
        moderation_reason=None,
        status="pending",
    )
    save(db, "thanks", record, actor, "create", creating=True)
    return view(db, record, actor)


@router.get("/thanks", response_model=s.ThanksPage, response_model_exclude_none=True)
def listing(
    ctx: Context, view: Literal["mine", "received", "wall", "moderation"] = "mine", limit: Limit = 30, cursor: Cursor = None
):
    db, actor = ctx
    items = [
        r
        for r in rows(db, "thanks", actor)
        if (view == "mine" and r["author_id"] == actor["id"])
        or (view == "received" and r["recipient_id"] == actor["id"])
        or (view == "wall" and r["status"] == "published")
        or (view == "moderation" and "moderator" in actor["assignments"]
            and r["status"] != "withdrawn" and r["recipient_choice"] == "organization")
    ]
    # Lists never expose the historical snapshots.
    return page([public_view(r) for r in items] if view == "wall" else items, limit, cursor)


@router.get("/thanks/{record_id}", response_model=s.ThanksView, response_model_exclude_none=True)
def read(record_id: UUID, ctx: Context):
    db, actor = ctx
    return view(db, get(db, "thanks", record_id, actor), actor)


def editable(ctx, record_id, expected, allowed):
    db, actor = ctx
    record = get(db, "thanks", record_id, actor)
    if actor["id"] not in [record[key] for key in allowed]:
        fail(404, "NOT_FOUND")
    check_revision(record, expected)
    check_state(record["status"] != "withdrawn")
    return db, actor, record


@router.patch("/thanks/{record_id}", response_model=s.ThanksView, response_model_exclude_none=True)
def edit(record_id: UUID, body: s.ThanksEdit, ctx: Context):
    db, actor, record = editable(ctx, record_id, body.expected_revision, ["author_id"])
    record.update(
        text=body.text,
        recipient_choice="pending",
        moderation_status="pending",
        moderation_reason=None,
        status="pending",
    )
    save(db, "thanks", record, actor, "edit")
    return view(db, record, actor)


@router.post("/thanks/{record_id}/visibility", response_model=s.ThanksView, response_model_exclude_none=True)
def visibility(record_id: UUID, body: s.Visibility, ctx: Context):
    db, actor, record = editable(ctx, record_id, body.expected_revision, ["recipient_id"])
    record.update(
        recipient_choice=body.choice,
        moderation_status="pending",
        moderation_reason=None,
        status="private" if body.choice == "private" else "pending",
    )
    save(db, "thanks", record, actor, "visibility")
    return view(db, record, actor)


@router.post("/thanks/{record_id}/moderation", response_model=s.ThanksView, response_model_exclude_none=True)
def moderation(record_id: UUID, body: s.Moderation, ctx: Context):
    db, actor = ctx
    record = get(db, "thanks", record_id, actor)
    if "moderator" not in actor["assignments"] or record["recipient_choice"] != "organization":
        fail(404, "NOT_FOUND")
    check_revision(record, body.expected_revision)
    check_state(record["status"] == "pending" and record["moderation_status"] == "pending")
    if actor["id"] in (record["author_id"], record["recipient_id"]):
        fail(409, "CONFLICT_OF_INTEREST")
    if body.result == "returned" and not body.reason:
        fail(422, "REASON_REQUIRED")
    record.update(
        moderation_status=body.result,
        moderation_reason=body.reason,
        status="published" if body.result == "approved" else "pending",
    )
    save(db, "thanks", record, actor, "moderation")
    return record


@router.post("/thanks/{record_id}/withdraw", response_model=s.ThanksView, response_model_exclude_none=True)
def withdraw(record_id: UUID, body: s.WithReason, ctx: Context):
    db, actor, record = editable(ctx, record_id, body.expected_revision, ["author_id", "recipient_id"])
    record.update(status="withdrawn", withdrawal_reason=body.reason)
    save(db, "thanks", record, actor, "withdraw")
    return view(db, record, actor)


@router.get("/session")
def session(ctx: Context):
    _, actor = ctx
    return {key: actor[key] for key in ("id", "name", "roles", "assignments")}


@router.get("/colleagues")
def colleagues(ctx: Context):
    import json
    db, actor = ctx
    require_employee(actor)
    return {"items": [
        {"id": row["id"], "name": row["name"]}
        for row in db.execute("SELECT id,name,roles FROM actors WHERE organization_id=? ORDER BY name",
                              (actor["organization_id"],))
        if "employee" in json.loads(row["roles"])
    ]}
