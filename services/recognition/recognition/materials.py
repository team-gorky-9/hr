from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field, HttpUrl, model_validator

from recognition.dependencies import Context, Cursor, Limit
from recognition.schemas import Input, Revision, Text, WithReason
from recognition.store import check_revision, check_state, fail, get, history, new, page, peer, rows, save

router = APIRouter()


class Audience(Input):
    kind: Literal["organization", "actors"]
    actor_ids: list[UUID] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def scope(self):
        if (self.kind == "organization" and self.actor_ids) or (self.kind == "actors" and not self.actor_ids):
            raise ValueError("actors requires IDs; organization must not contain IDs")
        if len(set(self.actor_ids)) != len(self.actor_ids):
            raise ValueError("Duplicate audience actor")
        return self


class MaterialCreate(Input):
    title: Text
    description: Text
    url: HttpUrl
    version: int = Field(ge=1, strict=True)
    audience_scope: Audience
    distribution_basis: Text
    supersedes_id: UUID | None = None


class MaterialView(BaseModel):
    id: UUID
    title: str
    description: str
    url: str | None = None
    version: int
    status: Literal["draft", "published", "withdrawn"]
    author_actor_id: UUID
    revision: int
    created_at: str
    updated_at: str
    supersedes_id: UUID | None = None
    audience_scope: Audience | None = None
    distribution_basis: str | None = None
    withdrawal_reason: str | None = None
    history: list[dict] | None = None


class MaterialPage(BaseModel):
    items: list[MaterialView]
    next_cursor: UUID | None


def allowed(record, actor):
    scope = record["audience_scope"]
    return scope["kind"] == "organization" or actor["id"] in scope["actor_ids"]


def view(db, record, actor, include_history=False):
    if record["author_actor_id"] == actor["id"]:
        return {**record, **({"history": history(db, record)} if include_history else {})}
    if record["status"] == "draft" or not allowed(record, actor):
        fail(404, "NOT_FOUND")
    # Audience membership, publication basis and old URLs are not reader data.
    result = {
        k: record[k]
        for k in (
            "id",
            "title",
            "description",
            "version",
            "status",
            "author_actor_id",
            "revision",
            "created_at",
            "updated_at",
        )
    }
    if record["status"] == "published":
        result["url"] = record["url"]
    else:
        result["withdrawal_reason"] = record["withdrawal_reason"]
    return result


@router.post("/materials", status_code=201, response_model=MaterialView, response_model_exclude_none=True)
def create(body: MaterialCreate, ctx: Context):
    db, actor = ctx
    if not {"organizer", "publisher"}.intersection(actor["assignments"]):
        fail(404, "NOT_FOUND")
    for actor_id in body.audience_scope.actor_ids:
        peer(db, actor, actor_id)
    if body.supersedes_id:
        previous = get(db, "material", body.supersedes_id, actor)
        if previous["author_actor_id"] != actor["id"]:
            fail(404, "NOT_FOUND")
        if body.version != previous["version"] + 1:
            fail(422, "INVALID_VERSION")
        if any(r.get("supersedes_id") == str(body.supersedes_id) for r in rows(db, "material", actor)):
            fail(409, "VERSION_ALREADY_EXISTS")
    elif body.version != 1:
        fail(422, "FIRST_VERSION_MUST_BE_ONE")
    record = new(actor, **body.model_dump(mode="json"), author_actor_id=actor["id"], status="draft")
    return save(db, "material", record, actor, "create", creating=True)


def owned(db, actor, record_id, expected):
    record = get(db, "material", record_id, actor)
    if record["author_actor_id"] != actor["id"]:
        fail(404, "NOT_FOUND")
    check_revision(record, expected)
    return record


@router.post("/materials/{record_id}/publish", response_model=MaterialView, response_model_exclude_none=True)
def publish(record_id: UUID, body: Revision, ctx: Context):
    db, actor = ctx
    record = owned(db, actor, record_id, body.expected_revision)
    check_state(record["status"] == "draft")
    # Nonempty distribution_basis is required at creation and persisted in this version.
    record["status"] = "published"
    return save(db, "material", record, actor, "publish")


@router.post("/materials/{record_id}/withdraw", response_model=MaterialView, response_model_exclude_none=True)
def withdraw(record_id: UUID, body: WithReason, ctx: Context):
    db, actor = ctx
    record = owned(db, actor, record_id, body.expected_revision)
    check_state(record["status"] == "published")
    record.update(status="withdrawn", withdrawal_reason=body.reason)
    return save(db, "material", record, actor, "withdraw")


@router.get("/materials/{record_id}", response_model=MaterialView, response_model_exclude_none=True)
def read(record_id: UUID, ctx: Context):
    db, actor = ctx
    return view(db, get(db, "material", record_id, actor), actor, include_history=True)


@router.get("/materials", response_model=MaterialPage, response_model_exclude_none=True)
def listing(ctx: Context, limit: Limit = 30, cursor: Cursor = None):
    db, actor = ctx
    items = [
        view(db, r, actor)
        for r in rows(db, "material", actor)
        if r["author_actor_id"] == actor["id"] or (r["status"] == "published" and allowed(r, actor))
    ]
    return page(items, limit, cursor)
