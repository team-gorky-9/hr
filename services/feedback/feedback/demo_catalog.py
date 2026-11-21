"""Read-only public view of the explicitly registered synthetic cycles."""

from uuid import UUID

from fastapi import APIRouter, Request

from feedback.demo_surveys import DEMO_SURVEY_IDS, get_demo_cycle
from feedback.dependencies import fixed_view
from feedback.publications import publication_for_cycle
from feedback.store import DEMO_ORG, fail, transaction

router = APIRouter(prefix="/demo/cycles")
demo_scope = {"organization_id": DEMO_ORG}


def public_category(category, key):
    item = {key: category[key], "status": category["status"]}
    if category["status"] == "shown":
        item["count"] = category["count"]
    return item


def public_group(group):
    item = {key: group[key] for key in ("key", "label", "status")}
    if group["status"] != "shown":
        return item
    return item | {
        "response_count": group["response_count"],
        "scales": [{"question_key": scale["question_key"],
                    "categories": [public_category(category, "value") for category in scale["categories"]]}
                   for scale in group["scales"]],
        "topics": [public_category(category, "key") for category in group["topics"]],
    }


@router.get("")
def list_demo_cycles(request: Request):
    fixed_view(request)
    with transaction(request.app.state.database_path) as db:
        items = []
        for cycle_id in DEMO_SURVEY_IDS:
            cycle = get_demo_cycle(db, cycle_id)
            if cycle is None or cycle["status"] not in ("open", "closed"):
                continue
            publication = publication_for_cycle(db, cycle_id, demo_scope) if cycle["status"] == "closed" else None
            items.append({
                "id": cycle["id"], "title": cycle["title"], "status": cycle["status"],
                "has_results": publication is not None,
            })
    return {"items": items}


@router.get("/{cycle_id}/results")
def demo_results(cycle_id: UUID, request: Request):
    fixed_view(request)
    with transaction(request.app.state.database_path) as db:
        cycle = get_demo_cycle(db, cycle_id)
        if cycle is None or cycle["status"] != "closed":
            fail(404, "NOT_FOUND")
        publication = publication_for_cycle(db, cycle_id, demo_scope)
        if publication is None:
            fail(404, "NOT_FOUND")
        return {
            "cycle_id": cycle["id"],
            "questions": cycle["questions"],
            "topic_options": cycle["topic_options"],
            "groups": [public_group(group) for group in publication["groups"]],
            "notice": publication["notice"],
        }
