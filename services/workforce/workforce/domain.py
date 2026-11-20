import base64
import hashlib
import json
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select

from workforce.models import (
    Actor,
    Assignment,
    Audit,
    Delegation,
    Department,
    Employee,
    Organization,
    Outbox,
    SourceRef,
    now,
)


class Problem(Exception):
    def __init__(self, status, code, message, field=None):
        self.status, self.code, self.message, self.field = status, code, message, field


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def iso(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def serialize(row):
    hidden = {"password_hash", "basis_key", "source_payload"}
    return {
        column.name: iso(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in hidden
    }


def actor_view(actor):
    return {
        "actor_id": actor.id,
        "login": actor.login,
        "organization_id": actor.organization_id,
        "grants": actor.grants,
    }


def permitted(actor, roles):
    return any(
        g["role"] in roles and g["scope_type"] == "organization" and g["scope_id"] == actor.organization_id
        for g in actor.grants
    )


def require(actor, *roles):
    if not permitted(actor, roles):
        raise Problem(403, "FORBIDDEN", "This operation is not allowed for this actor")


def lock_organization(session, organization_id):
    row = session.scalar(select(Organization).where(Organization.id == organization_id).with_for_update())
    if row is None:
        raise Problem(404, "NOT_FOUND", "Organization not found")


def owned(session, model, id, organization_id):
    row = session.scalar(select(model).where(model.id == str(id), model.organization_id == organization_id))
    if row is None:
        raise Problem(404, "NOT_FOUND", "Resource not found")
    return row


def revision(row, expected):
    if row.revision != expected:
        raise Problem(409, "STALE_REVISION", "The resource has changed; reload it", "expected_revision")


def changed(row):
    row.revision += 1
    row.updated_at = now()


def dates(start, end):
    if end is not None and end < start:
        raise Problem(422, "VALIDATION_ERROR", "End date precedes start date", "ends_on")


def page(session, statement, model, limit, cursor, scope, render=serialize):
    if cursor:
        try:
            data = json.loads(base64.urlsafe_b64decode(cursor.encode() + b"=" * (-len(cursor) % 4)))
            if data["scope"] != scope:
                raise ValueError("cursor scope")
            stamp = datetime.fromisoformat(data["time"])
            key = str(UUID(data["id"]))
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise Problem(422, "VALIDATION_ERROR", "Invalid cursor", "cursor") from exc
        statement = statement.where(
            (model.created_at > stamp) | ((model.created_at == stamp) & (model.id > key))
        )
    rows = list(session.scalars(statement.order_by(model.created_at, model.id).limit(limit + 1)))
    continuation = None
    if len(rows) > limit:
        last = rows[limit - 1]
        continuation = (
            base64.urlsafe_b64encode(
                json.dumps({"scope": scope, "time": iso(last.created_at), "id": last.id}).encode()
            )
            .decode()
            .rstrip("=")
        )
    return {"items": [render(row) for row in rows[:limit]], "next_cursor": continuation}


class Workforce:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.org = actor.organization_id

    def get(self, model, id):
        return owned(self.session, model, id, self.org)

    def employee_view(self, row, detail=False, self_view=False):
        result = serialize(row)
        if not self_view:
            result["source_refs"] = [
                {"system": r.system, "id": r.source_id}
                for r in self.session.scalars(
                    select(SourceRef)
                    .where(SourceRef.employee_id == row.id)
                    .order_by(SourceRef.system, SourceRef.source_id)
                )
            ]
        if detail:
            result["assignments"] = [
                serialize(r)
                for r in self.session.scalars(
                    select(Assignment)
                    .where(Assignment.employee_id == row.id)
                    .order_by(Assignment.starts_on, Assignment.id)
                )
            ]
            if self_view:
                for assignment in result["assignments"]:
                    for key in ("basis", "recorded_by"):
                        assignment.pop(key)
        return result

    def audit(self, action, row, before, basis, employee_id=None, effective_on=None):
        self.session.flush()
        self.session.add(
            Audit(
                organization_id=self.org,
                employee_id=employee_id,
                resource_id=row.id,
                actor_id=self.actor.id,
                action=action,
                before=before,
                after=serialize(row),
                basis=basis,
                effective_on=effective_on,
            )
        )

    def actor_link(self, actor_id):
        if actor_id:
            actor = self.get(Actor, actor_id)
            if not actor.active:
                raise Problem(422, "VALIDATION_ERROR", "Actor is inactive", "account_actor_id")

    def department_parent(self, parent_id, target=None):
        seen = {target} if target else set()
        while parent_id:
            parent_id = str(parent_id)
            if parent_id in seen:
                raise Problem(
                    422, "VALIDATION_ERROR", "Department hierarchy cannot contain cycles", "parent_id"
                )
            seen.add(parent_id)
            parent_id = self.get(Department, parent_id).parent_id

    def department_create(self, body, _):
        self.department_parent(body.parent_id)
        row = Department(organization_id=self.org, **body.model_dump(mode="json"))
        self.session.add(row)
        self.audit("department.create", row, None, "Directory entry")
        return serialize(row)

    def department_patch(self, body, row):
        before = serialize(row)
        values = body.model_dump(mode="json", exclude_unset=True, exclude={"expected_revision"})
        if "parent_id" in values:
            self.department_parent(values["parent_id"], row.id)
        for key, value in values.items():
            setattr(row, key, value)
        changed(row)
        self.audit("department.correct", row, before, "Directory correction")
        return serialize(row)

    def add_sources(self, row, sources):
        added = False
        for source in sources:
            existing = self.session.get(SourceRef, (self.org, source["system"], source["id"]))
            if existing and existing.employee_id != row.id:
                raise Problem(409, "INVALID_STATE", "Source is linked to a different employee")
            if not existing:
                added = True
                self.session.add(
                    SourceRef(
                        organization_id=self.org,
                        system=source["system"],
                        source_id=source["id"],
                        employee_id=row.id,
                    )
                )
                self.session.flush()
        return added

    def create_employee(self, name, sources, actor_id, basis):
        self.actor_link(actor_id)
        row = Employee(
            organization_id=self.org, display_name=name, account_actor_id=str(actor_id) if actor_id else None
        )
        self.session.add(row)
        self.session.flush()
        self.add_sources(row, sources)
        self.audit("employee.create", row, None, {"confirmation": basis, "source_refs": sources}, row.id)
        return row

    def employee_create(self, body, _):
        row = self.create_employee(
            body.display_name,
            [r.model_dump() for r in body.source_refs],
            body.account_actor_id,
            body.confirmation_basis,
        )
        return self.employee_view(row)

    def employee_patch(self, body, row):
        before = serialize(row)
        values = body.model_dump(
            mode="json", exclude_unset=True, exclude={"expected_revision", "correction_basis"}
        )
        if "account_actor_id" in values:
            self.actor_link(values["account_actor_id"])
        for key, value in values.items():
            setattr(row, key, value)
        changed(row)
        self.audit("employee.correct", row, before, body.correction_basis, row.id)
        return self.employee_view(row)

    def make_assignment(self, person, values):
        self.get(Department, values["department_id"])
        if values.get("manager_employee_id"):
            self.get(Employee, values["manager_employee_id"])
        dates(values["starts_on"], values.get("ends_on"))
        values = {
            **values,
            "department_id": str(values["department_id"]),
            "manager_employee_id": str(values["manager_employee_id"])
            if values.get("manager_employee_id")
            else None,
        }
        row = Assignment(
            organization_id=self.org,
            employee_id=person.id,
            recorded_by=self.actor.id,
            basis_key=digest(values["basis"]),
            **values,
        )
        self.session.add(row)
        self.audit("assignment.create", row, None, values["basis"], person.id, row.starts_on)
        return row

    def assignment_create(self, body, person):
        values = body.model_dump()
        values["basis"] = body.basis.model_dump(mode="json")
        return serialize(self.make_assignment(person, values))

    def assignment_end(self, body, row):
        dates(row.starts_on, body.ends_on)
        before = serialize(row)
        row.ends_on = body.ends_on
        changed(row)
        self.audit("assignment.end", row, before, body.reason, row.employee_id, row.ends_on)
        return serialize(row)

    def assignment_transfer(self, body, row):
        dates(row.starts_on, body.ends_on)
        if body.starts_on <= body.ends_on:
            raise Problem(
                422, "VALIDATION_ERROR", "Transfer starts after the previous period ends", "starts_on"
            )
        before = serialize(row)
        new = self.make_assignment(
            self.get(Employee, row.employee_id),
            {
                "department_id": body.new_department_id,
                "position_code": body.new_position_code,
                "starts_on": body.starts_on,
                "ends_on": None,
                "manager_employee_id": body.manager_employee_id,
                "basis": body.basis.model_dump(mode="json"),
            },
        )
        row.ends_on = body.ends_on
        changed(row)
        self.audit(
            "assignment.transfer",
            row,
            before,
            body.basis.model_dump(mode="json"),
            row.employee_id,
            row.ends_on,
        )
        return {"ended": serialize(row), "new": serialize(new)}

    def assignment_correct(self, body, row):
        before = serialize(row)
        values = body.model_dump(exclude_unset=True, exclude={"expected_revision", "reason", "basis"})
        manager = values.get("manager_employee_id")
        if manager:
            self.get(Employee, manager)
            values["manager_employee_id"] = str(manager)
        dates(values.get("starts_on", row.starts_on), values.get("ends_on", row.ends_on))
        for key, value in values.items():
            setattr(row, key, value)
        row.basis = body.basis.model_dump(mode="json")
        row.basis_key = digest(row.basis)
        changed(row)
        self.audit(
            "assignment.correct",
            row,
            before,
            {"reason": body.reason, "basis": row.basis},
            row.employee_id,
            row.starts_on,
        )
        return serialize(row)

    def delegation_create(self, body, _):
        self.get(Employee, body.manager_employee_id)
        self.get(Employee, body.substitute_employee_id)
        self.get(Department, body.department_id)
        dates(body.starts_on, body.ends_on)
        if body.manager_employee_id == body.substitute_employee_id:
            raise Problem(422, "VALIDATION_ERROR", "A manager cannot substitute themselves")
        values = body.model_dump(mode="json")
        values.update(starts_on=body.starts_on, ends_on=body.ends_on)
        row = Delegation(organization_id=self.org, **values)
        self.session.add(row)
        self.audit("delegation.create", row, None, values["basis"], row.manager_employee_id, row.starts_on)
        return serialize(row)

    def delegation_end(self, body, row):
        dates(row.starts_on, body.ends_on)
        if body.ends_on > row.ends_on:
            raise Problem(422, "VALIDATION_ERROR", "Ending a delegation cannot extend it", "ends_on")
        before = serialize(row)
        row.ends_on = body.ends_on
        changed(row)
        self.audit("delegation.end", row, before, body.reason, row.manager_employee_id, row.ends_on)
        return serialize(row)

    def intake_reject(self, body, row):
        if row.assignment_id:
            raise Problem(409, "CORRECTION_REVIEW_REQUIRED", "Review the existing assignment")
        if row.status not in {"received", "needs_review"} or row.assignment_id:
            raise Problem(409, "INVALID_STATE", "This intake cannot be rejected")
        before = serialize(row)
        row.status, row.issue = "rejected", body.reason
        changed(row)
        self.audit("intake.reject", row, before, body.reason)
        return serialize(row)

    def intake_register(self, body, row):
        if row.assignment_id:
            raise Problem(409, "CORRECTION_REVIEW_REQUIRED", "Review the existing assignment")
        if row.status not in {"received", "needs_review"} or row.assignment_id:
            raise Problem(
                409, "INVALID_STATE", "An existing registration requires a separate correction decision"
            )
        before = serialize(row)
        source = {"system": row.person_ref["system"], "id": row.person_ref["id"]}
        if body.employee_id:
            person = self.get(Employee, body.employee_id)
            previous_person = serialize(person)
            if self.add_sources(person, [source]):
                changed(person)
                self.audit(
                    "employee.source_confirm",
                    person,
                    previous_person,
                    {"identity_basis": body.identity_basis, "source_ref": source},
                    person.id,
                )
        else:
            person = self.create_employee(
                body.create_employee.display_name, [source], None, body.identity_basis
            )
        proposed = row.proposed_assignment
        assignment = self.make_assignment(
            person,
            {
                "department_id": proposed["department_id"],
                "position_code": proposed["position_code"],
                "starts_on": date.fromisoformat(proposed["starts_on"]),
                "ends_on": None,
                "basis": {key: proposed["basis"][key] for key in ("reference", "issued_on")},
                "manager_employee_id": None,
            },
        )
        row.employee_id, row.assignment_id = person.id, assignment.id
        row.status, row.issue = "registered", None
        changed(row)
        from workforce.events import registration_event

        envelope = registration_event(row, assignment)
        self.session.add(
            Outbox(
                organization_id=self.org,
                event_id=envelope["event_id"],
                event_type=envelope["event_type"],
                envelope=envelope,
            )
        )
        self.audit("intake.register", row, before, body.identity_basis, person.id, assignment.starts_on)
        return {
            "intake": serialize(row),
            "employee": self.employee_view(person),
            "assignment": serialize(assignment),
        }

    def intake_review(self, body, row):
        if row.status != "needs_review" or row.assignment_id is None:
            raise Problem(409, "INVALID_STATE", "No registered assignment awaits review")
        assignment = self.get(Assignment, row.assignment_id)
        revision(assignment, body.expected_assignment_revision)
        before_intake, before_assignment = serialize(row), serialize(assignment)
        if body.decision == "apply":
            proposed = row.proposed_assignment
            source = self.session.get(SourceRef, (self.org, row.person_ref["system"], row.person_ref["id"]))
            if (
                source is None
                or source.employee_id != assignment.employee_id
                or proposed["department_id"] != assignment.department_id
                or proposed["position_code"] != assignment.position_code
            ):
                raise Problem(
                    409,
                    "MANUAL_PERSONNEL_CHANGE_REQUIRED",
                    "Changing employee, department or position requires a separate personnel event",
                )
            starts_on = date.fromisoformat(proposed["starts_on"])
            dates(starts_on, assignment.ends_on)
            assignment.starts_on = starts_on
            assignment.basis = {key: proposed["basis"][key] for key in ("reference", "issued_on")}
            assignment.basis_key = digest(assignment.basis)
            changed(assignment)
        review = {
            "decision": body.decision,
            "reason": body.reason,
            "reviewed_by_actor_id": self.actor.id,
            "reviewed_at": now().isoformat(),
            "source_case_revision": row.source_case_revision,
            "source_event_id": row.source_event_id,
            "assignment_revision": assignment.revision,
        }
        row.last_review, row.status, row.issue = review, "registered", None
        changed(row)
        self.audit(
            "assignment.review",
            assignment,
            before_assignment,
            review,
            assignment.employee_id,
            assignment.starts_on,
        )
        self.audit("intake.review", row, before_intake, review, assignment.employee_id, assignment.starts_on)
        from workforce.events import review_event

        envelope = review_event(row, assignment, review)
        self.session.add(
            Outbox(
                organization_id=self.org,
                event_id=envelope["event_id"],
                event_type=envelope["event_type"],
                envelope=envelope,
            )
        )
        return {"intake": serialize(row), "assignment": serialize(assignment), "review": review}

    def intake_resolve_correction(self, body, row):
        from workforce.schemas import Review

        decision = "apply" if body.action == "apply_correction" else "keep"
        result = self.intake_review(
            Review(
                expected_revision=body.expected_revision,
                expected_assignment_revision=body.expected_assignment_revision,
                decision=decision,
                reason=body.reason,
            ),
            row,
        )
        return {
            "intake": result["intake"],
            "assignment": result["assignment"],
            "resolution": "corrected" if decision == "apply" else "kept_existing",
        }

    def delivery_retry(self, body, row):
        if row.status == "sent":
            raise Problem(409, "INVALID_STATE", "Delivery is already sent")
        before = serialize(row)
        row.status, row.attempts, row.last_error, row.next_attempt_at = "pending", 0, None, now()
        changed(row)
        self.audit("delivery.retry", row, before, "Manual retry")
        return delivery_view(row)


def delivery_view(row):
    return {
        key: iso(getattr(row, key))
        for key in (
            "event_id",
            "event_type",
            "status",
            "attempts",
            "last_error",
            "next_attempt_at",
            "revision",
        )
    }
