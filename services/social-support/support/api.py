import hashlib
import os
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse
from .core import (can_read, case_view, check_revision, document_view, fail, not_found,
                   now, owner, queue_view, require_owner, staff, state, uid)
from .schemas import Assignment, CreateCase, EditCase, Revision

router = APIRouter(prefix="/api/v1/support")
MAX_FILE_BYTES = 10 * 1024 * 1024

def actor(request: Request, authorization: str | None = Header(default=None)):
    return request.app.state.store.authenticate(authorization)

Actor = Annotated[dict, Depends(actor)]

@router.get("/rules")
def rules(request: Request, actor: Actor):
    with request.app.state.store.transaction(actor) as tx:
        return [r for r in tx.rules() if r["status"] == "published"]

@router.post("/cases", status_code=201)
def create(body: CreateCase, request: Request, actor: Actor):
    if "employee" not in actor["roles"]:
        not_found()
    with request.app.state.store.transaction(actor, True) as tx:
        rule = tx.rule(body.rule_version_id)
        case = {"id": uid(), "organization_id": actor["organization_id"],
                "applicant_actor_id": actor["actor_id"], "rule_version_id": rule["id"],
                "support_type": rule["support_type"], "revision": 0, "status": "draft",
                "statement": body.statement, "created_at": now(), "number": None,
                "submitted_at": None, "assigned_specialist_id": None,
                "assigned_secretary_id": None, "documents": [], "submissions": []}
        tx.save(case, "draft_created")
        return case_view(case, actor)

@router.get("/cases")
def list_cases(request: Request, actor: Actor):
    with request.app.state.store.transaction(actor) as tx:
        result = []
        for case in tx.all():
            if can_read(case, actor):
                result.append(case_view(case, actor))
            elif "coordinator" in actor["roles"] and case["status"] != "draft":
                result.append(queue_view(case))
        return result

@router.get("/cases/{case_id}")
def get_case(case_id: UUID, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor) as tx:
        return case_view(tx.get(case_id), actor)

@router.patch("/cases/{case_id}")
def edit(case_id: UUID, body: EditCase, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_owner(case, actor)
        check_revision(case, body.expected_revision)
        state(case, "draft")
        case["statement"] = body.statement
        tx.save(case, "draft_edited")
        return case_view(case, actor)

@router.post("/cases/{case_id}/documents", status_code=201)
def upload(case_id: UUID, request: Request, actor: Actor, file: UploadFile = File(),
           item_key: str = Form(), expected_revision: int = Form(ge=1),
           visibility: Literal["applicant", "internal"] = Form("applicant")):
    store = request.app.state.store
    final_path = None
    temp_path = None
    try:
        with store.transaction(actor, True) as tx:
            case = tx.get(case_id)
            if owner(case, actor):
                if visibility != "applicant":
                    not_found()
                state(case, "draft", "needs_information")
                if item_key not in {i["key"] for i in tx.rule(case["rule_version_id"])["required_items"]}:
                    fail("INVALID_ITEM", "Неизвестный пункт учебных правил.", 422)
            elif staff(case, actor):
                if visibility != "internal":
                    not_found()
                state(case, "submitted", "needs_information", "ready_for_review", "decision_recorded")
                if item_key != "internal":
                    fail("INVALID_ITEM", "Служебный файл имеет item_key=internal.", 422)
            else:
                not_found()
            check_revision(case, expected_revision)
            ident = uid()
            temp_path = store.files / (ident + ".upload")
            digest, size = hashlib.sha256(), 0
            with temp_path.open("xb") as output:
                while chunk := file.file.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        fail("FILE_TOO_LARGE", "Максимальный размер — 10 MiB.", 422)
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            if size == 0:
                fail("EMPTY_FILE", "Пустой файл не принимается.", 422)
            final_path = store.files / ident
            os.replace(temp_path, final_path)
            doc = {"id": ident, "case_id": case["id"], "item_key": item_key,
                   "original_name": (file.filename or "document").replace("\\", "/").split("/")[-1],
                   "content_type": file.content_type or "application/octet-stream",
                   "size_bytes": size, "sha256": digest.hexdigest(), "uploaded_by": actor["actor_id"],
                   "created_at": now(), "visibility": visibility, "storage_key": ident}
            case["documents"].append(doc)
            public = {"document_id": ident} if visibility == "applicant" else {}
            tx.save(case, "document_uploaded", public, {"document_id": ident})
            result = document_view(doc) | {"case_revision": case["revision"]}
        return result
    except BaseException:
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        file.file.close()

@router.get("/cases/{case_id}/documents/{document_id}/content")
def download(case_id: UUID, document_id: UUID, request: Request, actor: Actor):
    store = request.app.state.store
    with store.transaction(actor) as tx:
        case = tx.get(case_id)
        if not can_read(case, actor):
            not_found()
        doc = next((d for d in case["documents"] if d["id"] == str(document_id)), None)
        if doc is None or (owner(case, actor) and doc["visibility"] != "applicant"):
            not_found()
        path = store.files / doc["storage_key"]
        if not path.is_file():
            fail("ORIGINAL_UNAVAILABLE", "Оригинал временно недоступен.", 503)
        return FileResponse(path, media_type="application/octet-stream",
                            filename=doc["original_name"],
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

@router.post("/cases/{case_id}/submit")
def submit(case_id: UUID, body: Revision, request: Request, actor: Actor):
    with request.app.state.store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        require_owner(case, actor)
        check_revision(case, body.expected_revision)
        state(case, "draft")
        stamp = now()
        case["status"], case["submitted_at"] = "submitted", stamp
        case["number"] = "SP-" + case["id"]
        # An uploaded replacement supersedes the earlier file for this item only.
        latest = {d["item_key"]: d["id"] for d in case["documents"] if d["visibility"] == "applicant"}
        case["submissions"].append({"id": uid(), "submission_revision": 1,
                                   "statement": case["statement"], "document_ids": list(latest.values()),
                                   "submitted_by": actor["actor_id"], "submitted_at": stamp})
        tx.save(case, "submitted", {"submission_revision": 1})
        return case_view(case, actor)

@router.post("/cases/{case_id}/assign")
def assign(case_id: UUID, body: Assignment, request: Request, actor: Actor):
    store = request.app.state.store
    with store.transaction(actor, True) as tx:
        case = tx.get(case_id)
        if "coordinator" not in actor["roles"] or case["status"] == "draft":
            not_found()
        check_revision(case, body.expected_revision)
        state(case, "submitted", "needs_information", "ready_for_review", "decision_recorded")
        case["assigned_specialist_id"] = store.target(actor, body.specialist_actor_id, "specialist")
        case["assigned_secretary_id"] = store.target(actor, body.secretary_actor_id, "secretary")
        case["assignment_basis"] = body.assignment_basis
        tx.save(case, "assigned", internal=body.model_dump(mode="json"))
        return queue_view(case)
