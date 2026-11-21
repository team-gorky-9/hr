"""Execution is external evidence, separate from approval."""
from uuid import UUID
from fastapi import APIRouter, Request
from .api import Actor
from .core import (public_execution, case_view, check_revision, fail, not_found, now, queue_view,
                   require_assigned, require_owner, state, uid)
from .schemas import Execution, ExecutorAssignment, Reason

router = APIRouter(prefix="/api/v1/support")

@router.post("/cases/{case_id}/executor-assignment")
def assign_executor(case_id: UUID, body: ExecutorAssignment, request: Request, actor: Actor):
    store = request.app.state.store
    with store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        if "coordinator" not in actor["roles"] or case["submitted_at"] is None:
            not_found()
        check_revision(case, body.expected_revision)
        state(case, "submitted", "needs_information", "ready_for_review", "decision_recorded")
        ident = store.target(actor, body.executor_actor_id, "executor")
        if ident == case["applicant_actor_id"]:
            fail("SELF_ASSIGNMENT", "Для своего дела нужен другой исполнитель.", 422)
        case["assigned_executor_id"] = ident
        case["executor_assignment_basis"] = body.assignment_basis
        tx.save(case, "executor_assigned", internal=body.model_dump(mode="json"))
        return queue_view(case)

@router.post("/cases/{case_id}/execution")
def execution(case_id: UUID, body: Execution, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_assigned(case, actor, "executor")
        check_revision(case, body.expected_revision)
        state(case, "decision_recorded")
        decision = case["decisions"][-1]
        if decision["outcome"] != "approved":
            fail("APPROVAL_REQUIRED", "Исполнение допускается только после одобрения.")
        record = body.model_dump(mode="json", exclude={"expected_revision"})
        record.update(id=uid(), case_id=case["id"], decision_id=decision["id"],
                      recorded_by=actor["actor_id"], recorded_at=now())
        case.setdefault("executions", []).append(record)
        case["execution"] = record
        tx.save(case, "execution_recorded", {"execution": public_execution(record)}, {"execution": record})
        return case_view(case, actor)

@router.post("/cases/{case_id}/close")
def close(case_id: UUID, body: Reason, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_assigned(case, actor, "specialist")
        check_revision(case, body.expected_revision)
        state(case, "decision_recorded")
        if case["decisions"][-1]["outcome"] not in {"approved", "declined"}:
            fail("FINAL_DECISION_REQUIRED", "Сначала зарегистрируйте окончательное решение.")
        case["status"] = "closed"
        case["closure"] = {"reason": body.reason, "closed_by": actor["actor_id"], "closed_at": now(),
                           "execution_status": (case.get("execution") or {}).get("status", "unknown")}
        tx.save(case, "closed", {"closure": case["closure"]})
        return case_view(case, actor)

@router.post("/cases/{case_id}/withdraw")
def withdraw(case_id: UUID, body: Reason, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_owner(case, actor)
        check_revision(case, body.expected_revision)
        state(case, "draft", "submitted", "needs_information", "ready_for_review")
        if any(d["outcome"] in {"approved", "declined"} for d in case.get("decisions", [])):
            fail("DECISION_ALREADY_RECORDED", "Последствия отзыва после решения рассматривает владелец процесса.")
        case["status"] = "withdrawn"
        case["withdrawal"] = {"reason": body.reason, "withdrawn_by": actor["actor_id"], "withdrawn_at": now()}
        tx.save(case, "withdrawn", {"withdrawal": case["withdrawal"]})
        return case_view(case, actor)
