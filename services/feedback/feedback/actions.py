"""Group measures and messages; no code/response joins, including for nonparticipants."""

import json
from uuid import UUID

from fastapi import APIRouter, Request

from feedback.dependencies import Context, fixed_view
from feedback.publications import publication_for_cycle
from feedback.schemas import MeasureCreate, MeasureUpdate, ParticipantMessage
from feedback.store import check_revision, check_state, fail, get, new, require_assignment, rows, save

router = APIRouter()


def manages_group(actor, group_key):
    return "organizer" in actor["assignments"] or (
        "department" in actor["roles"] and actor["group_key"] == group_key
    )


def manages_measure(actor, measure):
    return manages_group(actor, measure["group_key"]) or actor["id"] == measure["owner_actor_id"]


@router.post("/measures", status_code=201)
def create_measure(body: MeasureCreate, ctx: Context):
    db, actor = ctx
    p = get(db, "publication", body.publication_id, actor)
    if not manages_group(actor, body.group_key):
        fail(404, "NOT_FOUND")
    group = next((g for g in p["groups"] if g["key"] == body.group_key), None)
    if group is None:
        fail(422, "UNKNOWN_GROUP")
    if group["status"] != "shown" or not any(
        t["key"] == body.topic_key and t["status"] == "shown" for t in group.get("topics", [])
    ):
        fail(409, "TOPIC_NOT_PUBLISHED")
    owner = db.execute(
        "SELECT * FROM actors WHERE id=? AND organization_id=?",
        (str(body.owner_actor_id), actor["organization_id"]),
    ).fetchone()
    if owner is None or owner["group_key"] != body.group_key or "employee" not in json.loads(owner["roles"]):
        fail(422, "INVALID_OWNER")
    measure = new(actor, **body.model_dump(mode="json"), status="planned", outcome_note=None)
    return save(db, "measure", measure, actor, "create", True)


@router.patch("/measures/{measure_id}")
def update_measure(measure_id: UUID, body: MeasureUpdate, ctx: Context):
    db, actor = ctx
    measure = get(db, "measure", measure_id, actor)
    if not manages_measure(actor, measure):
        fail(404, "NOT_FOUND")
    check_revision(measure, body.expected_revision)
    transitions = {
        "planned": {"in_progress", "completed", "cancelled"},
        "in_progress": {"completed", "cancelled"},
    }
    check_state(body.status in transitions.get(measure["status"], set()))
    measure.update(status=body.status, outcome_note=body.outcome_note)
    return save(db, "measure", measure, actor, body.status)


@router.get("/measures")
def list_measures(request: Request, ctx: Context):
    fixed_view(request)
    db, actor = ctx
    return {"items": [m for m in rows(db, "measure", actor) if manages_measure(actor, m)]}


@router.post("/publications/{publication_id}/participant-message", status_code=201)
def message(publication_id: UUID, body: ParticipantMessage, ctx: Context):
    db, actor = ctx
    require_assignment(actor, "organizer")
    p = get(db, "publication", publication_id, actor)
    measures = [get(db, "measure", mid, actor) for mid in body.measure_ids]
    # The contract body has no group selector: derive one group from the selected measures.
    if len({m["group_key"] for m in measures}) != 1 or any(
        m["publication_id"] != str(publication_id) for m in measures
    ):
        fail(422, "MEASURES_MUST_SHARE_PUBLICATION_AND_GROUP")
    result = new(
        actor,
        publication_id=str(publication_id),
        cycle_id=p["cycle_id"],
        group_key=measures[0]["group_key"],
        **body.model_dump(mode="json"),
        measures=measures,
        audience="all_invited_group",
        status="published",
    )
    return save(db, "participant_message", result, actor, "publish", True)


def audience_cycle(db, cycle_id, actor):
    cycle = get(db, "cycle", cycle_id, actor)
    if "organizer" not in actor["assignments"] and (
        "employee" not in actor["roles"] or actor["group_key"] not in {g["key"] for g in cycle["groups"]}
    ):
        fail(404, "NOT_FOUND")
    return cycle


def compare(db, cycle, other_id, actor):
    other = audience_cycle(db, other_id, actor)
    current_p = publication_for_cycle(db, cycle["id"], actor)
    other_p = publication_for_cycle(db, other["id"], actor)
    reasons = []
    if (cycle["question_version"], cycle["questions"], cycle["topic_options"]) != (
        other["question_version"],
        other["questions"],
        other["topic_options"],
    ):
        reasons.append("QUESTIONS_DIFFER")
    if cycle["groups"] != other["groups"]:
        reasons.append("GROUPS_DIFFER")
    if not current_p or not other_p:
        reasons.append("PUBLICATION_PENDING")
    elif (current_p["policy"], current_p["policy_version"]) != (other_p["policy"], other_p["policy_version"]):
        reasons.append("POLICY_DIFFERS")
    return {
        "cycle_id": other["id"],
        "comparable": not reasons,
        "reasons": reasons,
        "notice": "Совпадение методики не доказывает эффект меры; состав группы мог измениться.",
    }


@router.get("/cycles/{cycle_id}/outcome")
def outcome(cycle_id: UUID, request: Request, ctx: Context, compare_cycle_id: UUID | None = None):
    if set(request.query_params) - {"compare_cycle_id"}:
        fail(422, "UNSUPPORTED_FILTER")
    db, actor = ctx
    cycle = audience_cycle(db, cycle_id, actor)
    messages = [
        m
        for m in rows(db, "participant_message", actor)
        if m["cycle_id"] == str(cycle_id)
        and ("organizer" in actor["assignments"] or m["group_key"] == actor["group_key"])
    ]
    return {
        "cycle_id": str(cycle_id),
        "messages": messages,
        "comparison": compare(db, cycle, compare_cycle_id, actor) if compare_cycle_id else None,
        "notice": "Завершение меры не доказывает влияние на настроение или текучесть.",
    }
