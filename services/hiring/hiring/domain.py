"""Hiring operations. Each method runs inside one database transaction opened by the API layer
and works on a case row locked with SELECT … FOR UPDATE, so two tabs cannot both act on the
same revision: the second one sees the new revision and gets STALE_REVISION."""
import base64
import json
import uuid
from datetime import datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hiring import schemas as s
from hiring.auth import Actor, known_candidate
from hiring.errors import Problem, forbidden, invalid_state, not_found, stale
from hiring.models import Case, CaseEvent, ChecklistItem, Document, now

ACTIVE = ("preparing", "awaiting_documents", "ready")
STATUSES = ("preparing", "awaiting_documents", "ready", "withdrawn", "started")
ITEM_DOCUMENT_KINDS = ("hiring_application", "hiring_evidence")
CANDIDATE_HIDDEN_KINDS = ("employment_basis",)


def iso(value):
    return value.isoformat() if value is not None else None


def uid(value):
    return str(value) if value is not None else None


# ---------------------------------------------------------------- views


def document_view(document: Document) -> dict:
    return {
        "id": uid(document.id),
        "organization_id": uid(document.organization_id),
        "case_id": uid(document.case_id),
        "kind": document.kind,
        "original_name": document.original_name,
        "media_type": document.media_type,
        "size_bytes": document.size_bytes,
        "sha256": document.sha256,
        "revision": document.revision,
        "uploaded_by": uid(document.uploaded_by),
        "created_at": iso(document.created_at),
        "updated_at": iso(document.updated_at),
    }


def item_view(item: ChecklistItem, for_candidate: bool = False) -> dict:
    view = {
        "id": uid(item.id),
        "case_id": uid(item.case_id),
        "key": item.key,
        "title": item.title,
        "required": item.required,
        "status": item.status,
        "document_ids": list(item.document_ids),
        "review_reason": item.review_reason,
        "reviewed_by_actor_id": uid(item.reviewed_by_actor_id),
        "revision": item.revision,
        "created_at": iso(item.created_at),
        "updated_at": iso(item.updated_at),
    }
    if for_candidate:
        view.pop("reviewed_by_actor_id")
    return view


def case_view(case: Case, items: list[ChecklistItem], for_candidate: bool = False) -> dict:
    checklist = [item_view(item, for_candidate) for item in items]
    if for_candidate:
        # The candidate sees the goal, statuses, own items with explanations and the allowed
        # result. No decision basis, no actor ids, no internal employment basis.
        return {
            "id": uid(case.id),
            "revision": case.revision,
            "status": case.status,
            "organization_id": uid(case.organization_id),
            "department_id": case.selection["department_id"],
            "position_code": case.selection["position_code"],
            "checklist_version": case.checklist_version,
            "starts_on": iso(case.starts_on),
            "checklist": checklist,
            "created_at": iso(case.created_at),
            "updated_at": iso(case.updated_at),
        }
    return {
        "id": uid(case.id),
        "revision": case.revision,
        "organization_id": uid(case.organization_id),
        "selection": case.selection,
        "provenance": {
            "source_mode": case.source_mode,
            "verified_by_actor_id": uid(case.verified_by_actor_id),
            "verified_at": iso(case.verified_at),
        },
        "is_synthetic": case.is_synthetic,
        "status": case.status,
        "checklist_version": case.checklist_version,
        "candidate_actor_id": uid(case.candidate_actor_id),
        "identity_basis": case.identity_basis,
        "starts_on": iso(case.starts_on),
        "basis": case.basis,
        "confirmation_basis": case.confirmation_basis,
        "withdraw_reason": case.withdraw_reason,
        "transfer_mode": case.transfer_mode,
        "workforce_status": case.workforce_status,
        "employee_id": uid(case.employee_id),
        "assignment_id": uid(case.assignment_id),
        "workforce_confirmation": case.workforce_confirmation,
        "workforce_assignment_snapshot": case.workforce_assignment_snapshot,
        "workforce_resolution": case.workforce_resolution,
        "workforce_review_reason": case.workforce_review_reason,
        "checklist": checklist,
        "created_at": iso(case.created_at),
        "updated_at": iso(case.updated_at),
    }


