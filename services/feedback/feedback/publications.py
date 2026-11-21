"""Freeze one table. Only safe cells are persisted in the publication, never hidden counts."""

import json
from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Request

from feedback.dependencies import Context, fixed_view
from feedback.schemas import PublicationCreate
from feedback.store import check_revision, check_state, fail, get, new, require_assignment, rows, save

router = APIRouter()


def publication_for_cycle(db, cycle_id, actor):
    return next((p for p in rows(db, "publication", actor) if p["cycle_id"] == str(cycle_id)), None)


def distribution(keys, counts, k, key_field):
    # Hide the ENTIRE distribution if any cell is small. Revealing the other cells
    # plus a row total would let the reader recover one suppressed value by subtraction.
    hidden = any(counts[key] < k for key in keys)
    return [
        {key_field: key, "status": "suppressed"}
        if hidden
        else {key_field: key, "status": "shown", "count": counts[key]}
        for key in keys
    ]


def table(db, cycle, k):
    groups = []
    for group in cycle["groups"]:
        answers = list(
            db.execute(
                "SELECT answers,topic_key FROM responses WHERE cycle_id=? AND group_key=?",
                (cycle["id"], group["key"]),
            )
        )
        count = len(answers)
        row = {"key": group["key"], "label": group["label"]}
        if count < k or count > group["eligible_count"] - k:
            groups.append(row | {"status": "suppressed", "reason": "GROUP_DISCLOSURE_POLICY"})
            continue
        scales = []
        parsed = [json.loads(a["answers"]) for a in answers]
        for question in cycle["questions"]:
            counts = Counter(
                a["value"] for values in parsed for a in values if a["question_key"] == question["key"]
            )
            scales.append(
                {
                    "question_key": question["key"],
                    "categories": distribution(
                        list(range(question["min"], question["max"] + 1)), counts, k, "value"
                    ),
                }
            )
        topics = distribution(
            [t["key"] for t in cycle["topic_options"]], Counter(a["topic_key"] for a in answers), k, "key"
        )
        groups.append(row | {"status": "shown", "response_count": count, "scales": scales, "topics": topics})
    return groups


def scoped_publication(publication, actor):
    if "organizer" in actor["assignments"] or "publisher" in actor["assignments"]:
        return publication
    if "department" not in actor["roles"]:
        fail(404, "NOT_FOUND")
    groups = [g for g in publication["groups"] if g["key"] == actor["group_key"]]
    if not groups:
        fail(404, "NOT_FOUND")
    return publication | {"groups": groups}


@router.post("/cycles/{cycle_id}/publication")
def publish(cycle_id: UUID, body: PublicationCreate, ctx: Context):
    db, actor = ctx
    require_assignment(actor, "publisher")
    cycle = get(db, "cycle", cycle_id, actor)
    check_state(cycle["status"] == "closed")
    existing = publication_for_cycle(db, cycle_id, actor)
    if existing:
        if existing["policy"] != body.policy.model_dump() or existing["policy_basis"] != body.policy_basis:
            fail(409, "PUBLICATION_IMMUTABLE")
        return existing
    check_revision(cycle, body.expected_revision)
    publication = new(
        actor,
        cycle_id=str(cycle_id),
        status="published",
        policy=body.policy.model_dump(),
        policy_basis=body.policy_basis,
        policy_version="fixed-distributions-v1",
        question_version=cycle["question_version"],
        groups=table(db, cycle, body.policy.k),
        notice="Учебный порог; не нормативная гарантия анонимности. Скрытая строка не содержит чисел.",
    )
    return save(db, "publication", publication, actor, "publish", True)


@router.get("/publications/{publication_id}")
def read(publication_id: UUID, request: Request, ctx: Context):
    fixed_view(request)
    db, actor = ctx
    return scoped_publication(get(db, "publication", publication_id, actor), actor)


@router.get("/publications")
def list_publications(request: Request, ctx: Context):
    fixed_view(request)
    db, actor = ctx
    privileged = bool({"organizer", "publisher"}.intersection(actor["assignments"]))
    if not privileged and "department" not in actor["roles"]:
        return {"items": []}
    return {"items": [scoped_publication(p, actor) for p in rows(db, "publication", actor)
        if privileged or any(g["key"] == actor["group_key"] for g in p["groups"])]}
