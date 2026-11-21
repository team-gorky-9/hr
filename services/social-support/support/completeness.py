"""Reviews always refer to a submitted snapshot, never to a pending upload."""
from uuid import UUID
from fastapi import APIRouter, Request
from .api import Actor
from .core import (can_read, case_view, check_revision, fail, not_found, now, owner,
                   require_assigned, require_owner, state, uid)
from .schemas import Addendum, Completeness, StaffConfirmation

router = APIRouter(prefix="/api/v1/support")

@router.post("/cases/{case_id}/staff-confirmation")
def confirm_staff(case_id: UUID, body: StaffConfirmation, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_assigned(case, actor, "specialist")
        check_revision(case, body.expected_revision)
        state(case, "submitted", "needs_information", "ready_for_review")
        confirmation = {"state": body.state, "source_reference": body.source_reference,
                        "verified_by_actor_id": actor["actor_id"], "verified_at": now()}
        case["staff_confirmation"] = confirmation
        if body.state == "unknown" and case["status"] == "ready_for_review":
            case["status"] = "submitted"
        tx.save(case, "staff_confirmation", internal=confirmation)
        return case_view(case, actor)

@router.post("/cases/{case_id}/completeness")
def review(case_id: UUID, body: Completeness, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_assigned(case, actor, "specialist")
        check_revision(case, body.expected_revision)
        state(case, "submitted", "needs_information", "ready_for_review")
        rule = tx.rule(case["rule_version_id"])
        required = {i["key"] for i in rule["required_items"]}
        if len(body.items) != len(required) or {i.key for i in body.items} != required:
            fail("INVALID_CHECKLIST", "Нужна одна отметка по каждому пункту правил.", 422)
        submission = case["submissions"][-1]
        documents = {d["id"]: d for d in case["documents"] if d["id"] in submission["document_ids"]}
        for item in body.items:
            if item.result == "missing":
                if item.document_id is not None or any(d["item_key"] == item.key for d in documents.values()):
                    fail("INVALID_CHECKLIST", "Отсутствующий пункт не может иметь поданный документ.", 422)
            else:
                doc = documents.get(str(item.document_id))
                if doc is None or doc["item_key"] != item.key:
                    fail("INVALID_CHECKLIST", "Документ не принадлежит пункту текущей подачи.", 422)
            if item.result != "present" and not item.reason.strip():
                fail("REASON_REQUIRED", "Для замечания нужна причина.", 422)
        result = {"id": uid(), "case_id": case["id"],
                  "submission_revision": submission["submission_revision"],
                  "items": [i.model_dump(mode="json") for i in body.items],
                  "reviewed_by": actor["actor_id"], "reviewed_at": now()}
        case.setdefault("checklists", []).append(result)
        complete = all(i.result == "present" for i in body.items)
        confirmed = case.get("staff_confirmation", {}).get("state") == "confirmed"
        case["status"] = "ready_for_review" if complete and confirmed else ("submitted" if complete else "needs_information")
        case["public_message"] = body.public_message
        tx.save(case, "completeness_reviewed",
                {"message": body.public_message, "status": case["status"],
                 "submission_revision": submission["submission_revision"]}, result)
        return case_view(case, actor)

@router.post("/cases/{case_id}/addenda")
def addendum(case_id: UUID, body: Addendum, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_owner(case, actor)
        check_revision(case, body.expected_revision)
        state(case, "needs_information")
        ids = [str(d) for d in body.document_ids]
        if len(ids) != len(set(ids)):
            fail("DUPLICATE_DOCUMENT", "Документ указан дважды.", 422)
        documents = {d["id"]: d for d in case["documents"]}
        selected = [documents.get(d) for d in ids]
        if any(d is None or d["visibility"] != "applicant" or d["uploaded_by"] != actor["actor_id"] for d in selected):
            fail("INVALID_DOCUMENT", "Дополнение содержит недоступный документ.", 422)
        keys = [d["item_key"] for d in selected]
        if len(keys) != len(set(keys)):
            fail("DUPLICATE_ITEM", "Выберите одну новую версию на пункт.", 422)
        previous = case["submissions"][-1]
        current = {documents[d]["item_key"]: d for d in previous["document_ids"]}
        current.update({d["item_key"]: d["id"] for d in selected})
        submission = {"id": uid(), "submission_revision": previous["submission_revision"] + 1,
                      "statement": case["statement"], "text": body.text,
                      "document_ids": list(current.values()), "submitted_by": actor["actor_id"],
                      "submitted_at": now()}
        case["submissions"].append(submission)
        case["status"] = "submitted"
        case["public_message"] = "Дополнение получено; требуется новая проверка."
        tx.save(case, "addendum_submitted", {"submission": submission})
        return case_view(case, actor)

@router.get("/cases/{case_id}/history")
def history(case_id: UUID, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor) as tx:
        case = tx.get(case_id)
        if not can_read(case, actor):
            not_found()
        return tx.history(case)