def event_view(event: CaseEvent, for_candidate: bool = False) -> dict:
    view = {
        "id": uid(event.id),
        "sequence": event.sequence,
        "case_revision": event.case_revision,
        "event_type": event.event_type,
        "item_id": uid(event.item_id),
        "actor_role": event.actor_role,
        "created_at": iso(event.created_at),
    }
    if for_candidate:
        view["data"] = event.candidate_data
    else:
        view["actor_id"] = uid(event.actor_id)
        view["data"] = event.data
    return view


# ---------------------------------------------------------------- operations


class Hiring:
    def __init__(self, session: Session, actor: Actor, settings):
        self.session, self.actor, self.settings = session, actor, settings

    # --- access

    def require_hr(self):
        if not self.actor.is_hr():
            raise forbidden("hr or admin of the organization is required")

    def require_reader(self):
        if not (self.actor.is_hr() or self.actor.is_candidate()):
            raise forbidden("Hiring cases are available to hr, admin and the linked candidate")

    def visible(self, case: Case | None) -> bool:
        if case is None or case.organization_id != self.actor.organization_id:
            return False
        if self.actor.is_hr():
            return True
        return self.actor.is_candidate() and case.candidate_actor_id == self.actor.actor_id

    def for_candidate(self) -> bool:
        return not self.actor.is_hr()

    def load_case(self, case_id: uuid.UUID, lock: bool = False) -> Case:
        self.require_reader()
        query = select(Case).where(Case.id == case_id)
        if lock:
            query = query.with_for_update()
        case = self.session.scalar(query)
        if not self.visible(case):
            raise not_found("Case")
        return case

    def items(self, case: Case) -> list[ChecklistItem]:
        return list(self.session.scalars(
            select(ChecklistItem).where(ChecklistItem.case_id == case.id).order_by(ChecklistItem.position)
        ))

    def view(self, case: Case) -> dict:
        self.session.flush()
        return case_view(case, self.items(case), self.for_candidate())

    # --- history

    def record(self, case: Case, event_type: str, data: dict, *, candidate: dict | None = None,
               item: ChecklistItem | None = None) -> None:
        """candidate=None hides the event from the candidate; a dict is what the candidate sees."""
        self.session.flush()
        sequence = (self.session.scalar(
            select(func.max(CaseEvent.sequence)).where(CaseEvent.case_id == case.id)) or 0) + 1
        self.session.add(CaseEvent(
            case_id=case.id, sequence=sequence, case_revision=case.revision,
            item_id=item.id if item else None, event_type=event_type,
            actor_id=self.actor.actor_id, actor_role=self.actor.role,
            visible_to_candidate=candidate is not None,
            data=json.loads(json.dumps(data, default=str)),
            candidate_data=json.loads(json.dumps(candidate or {}, default=str)),
        ))

    def history(self, case_id: uuid.UUID) -> dict:
        case = self.load_case(case_id)
        query = select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.sequence)
        if self.for_candidate():
            query = query.where(CaseEvent.visible_to_candidate.is_(True))
        return {"items": [event_view(e, self.for_candidate()) for e in self.session.scalars(query)]}

    # --- helpers

    @staticmethod
    def check_revision(obj, expected: int):
        if obj.revision != expected:
            raise stale()

    @staticmethod
    def bump(*objects):
        for obj in objects:
            obj.revision += 1

    def check_selection_source(self, selection: s.PositiveSelection):
        """fixture: the selection must be exactly one of the configured training snapshots.
        manual-confirmed: the authorized HR is the source; this is recorded, not hidden."""
        if self.settings.source_mode != "fixture":
            return
        wanted = selection.model_dump(mode="json")
        for entry in fixture_selections(self.settings):
            known = s.PositiveSelection.model_validate(entry).model_dump(mode="json")
            if known["application_ref"] == wanted["application_ref"]:
                if known != wanted:
                    raise Problem(409, "SELECTION_NOT_READY",
                                  "Selection differs from the confirmed fixture snapshot", "selection")
                return
        raise Problem(409, "SELECTION_NOT_READY", "No confirmed positive decision for this application",
                      "selection.application_ref")

    def check_candidate_account(self, candidate_actor_id: uuid.UUID):
        if known_candidate(self.settings, candidate_actor_id, self.actor.organization_id) is False:
            raise Problem(422, "VALIDATION_ERROR",
                          "candidate_actor_id is not a candidate account of this organization",
                          "candidate_actor_id")

    def basis_document(self, case: Case, basis: s.Basis) -> dict:
        document = self.session.scalar(select(Document).where(Document.id == basis.document_id).with_for_update())
        if document is None or document.organization_id != case.organization_id:
            raise Problem(422, "VALIDATION_ERROR", "Basis document not found", "basis.document_id")
        if document.kind != "employment_basis":
            raise Problem(422, "VALIDATION_ERROR", "Basis document must have kind employment_basis",
                          "basis.document_id")
        if document.case_id not in (None, case.id):
            raise invalid_state("Document belongs to another case", "basis.document_id")
        document.case_id = case.id
        return {"document_id": str(document.id), "reference": basis.reference, "issued_on": basis.issued_on.isoformat()}

    def find_active(self, application_ref: s.ApplicationRef) -> Case | None:
        return self.session.scalar(select(Case).where(
            Case.application_system == application_ref.system,
            Case.application_id == application_ref.id,
            Case.status != "withdrawn",
        ))

    # --- cases

    def create(self, body: s.CreateCase) -> tuple[int, dict]:
        self.require_hr()
        selection = body.selection
        if selection.organization_id != self.actor.organization_id:
            raise forbidden("Selection belongs to another organization")
        if selection.outcome != "hired":
            raise Problem(409, "SELECTION_NOT_READY", "Selection outcome is not hired", "selection.outcome")
        self.check_selection_source(selection)
        if self.settings.source_mode == "fixture" and not selection.is_synthetic:
            raise Problem(422, "VALIDATION_ERROR", "Fixture source accepts only synthetic selections",
                          "selection.is_synthetic")
        existing = self.find_active(selection.application_ref)
        if existing is not None:
            return self.existing(existing)
        if body.candidate_actor_id is not None:
            self.check_candidate_account(body.candidate_actor_id)
        case = Case(
            id=uuid.uuid4(), organization_id=selection.organization_id,
            application_system=selection.application_ref.system, application_id=selection.application_ref.id,
            selection=selection.model_dump(mode="json"), is_synthetic=selection.is_synthetic,
            source_mode=self.settings.source_mode, verified_by_actor_id=self.actor.actor_id, verified_at=now(),
            status="preparing", checklist_version=body.checklist_version,
            candidate_actor_id=body.candidate_actor_id, identity_basis=body.identity_basis,
            transfer_mode="manual", workforce_status="not_sent", start_version=0,
        )
        try:
            with self.session.begin_nested():
                self.session.add(case)
                self.session.flush()
        except IntegrityError:
            # A parallel request created the case for the same application_ref first.
            existing = self.find_active(selection.application_ref)
            if existing is None:
                raise
            return self.existing(existing)
        for position, entry in enumerate(body.checklist):
            self.session.add(ChecklistItem(case_id=case.id, position=position, key=entry.key, title=entry.title,
                                           required=entry.required, status="requested", document_ids=[]))
        self.record(case, "case.created", {
            "application_ref": selection.application_ref.model_dump(mode="json"),
            "source_mode": case.source_mode, "checklist_version": body.checklist_version,
            "checklist": [e.model_dump() for e in body.checklist],
            "candidate_actor_id": body.candidate_actor_id, "identity_basis": body.identity_basis,
        }, candidate={"position_code": selection.position_code})
        return 201, self.view(case)

    def existing(self, case: Case) -> tuple[int, dict]:
        if case.organization_id != self.actor.organization_id:
            raise invalid_state("Application is already handled by another organization", "selection.application_ref")
        return 200, self.view(case)

    def list_cases(self, status: str | None, limit: int, cursor: str | None) -> dict:
        self.require_reader()
        query = select(Case).where(Case.organization_id == self.actor.organization_id)
        if not self.actor.is_hr():
            query = query.where(Case.candidate_actor_id == self.actor.actor_id)
        if status is not None:
            if status not in STATUSES:
                raise Problem(422, "VALIDATION_ERROR", f"status must be one of {', '.join(STATUSES)}", "status")
            query = query.where(Case.status == status)
        if cursor:
            created_at, case_id = decode_cursor(cursor)
            query = query.where(tuple_(Case.created_at, Case.id) > tuple_(created_at, case_id))
        rows = list(self.session.scalars(query.order_by(Case.created_at, Case.id).limit(limit + 1)))
        page, more = rows[:limit], len(rows) > limit
        return {
            "items": [self.view(case) for case in page],
            "next_cursor": encode_cursor(page[-1]) if more else None,
        }

    def get(self, case_id: uuid.UUID) -> dict:
        return self.view(self.load_case(case_id))

    def request_documents(self, case_id, body: s.RequestDocuments) -> dict:
        self.require_hr()
        case = self.load_case(case_id, lock=True)
        self.check_revision(case, body.expected_revision)
        if case.status not in ("preparing", "awaiting_documents"):
            raise invalid_state(f"Documents cannot be requested in status {case.status}")
        case.status = "awaiting_documents"
        self.bump(case)
        self.record(case, "documents.requested", {"message": body.message}, candidate={"message": body.message})
        return self.view(case)

    def locked_item(self, case: Case, item_id: uuid.UUID) -> ChecklistItem:
        item = self.session.scalar(select(ChecklistItem).where(
            ChecklistItem.id == item_id, ChecklistItem.case_id == case.id).with_for_update())
        if item is None:
            raise not_found("Checklist item")
        return item

    def submit(self, case_id, item_id, body: s.SubmitItem) -> dict:
        # Role check before lookup: a candidate who is not linked gets the same 404 as a missing case.
        case = self.load_case(case_id, lock=True)
        item = self.locked_item(case, item_id)
        if case.status == "withdrawn":
            raise invalid_state("Case is withdrawn")
        self.check_revision(item, body.expected_revision)
        document = self.session.scalar(select(Document).where(Document.id == body.document_id).with_for_update())
        own = document is not None and document.organization_id == case.organization_id and (
            self.actor.is_hr() or document.uploaded_by == self.actor.actor_id)
        if not own:
            raise Problem(422, "VALIDATION_ERROR", "Document not found", "document_id")
        if document.kind not in ITEM_DOCUMENT_KINDS:
            raise Problem(422, "VALIDATION_ERROR",
                          f"Checklist accepts {', '.join(ITEM_DOCUMENT_KINDS)} documents", "document_id")
        if document.case_id not in (None, case.id):
            raise invalid_state("Document belongs to another case", "document_id")
        if any(str(document.id) in other.document_ids for other in self.items(case)):
            raise invalid_state("Document is already submitted; upload a new file for a new version",
                                "document_id")
        previous = item.status
        document.case_id = case.id
        item.document_ids = [*item.document_ids, str(document.id)]
        item.status = "received"
        item.review_reason = None
        item.reviewed_by_actor_id = None
        reopened = case.status == "ready"
        if case.status in ("preparing", "ready"):
            # The new version is not accepted yet, so an earlier «ready» no longer holds.
            case.status = "awaiting_documents"
        self.bump(item, case)
        self.record(case, "item.submitted", {
            "item_key": item.key, "document_id": str(document.id), "comment": body.comment,
            "previous_status": previous, "revoked_accepted": previous == "accepted",
            "case_reopened": reopened, "after_start": case.status == "started",
        }, candidate={"item_key": item.key, "document_id": str(document.id), "comment": body.comment}, item=item)
        self.session.flush()
        return item_view(item, self.for_candidate())

    def review(self, case_id, item_id, body: s.ReviewItem) -> dict:
        self.require_hr()
        case = self.load_case(case_id, lock=True)
        item = self.locked_item(case, item_id)
        if case.status == "withdrawn":
            raise invalid_state("Case is withdrawn")
        self.check_revision(item, body.expected_revision)
        if item.status != "received":
            raise invalid_state(f"Only a received document can be reviewed, item is {item.status}")
        document_id = item.document_ids[-1]
        item.status = body.result
        item.review_reason = body.reason
        item.reviewed_by_actor_id = self.actor.actor_id
        self.bump(item, case)
        self.record(case, "item.reviewed", {
            "item_key": item.key, "document_id": document_id, "result": body.result, "reason": body.reason,
        }, candidate={"item_key": item.key, "document_id": document_id, "result": body.result,
                      "reason": body.reason}, item=item)
        self.session.flush()
        return item_view(item)

    def missing_items(self, case: Case) -> list[str]:
        return [item.key for item in self.items(case) if item.required and item.status != "accepted"]

    def ready(self, case_id, body: s.Ready) -> dict:
        self.require_hr()
        case = self.load_case(case_id, lock=True)
        self.check_revision(case, body.expected_revision)
        if case.status not in ("preparing", "awaiting_documents"):
            raise invalid_state(f"Case cannot become ready from status {case.status}")
        missing = self.missing_items(case)
        if missing:
            raise invalid_state("Required items are not accepted: " + ", ".join(missing), "checklist")
        case.status = "ready"
        self.bump(case)
        self.record(case, "case.ready", {}, candidate={})
        return self.view(case)

    def start(self, case_id, body: s.Start) -> dict:
        self.require_hr()
        case = self.load_case(case_id, lock=True)
        self.check_revision(case, body.expected_revision)
        if case.status != "ready":
            raise invalid_state(f"Start can be confirmed only for a ready case, status is {case.status}")
        missing = self.missing_items(case)
        if missing:  # defensive: «ready» is reset by every item change, this should not happen
            raise invalid_state("Required items are not accepted: " + ", ".join(missing), "checklist")
        case.basis = self.basis_document(case, body.basis)
        case.starts_on = body.starts_on
        case.confirmation_basis = body.confirmation_basis
        case.started_by_actor_id = self.actor.actor_id
        case.start_version = 1
        case.status = "started"
        case.workforce_status = "not_sent"  # stage 1: HR registers the employee manually
        self.bump(case)
        self.record(case, "case.started", {
            "starts_on": body.starts_on, "basis": case.basis, "confirmation_basis": body.confirmation_basis,
            "start_version": 1, "transfer_mode": "manual",
        }, candidate={"starts_on": body.starts_on})
        return self.view(case)

    def withdraw(self, case_id, body: s.Withdraw) -> dict:
        case = self.load_case(case_id, lock=True)  # hr or the linked candidate
        self.check_revision(case, body.expected_revision)
        if case.status == "started":
            raise invalid_state("A started case needs a separate HR correction, not a withdrawal")
        if case.status not in ACTIVE:
            raise invalid_state(f"Case cannot be withdrawn from status {case.status}")
        case.status = "withdrawn"
        case.withdraw_reason = body.reason
        self.bump(case)
        self.record(case, "case.withdrawn", {"reason": body.reason}, candidate={"by_role": self.actor.role})
        return self.view(case)

    def link_account(self, case_id, body: s.LinkAccount) -> dict:
        self.require_hr()
        case = self.load_case(case_id, lock=True)
        self.check_revision(case, body.expected_revision)
        if case.status == "withdrawn":
            raise invalid_state("Case is withdrawn")
        self.check_candidate_account(body.candidate_actor_id)
        previous = case.candidate_actor_id
        case.candidate_actor_id = body.candidate_actor_id
        case.identity_basis = body.identity_basis
        self.bump(case)
        self.record(case, "account.linked", {
            "candidate_actor_id": body.candidate_actor_id, "previous_candidate_actor_id": previous,
            "identity_basis": body.identity_basis,
        })
        return self.view(case)

    def correct_start(self, case_id, body: s.CorrectStart) -> dict:
        self.require_hr()
        case = self.load_case(case_id, lock=True)
        self.check_revision(case, body.expected_revision)
        if case.status != "started":
            raise invalid_state(f"Only a started case can be corrected, status is {case.status}")
        previous = {"starts_on": iso(case.starts_on), "basis": case.basis, "start_version": case.start_version}
        if body.basis is not None:
            case.basis = self.basis_document(case, body.basis)
        if body.starts_on is not None:
            case.starts_on = body.starts_on
        case.start_version += 1
        if case.workforce_confirmation is not None:
            # The HR record was confirmed for the previous version: it must be re-checked.
            # The previous confirmation and snapshot stay on the case so HR sees both side by side.
            case.workforce_status = "review_required"
            case.workforce_resolution = None
            case.workforce_review_reason = body.reason
        self.bump(case)
        self.record(case, "start.corrected", {
            "previous": previous, "starts_on": iso(case.starts_on), "basis": case.basis, "reason": body.reason,
            "start_version": case.start_version, "workforce_status": case.workforce_status,
        }, candidate={"starts_on": iso(case.starts_on)})
        return self.view(case)

    def record_assignment(self, case_id, body: s.RecordAssignment) -> dict:
        self.require_hr()
        case = self.load_case(case_id, lock=True)
        self.check_revision(case, body.expected_revision)
        if case.status != "started":
            raise invalid_state(f"Assignment can be recorded only for a started case, status is {case.status}")
        previous = {
            "workforce_status": case.workforce_status, "workforce_confirmation": case.workforce_confirmation,
            "workforce_assignment_snapshot": case.workforce_assignment_snapshot,
        }
        same_date = body.actual_starts_on == case.starts_on
        recorded_at = now()
        system = body.employee_ref.system
        case.workforce_confirmation = {
            "employee_ref": body.employee_ref.model_dump(mode="json"),
            "assignment_ref": body.assignment_ref.model_dump(mode="json"),
            "actual_starts_on": body.actual_starts_on.isoformat(),
            "confirmation_basis": body.confirmation_basis,
            "recorded_by_actor_id": str(self.actor.actor_id),
            "recorded_at": recorded_at.isoformat(),
            "method": "manual-confirmed",
            "start_version": case.start_version,
        }
        case.workforce_assignment_snapshot = {
            "department_id": case.selection["department_id"],
            "position_code": case.selection["position_code"],
            "starts_on": body.actual_starts_on.isoformat(),
            # A manual record has no Workforce revision; the source says where the data came from.
            "revision": None,
            "source": {"system": system, "method": "manual-confirmed"},
        }
        # Old employee_id/assignment_id carry only Workforce ids, never ids of an external system.
        case.employee_id = body.employee_ref.id if system == "workforce" else None
        case.assignment_id = body.assignment_ref.id if system == "workforce" else None
        case.workforce_status = "registered" if same_date else "registered_with_difference"
        if previous["workforce_status"] == "review_required":
            case.workforce_resolution = "corrected" if same_date else "kept_existing"
        else:
            case.workforce_resolution = None
        case.workforce_review_reason = None if same_date else (
            f"Кадровая дата {body.actual_starts_on.isoformat()} отличается от даты оформления "
            f"{case.starts_on.isoformat()}. Основание: {body.confirmation_basis}")
        self.bump(case)
        self.record(case, "assignment.recorded", {
            "confirmation": case.workforce_confirmation, "snapshot": case.workforce_assignment_snapshot,
            "workforce_status": case.workforce_status, "workforce_resolution": case.workforce_resolution,
            "previous": previous,
        })
        return self.view(case)

    def registration_data(self, case_id) -> dict:
        self.require_hr()
        case = self.load_case(case_id)
        if case.status != "started":
            raise invalid_state(f"Registration data exists only for a started case, status is {case.status}")
        selection = case.selection
        return {
            "case_id": str(case.id),
            "case_revision": case.revision,
            "application_ref": selection["application_ref"],
            "person_ref": selection["candidate_ref"],
            "organization_id": str(case.organization_id),
            "department_id": selection["department_id"],
            "position_code": selection["position_code"],
            "starts_on": iso(case.starts_on),
            "basis": {
                "document_ref": {"service": "hiring", "id": case.basis["document_id"]},
                "reference": case.basis["reference"],
                "issued_on": case.basis["issued_on"],
            },
            "transfer_mode": "manual",
        }

    # --- documents

    def can_read_document(self, document: Document | None) -> bool:
        if document is None or document.organization_id != self.actor.organization_id:
            return False
        if self.actor.is_hr():
            return True
        if not self.actor.is_candidate():
            return False
        if document.uploaded_by == self.actor.actor_id:
            return True
        if document.kind in CANDIDATE_HIDDEN_KINDS or document.case_id is None:
            return False
        case = self.session.get(Case, document.case_id)
        return case is not None and case.candidate_actor_id == self.actor.actor_id

    def document(self, document_id: uuid.UUID) -> Document:
        self.require_reader()
        document = self.session.get(Document, document_id)
        if not self.can_read_document(document):
            raise not_found("Document")
        return document


def fixture_selections(settings) -> list[dict]:
    shared = json.loads((settings.fixture_dir / "selection.json").read_text(encoding="utf-8"))
    extra = json.loads(settings.extra_selections_file.read_text(encoding="utf-8"))
    return [shared, *extra["selections"]]


def encode_cursor(case: Case) -> str:
    raw = json.dumps([case.created_at.isoformat(), str(case.id)]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str):
    try:
        created_at, case_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(created_at), uuid.UUID(case_id)
    except (ValueError, TypeError) as exc:
        raise Problem(422, "VALIDATION_ERROR", "Invalid cursor", "cursor") from exc
