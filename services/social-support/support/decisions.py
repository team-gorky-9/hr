"""Registration of external decisions; applicant extracts are an explicit allowlist."""
from uuid import UUID
from fastapi import APIRouter, Request
from .api import Actor
from .core import (extract_view, can_read, case_view, check_revision, fail, not_found, now,
                   require_assigned, state, uid)
from .schemas import Decision, DecisionCorrection

router = APIRouter(prefix="/api/v1/support")

def record(tx, case, body, actor, correction=False):
    require_assigned(case, actor, "secretary")
    check_revision(case, body.expected_revision)
    if correction:
        state(case, "decision_recorded")
        if not case.get("decisions"):
            fail("DECISION_REQUIRED", "Нет решения для исправления.")
    else:
        state(case, "ready_for_review")
    version = len(case.get("decisions", [])) + 1
    decision = body.model_dump(mode="json", exclude={"expected_revision"})
    decision.update(id=uid(), case_id=case["id"], version=version,
                    submission_revision=case["submissions"][-1]["submission_revision"],
                    recorded_by=actor["actor_id"], recorded_at=now(),
                    replaces_decision_id=case["decisions"][-1]["id"] if correction else None)
    case.setdefault("decisions", []).append(decision)
    case["status"] = "needs_information" if body.outcome == "needs_information" else "decision_recorded"
    case["public_message"] = body.public_explanation
    # Execution evidence is tied to an exact decision, never inherited by a correction.
    if correction:
        case["execution"] = None
    tx.save(case, "decision_corrected" if correction else "decision_recorded",
            {"extract": extract_view(decision)}, {"decision": decision})
    return case_view(case, actor)

@router.post("/cases/{case_id}/decision")
def decision(case_id: UUID, body: Decision, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        return record(tx, tx.get(case_id), body, actor)

@router.post("/cases/{case_id}/decision-corrections")
def correction(case_id: UUID, body: DecisionCorrection, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        return record(tx, tx.get(case_id), body, actor, correction=True)

@router.get("/cases/{case_id}/extract")
def extract(case_id: UUID, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor) as tx:
        case = tx.get(case_id)
        if not can_read(case, actor):
            not_found()
        if not case.get("decisions"):
            not_found()
        return extract_view(case["decisions"][-1])
