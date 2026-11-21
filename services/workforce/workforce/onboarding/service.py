from copy import deepcopy

from sqlalchemy import select

from workforce.domain import Problem, Workforce, changed, iso, owned, permitted, require, revision, serialize
from workforce.models import Assignment, Employee, now
from workforce.onboarding.models import Program, Template


def self_access(actor):
    return any(
        g["role"] == "employee" and g["scope_type"] == "self" and g["scope_id"] == actor.id
        for g in actor.grants
    )


def reader(actor):
    if not permitted(actor, ("hr", "admin")) and not self_access(actor):
        raise Problem(403, "FORBIDDEN", "HR or employee access required")


def assignment_active(assignment):
    # A date-only personnel period includes its final day; timestamps use UTC.
    today = now().date()
    return assignment.starts_on <= today and (assignment.ends_on is None or today <= assignment.ends_on)


def require_active(assignment):
    if not assignment_active(assignment):
        raise Problem(409, "ASSIGNMENT_NOT_ACTIVE", "Personnel assignment is not active today")


class Onboarding:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.workforce = Workforce(session, actor)

    def get(self, id):
        reader(self.actor)
        row = owned(self.session, Program, id, self.actor.organization_id)
        employee = owned(self.session, Employee, row.employee_id, self.actor.organization_id)
        if not permitted(self.actor, ("hr", "admin")) and employee.account_actor_id != self.actor.id:
            raise Problem(404, "NOT_FOUND", "Program not found")
        return row

    def view(self, row):
        assignment = self.session.get(Assignment, row.workforce_assignment_id)
        employee = self.session.get(Employee, row.employee_id)
        result = serialize(row)
        result.pop("created_at")
        result.pop("updated_at")
        result.update(
            completed_count=sum(step["acknowledged_at"] is not None for step in row.steps),
            total_count=len(row.steps),
            assignment_state="active" if assignment_active(assignment) else "inactive",
            account_link_required=employee.account_actor_id is None,
        )
        return result

    def list(self):
        reader(self.actor)
        statement = select(Program).where(Program.organization_id == self.actor.organization_id)
        if not permitted(self.actor, ("hr", "admin")):
            statement = statement.join(Employee, Employee.id == Program.employee_id).where(
                Employee.account_actor_id == self.actor.id,
                Employee.organization_id == self.actor.organization_id,
            )
        return {
            "items": [
                self.view(row)
                for row in self.session.scalars(statement.order_by(Program.created_at, Program.id))
            ]
        }

    def assign(self, body):
        require(self.actor, "hr", "admin")
        assignment = owned(self.session, Assignment, body.workforce_assignment_id, self.actor.organization_id)
        previous = self.session.scalar(
            select(Program).where(
                Program.workforce_assignment_id == assignment.id,
                Program.template_code == body.template_code,
                Program.template_version == body.template_version,
            )
        )
        # Repeating an assignment returns its existing history, including after cancellation.
        if previous:
            return self.view(previous), 200
        require_active(assignment)
        template = self.session.get(Template, (body.template_code, body.template_version))
        if template is None:
            raise Problem(422, "VALIDATION_ERROR", "Unknown template version", "template_code")
        steps = [
            {
                **{k: v for k, v in step.items() if k != "kind"},
                "acknowledged_at": None,
                "acknowledged_by": None,
            }
            for step in deepcopy(template.steps)
        ]
        row = Program(
            organization_id=self.actor.organization_id,
            employee_id=assignment.employee_id,
            workforce_assignment_id=assignment.id,
            template_code=template.code,
            template_version=template.version,
            assigned_by_actor_id=self.actor.id,
            steps=steps,
        )
        self.session.add(row)
        self.workforce.audit("onboarding.assign", row, None, "Introductory programme", row.employee_id)
        return self.view(row), 201

    def acknowledge(self, id, key, body):
        row = self.get(id)
        employee = self.session.get(Employee, row.employee_id)
        if not self_access(self.actor) or employee.account_actor_id != self.actor.id:
            raise Problem(403, "FORBIDDEN", "Only the employee can acknowledge their own step")
        step = next((item for item in row.steps if item["key"] == key), None)
        if step is None:
            raise Problem(404, "NOT_FOUND", "Step not found")
        # Replays are read-only: preserve the original author/time even with an old revision.
        if step["acknowledged_at"] is not None:
            return self.view(row)
        revision(row, body.expected_revision)
        if row.status != "active":
            raise Problem(409, "INVALID_STATE", "Program is not active")
        require_active(self.session.get(Assignment, row.workforce_assignment_id))
        before = serialize(row)
        steps = deepcopy(row.steps)
        target = next(item for item in steps if item["key"] == key)
        target.update(acknowledged_at=iso(now()), acknowledged_by=self.actor.id)
        row.steps = steps
        if all(item["acknowledged_at"] is not None for item in steps):
            row.status = "intro_completed"
        changed(row)
        self.workforce.audit("onboarding.acknowledge", row, before, key, row.employee_id)
        return self.view(row)

    def cancel(self, id, body):
        require(self.actor, "hr", "admin")
        row = self.get(id)
        revision(row, body.expected_revision)
        if row.status == "cancelled":
            raise Problem(409, "INVALID_STATE", "Program is already cancelled")
        before = serialize(row)
        row.status, row.cancel_reason = "cancelled", body.reason
        changed(row)
        self.workforce.audit("onboarding.cancel", row, before, body.reason, row.employee_id)
        return self.view(row)
