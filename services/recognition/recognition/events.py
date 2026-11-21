from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from recognition.campaigns import Consent
from recognition.dependencies import Context, Cursor, Limit
from recognition.schemas import Input, Revision, Text, WithReason
from recognition.store import (
    check_revision,
    check_state,
    fail,
    get,
    history,
    new,
    page,
    require_assignment,
    require_employee,
    rows,
    save,
)

router = APIRouter()
RESERVED = ("confirmed", "awaiting_reconfirmation")


class EventCreate(Input):
    title: Text
    description: Text
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: Text
    capacity: int = Field(ge=1, le=100000, strict=True)

    @model_validator(mode="after")
    def period(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class EventEdit(WithReason):
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: Text | None = None


class EventFinish(WithReason):
    outcome: Literal["completed", "cancelled"]


class RegistrationCreate(Input):
    participants_count: int = Field(ge=1, le=100000, strict=True)
    child_age_bands: list[Literal["0-3", "4-6", "7-12", "13-17"]] = Field(
        default_factory=list, max_length=100
    )

    @model_validator(mode="after")
    def family_count(self):
        if len(self.child_age_bands) >= self.participants_count:
            raise ValueError("At least one adult participant is required")
        return self


class CancelRegistration(Revision):
    reason: Text | None = None


class EventView(BaseModel):
    id: UUID
    organization_id: UUID
    organizer_id: UUID
    title: str
    description: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: str
    capacity: int
    status: Literal["draft", "open", "cancelled", "completed"]
    revision: int
    created_at: str
    updated_at: str
    available_places: int
    change_reason: str | None = None
    finish_reason: str | None = None
    history: list[dict] | None = None


class RegistrationView(BaseModel):
    id: UUID
    event_id: UUID
    actor_id: UUID
    participants_count: int
    child_age_bands: list[str]
    status: Literal["confirmed", "waiting", "awaiting_reconfirmation", "cancelled"]
    agreed_event_revision: int
    revision: int
    created_at: str
    updated_at: str
    cancellation_reason: str | None = None
    history: list[dict] | None = None


class EventPage(BaseModel):
    items: list[EventView]
    next_cursor: UUID | None


class RegistrationPage(BaseModel):
    items: list[RegistrationView]
    next_cursor: UUID | None


def registrations(db, event, actor):
    return [r for r in rows(db, "registration", actor) if r["event_id"] == event["id"]]


def seats(db, event):
    # Called within the same database write transaction as register/offer/edit.
    used = db.execute(
        "SELECT COALESCE(SUM(json_extract(data,'$.participants_count')),0) FROM records "
        "WHERE kind='registration' AND parent_id=? AND status IN ('confirmed','awaiting_reconfirmation')",
        (event["id"],),
    ).fetchone()[0]
    return event["capacity"] - used


def event_visible(event, actor):
    if event["status"] == "draft" and event["organizer_id"] != actor["id"]:
        fail(404, "NOT_FOUND")


def event_view(db, event):
    return {**event, "available_places": seats(db, event) if event["status"] == "open" else 0}


def owned_event(db, actor, event_id, expected):
    event = get(db, "event", event_id, actor)
    if event["organizer_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(event, expected)
    return event


def manages_list(event, actor):
    return event["organizer_id"] == actor["id"]


def registration_access(db, actor, record_id):
    record = get(db, "registration", record_id, actor)
    event = get(db, "event", record["event_id"], actor)
    if record["actor_id"] != actor["id"] and not manages_list(event, actor):
        fail(404, "NOT_FOUND")
    return record, event


@router.post("/events", status_code=201, response_model=EventView, response_model_exclude_none=True)
def create(body: EventCreate, ctx: Context):
    db, actor = ctx
    require_assignment(actor, "organizer")
    event = new(actor, **body.model_dump(mode="json"), organizer_id=actor["id"], status="draft")
    save(db, "event", event, actor, "create", creating=True)
    return event_view(db, event)


@router.post("/events/{event_id}/open", response_model=EventView, response_model_exclude_none=True)
def open_event(event_id: UUID, body: Revision, ctx: Context):
    db, actor = ctx
    event = owned_event(db, actor, event_id, body.expected_revision)
    check_state(event["status"] == "draft")
    event["status"] = "open"
    save(db, "event", event, actor, "open")
    return event_view(db, event)


@router.get("/events", response_model=EventPage, response_model_exclude_none=True)
def list_events(ctx: Context, limit: Limit = 30, cursor: Cursor = None):
    db, actor = ctx
    return page(
        [
            event_view(db, event)
            for event in rows(db, "event", actor)
            if event["status"] != "draft" or event["organizer_id"] == actor["id"]
        ],
        limit,
        cursor,
    )


@router.get("/events/{event_id}", response_model=EventView, response_model_exclude_none=True)
def read(event_id: UUID, ctx: Context):
    db, actor = ctx
    event = get(db, "event", event_id, actor)
    event_visible(event, actor)
    result = event_view(db, event)
    if event["organizer_id"] == actor["id"]:
        result["history"] = history(db, event)
    return result


@router.post(
    "/events/{event_id}/registrations",
    status_code=201,
    response_model=RegistrationView,
    response_model_exclude_none=True,
)
def register(event_id: UUID, body: RegistrationCreate, ctx: Context):
    db, actor = ctx
    require_employee(actor)
    event = get(db, "event", event_id, actor)
    event_visible(event, actor)
    check_state(event["status"] == "open")
    if any(
        r["actor_id"] == actor["id"] and r["status"] != "cancelled" for r in registrations(db, event, actor)
    ):
        fail(409, "ACTIVE_REGISTRATION_EXISTS")
    record = new(
        actor,
        event_id=event["id"],
        actor_id=actor["id"],
        **body.model_dump(),
        agreed_event_revision=event["revision"],
        status="confirmed" if seats(db, event) >= body.participants_count else "waiting",
    )
    return save(db, "registration", record, actor, "register", creating=True)


@router.get(
    "/events/{event_id}/registrations", response_model=RegistrationPage, response_model_exclude_none=True
)
def list_registrations(event_id: UUID, ctx: Context, limit: Limit = 30, cursor: Cursor = None):
    db, actor = ctx
    event = get(db, "event", event_id, actor)
    event_visible(event, actor)
    return page(
        [
            r
            for r in registrations(db, event, actor)
            if r["actor_id"] == actor["id"] or manages_list(event, actor)
        ],
        limit,
        cursor,
    )


@router.get("/registrations/{record_id}", response_model=RegistrationView, response_model_exclude_none=True)
def read_registration(record_id: UUID, ctx: Context):
    db, actor = ctx
    record, _ = registration_access(db, actor, record_id)
    return {**record, "history": history(db, record)}


@router.post(
    "/registrations/{record_id}/cancel", response_model=RegistrationView, response_model_exclude_none=True
)
def cancel(record_id: UUID, body: CancelRegistration, ctx: Context):
    db, actor = ctx
    record, event = registration_access(db, actor, record_id)
    if record["actor_id"] != actor["id"]:
        if event["organizer_id"] != actor["id"]:
            fail(404, "NOT_FOUND")
        if not body.reason:
            fail(422, "REASON_REQUIRED")
    check_revision(record, body.expected_revision)
    check_state(event["status"] == "open" and record["status"] != "cancelled")
    record.update(status="cancelled", cancellation_reason=body.reason)
    return save(db, "registration", record, actor, "cancel")


@router.post(
    "/registrations/{record_id}/offer", response_model=RegistrationView, response_model_exclude_none=True
)
def offer(record_id: UUID, body: Revision, ctx: Context):
    db, actor = ctx
    record, event = registration_access(db, actor, record_id)
    if event["organizer_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(record, body.expected_revision)
    check_state(event["status"] == "open" and record["status"] == "waiting")
    if seats(db, event) < record["participants_count"]:
        fail(409, "INSUFFICIENT_CAPACITY")
    record["status"] = "awaiting_reconfirmation"
    return save(db, "registration", record, actor, "offer")


@router.post(
    "/registrations/{record_id}/reconfirm", response_model=RegistrationView, response_model_exclude_none=True
)
def reconfirm(record_id: UUID, body: Consent, ctx: Context):
    db, actor = ctx
    record, event = registration_access(db, actor, record_id)
    if record["actor_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(record, body.expected_revision)
    check_state(event["status"] == "open" and record["status"] == "awaiting_reconfirmation")
    record["status"] = "confirmed" if body.accepted else "cancelled"
    if body.accepted:
        record["agreed_event_revision"] = event["revision"]
    return save(db, "registration", record, actor, "reconfirm")


@router.patch("/events/{event_id}", response_model=EventView, response_model_exclude_none=True)
def edit(event_id: UUID, body: EventEdit, ctx: Context):
    db, actor = ctx
    event = owned_event(db, actor, event_id, body.expected_revision)
    check_state(event["status"] in ("draft", "open"))
    fields = body.model_dump(mode="json", exclude_unset=True)
    changes = {k: v for k, v in fields.items() if k in ("starts_at", "ends_at", "location")}
    if not changes or any(v is None for v in changes.values()):
        fail(422, "CHANGES_REQUIRED")
    candidate = {**event, **changes}
    if datetime.fromisoformat(candidate["ends_at"]) <= datetime.fromisoformat(candidate["starts_at"]):
        fail(422, "INVALID_PERIOD")
    if all(event[k] == v for k, v in changes.items()):
        fail(422, "CHANGES_REQUIRED")
    event.update(**changes, change_reason=body.reason)
    save(db, "event", event, actor, "reschedule")
    for record in registrations(db, event, actor):
        if record["status"] in RESERVED:
            # Preserve seats and previous agreement; invalidate responses to the previous offer.
            record["status"] = "awaiting_reconfirmation"
            save(db, "registration", record, actor, "event_changed")
    return event_view(db, event)


@router.post("/events/{event_id}/finish", response_model=EventView, response_model_exclude_none=True)
def finish(event_id: UUID, body: EventFinish, ctx: Context):
    db, actor = ctx
    event = owned_event(db, actor, event_id, body.expected_revision)
    check_state(event["status"] == "open")
    event.update(status=body.outcome, finish_reason=body.reason)
    save(db, "event", event, actor, "finish")
    if body.outcome == "cancelled":
        for record in registrations(db, event, actor):
            if record["status"] != "cancelled":
                record.update(status="cancelled", cancellation_reason=body.reason)
                save(db, "registration", record, actor, "event_cancelled")
    return event_view(db, event)
