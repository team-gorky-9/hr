from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

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
    peer,
    require_assignment,
    require_employee,
    rows,
    save,
)

router = APIRouter()


class CampaignCreate(Input):
    title: Text
    criteria: Text
    starts_on: date
    ends_on: date
    reviewer_actor_id: UUID

    @model_validator(mode="after")
    def period(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must not precede starts_on")
        return self


class ReplaceReviewer(WithReason):
    reviewer_actor_id: UUID


class NominationCreate(Input):
    nominee_id: UUID
    statement: Text


class Consent(Revision):
    accepted: bool = Field(strict=True)


class Decision(WithReason):
    result: Literal["selected", "not_selected"]


class Publication(Revision):
    allowed: bool = Field(strict=True)


class CampaignView(BaseModel):
    id: UUID
    organization_id: UUID
    organizer_id: UUID
    title: str
    criteria: str
    starts_on: date
    ends_on: date
    reviewer_actor_id: UUID
    status: Literal["draft", "open", "closed"]
    revision: int
    created_at: str
    updated_at: str
    history: list[dict] | None = None


class NominationView(BaseModel):
    id: UUID
    campaign_id: UUID
    author_id: UUID
    nominee_id: UUID
    statement: str
    revision: int
    status: Literal["awaiting_consent", "submitted", "declined", "selected", "not_selected"]
    decision_reason: str | None = None
    publication_choice: Literal["pending", "allowed", "denied"]
    created_at: str
    updated_at: str
    history: list[dict] | None = None


class CampaignPage(BaseModel):
    items: list[CampaignView]
    next_cursor: UUID | None


class ResultView(BaseModel):
    id: UUID
    nominee_id: UUID
    campaign_id: UUID
    status: Literal["selected"]
    revision: int


class ResultPage(BaseModel):
    items: list[ResultView]
    next_cursor: UUID | None


def campaign_readable(record, actor):
    if record["status"] == "draft" and record["organizer_id"] != actor["id"]:
        fail(404, "NOT_FOUND")


def campaign_owned(db, actor, record_id, expected):
    record = get(db, "campaign", record_id, actor)
    if record["organizer_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(record, expected)
    return record


@router.post("/campaigns", status_code=201, response_model=CampaignView, response_model_exclude_none=True)
def create(body: CampaignCreate, ctx: Context):
    db, actor = ctx
    require_assignment(actor, "organizer")
    peer(db, actor, body.reviewer_actor_id)
    record = new(actor, **body.model_dump(mode="json"), organizer_id=actor["id"], status="draft")
    return save(db, "campaign", record, actor, "create", creating=True)


@router.post("/campaigns/{record_id}/open", response_model=CampaignView, response_model_exclude_none=True)
def open_campaign(record_id: UUID, body: Revision, ctx: Context):
    db, actor = ctx
    record = campaign_owned(db, actor, record_id, body.expected_revision)
    check_state(record["status"] == "draft")
    record["status"] = "open"
    return save(db, "campaign", record, actor, "open")


@router.patch("/campaigns/{record_id}", response_model=CampaignView, response_model_exclude_none=True)
def replace_reviewer(record_id: UUID, body: ReplaceReviewer, ctx: Context):
    db, actor = ctx
    record = campaign_owned(db, actor, record_id, body.expected_revision)
    check_state(record["status"] in ("draft", "open"))
    peer(db, actor, body.reviewer_actor_id)
    record.update(reviewer_actor_id=str(body.reviewer_actor_id), replacement_reason=body.reason)
    return save(db, "campaign", record, actor, "replace_reviewer")


@router.get("/campaigns", response_model=CampaignPage, response_model_exclude_none=True)
def campaigns(ctx: Context, limit: Limit = 30, cursor: Cursor = None):
    db, actor = ctx
    return page(
        [
            r
            for r in rows(db, "campaign", actor)
            if r["status"] != "draft" or r["organizer_id"] == actor["id"]
        ],
        limit,
        cursor,
    )


@router.get("/campaigns/{record_id}", response_model=CampaignView, response_model_exclude_none=True)
def read_campaign(record_id: UUID, ctx: Context):
    db, actor = ctx
    record = get(db, "campaign", record_id, actor)
    campaign_readable(record, actor)
    if record["organizer_id"] == actor["id"]:
        record["history"] = history(db, record)
    return record


@router.post(
    "/campaigns/{record_id}/nominations",
    status_code=201,
    response_model=NominationView,
    response_model_exclude_none=True,
)
def nominate(record_id: UUID, body: NominationCreate, ctx: Context):
    db, actor = ctx
    require_employee(actor)
    campaign = get(db, "campaign", record_id, actor)
    campaign_readable(campaign, actor)
    # Campaign dates use the product's Moscow civil day, independent of the host TZ.
    today = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
    check_state(campaign["status"] == "open" and campaign["starts_on"] <= today <= campaign["ends_on"])
    peer(db, actor, body.nominee_id, "employee")
    if str(body.nominee_id) == actor["id"]:
        fail(422, "SELF_NOMINATION")
    record = new(
        actor,
        campaign_id=campaign["id"],
        campaign_revision=campaign["revision"],
        author_id=actor["id"],
        **body.model_dump(mode="json"),
        status="awaiting_consent",
        decision_reason=None,
        publication_choice="pending",
    )
    return save(db, "nomination", record, actor, "nominate", creating=True)


def nomination_access(db, actor, record_id):
    record = get(db, "nomination", record_id, actor)
    campaign = get(db, "campaign", record["campaign_id"], actor)
    if actor["id"] not in (record["author_id"], record["nominee_id"], campaign["reviewer_actor_id"]):
        fail(404, "NOT_FOUND")
    return record, campaign


@router.get("/nominations/{record_id}", response_model=NominationView, response_model_exclude_none=True)
def read_nomination(record_id: UUID, ctx: Context):
    db, actor = ctx
    record, _ = nomination_access(db, actor, record_id)
    return {**record, "history": history(db, record)}


@router.post(
    "/nominations/{record_id}/consent", response_model=NominationView, response_model_exclude_none=True
)
def consent(record_id: UUID, body: Consent, ctx: Context):
    db, actor = ctx
    record, _ = nomination_access(db, actor, record_id)
    if record["nominee_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(record, body.expected_revision)
    check_state(record["status"] == "awaiting_consent")
    record["status"] = "submitted" if body.accepted else "declined"
    return save(db, "nomination", record, actor, "consent")


@router.post(
    "/nominations/{record_id}/decision", response_model=NominationView, response_model_exclude_none=True
)
def decision(record_id: UUID, body: Decision, ctx: Context):
    db, actor = ctx
    record, campaign = nomination_access(db, actor, record_id)
    if campaign["reviewer_actor_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(record, body.expected_revision)
    check_state(record["status"] == "submitted")
    if actor["id"] in (record["author_id"], record["nominee_id"]):
        fail(409, "CONFLICT_OF_INTEREST")
    record.update(status=body.result, decision_reason=body.reason, decision_actor_id=actor["id"])
    return save(db, "nomination", record, actor, "decision")


@router.post(
    "/nominations/{record_id}/publication", response_model=NominationView, response_model_exclude_none=True
)
def publication(record_id: UUID, body: Publication, ctx: Context):
    db, actor = ctx
    record, _ = nomination_access(db, actor, record_id)
    if record["nominee_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(record, body.expected_revision)
    check_state(record["status"] == "selected")
    record["publication_choice"] = "allowed" if body.allowed else "denied"
    return save(db, "nomination", record, actor, "publication")


@router.get("/campaigns/{record_id}/results", response_model=ResultPage)
def results(record_id: UUID, ctx: Context, limit: Limit = 30, cursor: Cursor = None):
    db, actor = ctx
    campaign = get(db, "campaign", record_id, actor)
    campaign_readable(campaign, actor)
    items = [
        {key: r[key] for key in ("id", "campaign_id", "nominee_id", "status", "revision")}
        for r in rows(db, "nomination", actor)
        if r["campaign_id"] == campaign["id"]
        and r["status"] == "selected"
        and r["publication_choice"] == "allowed"
    ]
    return page(items, limit, cursor)


@router.get("/nominations")
def list_nominations(ctx: Context, limit: Limit = 30, cursor: Cursor = None):
    db, actor = ctx
    campaigns = {c["id"]: c for c in rows(db, "campaign", actor)}
    return page([
        r for r in rows(db, "nomination", actor)
        if actor["id"] in (r["author_id"], r["nominee_id"],
                           campaigns[r["campaign_id"]]["reviewer_actor_id"])
    ], limit, cursor)
