from copy import deepcopy

from sqlalchemy import func, or_, select

from workforce.development import schemas as s
from workforce.development.models import Goal, GoalVersion, Plan, ResultPackage, Review, Submission
from workforce.domain import Problem, changed, iso, owned, revision, serialize
from workforce.models import Actor, Department, now
from workforce.onboarding.service import self_access


def missing():
    raise Problem(404, "NOT_FOUND", "Development object not found")


def state(row, *allowed):
    if row.status not in allowed:
        raise Problem(409, "INVALID_STATE", "Operation is not allowed in this state")


class Development:
    def __init__(self, session, actor):
        self.session, self.actor = session, actor

    def save(self, row):
        self.session.add(row)
        self.session.flush()
        return serialize(row)

    def save_goal(self, row):
        snapshot = self.save(row)
        self.session.add(GoalVersion(goal_id=row.id, revision=row.revision, snapshot=snapshot))
        self.session.flush()
        return snapshot

    def participant_filter(self):
        return or_(
            Plan.owner_actor_id == self.actor.id,
            Plan.manager_actor_id == self.actor.id,
            Plan.reviewer_actor_id == self.actor.id,
        )

    def goal_filter(self):
        return or_(
            Goal.owner_actor_id == self.actor.id,
            (Goal.status == "shared") & (Goal.shared_with_actor_id == self.actor.id),
        )

    def goal(self, id):
        row = self.session.scalar(
            select(Goal).where(
                Goal.id == str(id),
                Goal.organization_id == self.actor.organization_id,
                self.goal_filter(),
            )
        )
        if row is None:
            missing()
        return row

    def plan(self, id):
        row = self.session.scalar(
            select(Plan).where(
                Plan.id == str(id),
                Plan.organization_id == self.actor.organization_id,
                self.participant_filter(),
            )
        )
        if row is None:
            missing()
        return row

    def owner(self, row):
        if row.owner_actor_id != self.actor.id:
            missing()

    def department_actor(self, id, owner_id):
        candidate = owned(self.session, Actor, id, self.actor.organization_id)
        if not candidate.active or candidate.id == owner_id:
            raise Problem(422, "INVALID_PARTICIPANT", "Participant must be active and different from owner")
        grants = []
        for grant in candidate.grants:
            if grant["role"] != "department" or grant["scope_type"] != "department":
                continue
            department = self.session.get(Department, grant["scope_id"])
            if department and department.organization_id == candidate.organization_id:
                grants.append(deepcopy(grant))
        if not grants:
            raise Problem(
                422, "INVALID_PARTICIPANT", "A department assignment in this organization is required"
            )
        return {"actor_id": candidate.id, "organization_id": candidate.organization_id, "grants": grants}

    def goals(self):
        return {
            "items": [
                serialize(row)
                for row in self.session.scalars(
                    select(Goal)
                    .where(
                        Goal.organization_id == self.actor.organization_id,
                        self.goal_filter(),
                    )
                    .order_by(Goal.created_at, Goal.id)
                )
            ]
        }

    def plans(self):
        return {
            "items": [
                serialize(row)
                for row in self.session.scalars(
                    select(Plan)
                    .where(
                        Plan.organization_id == self.actor.organization_id,
                        self.participant_filter(),
                    )
                    .order_by(Plan.created_at, Plan.id)
                )
            ]
        }

    def create_goal(self, body):
        if not self_access(self.actor):
            raise Problem(403, "FORBIDDEN", "Employee self grant required")
        return self.save_goal(
            Goal(
                organization_id=self.actor.organization_id, owner_actor_id=self.actor.id, **body.model_dump()
            )
        )

    def patch_goal(self, id, body):
        row = self.goal(id)
        self.owner(row)
        revision(row, body.expected_revision)
        for key, value in body.model_dump(exclude_unset=True, exclude={"expected_revision"}).items():
            setattr(row, key, value)
        # Editing is a new private draft. An old share must not expose unsent personal text.
        row.status, row.shared_with_actor_id, row.share_basis = "private", None, None
        changed(row)
        return self.save_goal(row)

    def share_goal(self, id, body):
        row = self.goal(id)
        self.owner(row)
        revision(row, body.expected_revision)
        recipient = self.department_actor(body.recipient_actor_id, row.owner_actor_id)
        row.status, row.shared_with_actor_id = "shared", str(body.recipient_actor_id)
        row.share_basis = {"shared_by": self.actor.id, "shared_at": iso(now()), "recipient": recipient}
        changed(row)
        return self.save_goal(row)

    def create_plan(self, body):
        goal = self.goal(body.goal_id)
        if goal.status != "shared" or goal.shared_with_actor_id != self.actor.id:
            missing()
        revision(goal, body.goal_revision)
        manager = self.department_actor(self.actor.id, goal.owner_actor_id)
        reviewer = self.department_actor(body.reviewer_actor_id, goal.owner_actor_id)
        data = body.model_dump(mode="json", exclude={"goal_id", "goal_revision"})
        return self.save(
            Plan(
                organization_id=goal.organization_id,
                goal_id=goal.id,
                goal_revision=goal.revision,
                goal_snapshot=s.GoalView.model_validate(serialize(goal)).model_dump(mode="json"),
                owner_actor_id=goal.owner_actor_id,
                manager_actor_id=self.actor.id,
                assignment_basis={
                    "share": deepcopy(goal.share_basis),
                    "manager": manager,
                    "reviewer": reviewer,
                    "assigned_by": self.actor.id,
                    "assigned_at": iso(now()),
                },
                **data,
            )
        )

    def patch_plan(self, id, body):
        row = self.plan(id)
        if row.manager_actor_id != self.actor.id:
            missing()
        self.department_actor(self.actor.id, row.owner_actor_id)
        revision(row, body.expected_revision)
        state(row, "proposed", "returned")
        data = body.model_dump(mode="json", exclude_unset=True, exclude={"expected_revision"})
        try:
            s.validate_plan(data.get("criteria", row.criteria), data.get("activities", row.activities))
        except ValueError as exc:
            raise Problem(422, "VALIDATION_ERROR", str(exc)) from exc
        if "reviewer_actor_id" in data:
            reviewer = self.department_actor(data["reviewer_actor_id"], row.owner_actor_id)
            row.assignment_basis = {
                **row.assignment_basis,
                "reviewer": reviewer,
                "assigned_by": self.actor.id,
                "assigned_at": iso(now()),
            }
        for key, value in data.items():
            setattr(row, key, value)
        row.status = "proposed"
        changed(row)
        return self.save(row)

    def submit(self, id, body):
        plan = self.plan(id)
        self.owner(plan)
        state(plan, "active")
        activity = next((item for item in plan.activities if item["key"] == body.activity_key), None)
        if activity is None or not set(body.criterion_keys) <= set(activity["criterion_keys"]):
            raise Problem(422, "VALIDATION_ERROR", "Criteria must belong to this plan activity")
        attempt = (
            self.session.scalar(
                select(func.max(Submission.attempt_no)).where(
                    Submission.plan_id == plan.id,
                    Submission.activity_key == body.activity_key,
                )
            )
            or 0
        )
        sequence = (
            self.session.scalar(
                select(func.max(Submission.sequence_no)).where(
                    Submission.plan_id == plan.id,
                )
            )
            or 0
        )
        return self.save(
            Submission(
                plan_id=plan.id,
                plan_revision=plan.agreed_revision,
                created_by=self.actor.id,
                attempt_no=attempt + 1,
                sequence_no=sequence + 1,
                **body.model_dump(mode="json"),
            )
        )

    def submission_history(self, plan):
        rows = self.session.execute(
            select(Submission, Review)
            .outerjoin(
                Review,
                Review.submission_id == Submission.id,
            )
            .where(Submission.plan_id == plan.id)
            .order_by(Submission.sequence_no)
        ).all()
        return [
            {**serialize(submission), "review": serialize(review) if review else None}
            for submission, review in rows
        ]

    def submissions(self, id):
        return {"items": self.submission_history(self.plan(id))}

    def review(self, id, body):
        submission = self.session.get(Submission, str(id))
        if submission is None:
            missing()
        plan = self.plan(submission.plan_id)
        if plan.reviewer_actor_id != self.actor.id or submission.created_by == self.actor.id:
            missing()
        self.department_actor(self.actor.id, plan.owner_actor_id)
        results = sorted(body.model_dump(mode="json")["results"], key=lambda item: item["criterion_key"])
        previous = self.session.scalar(select(Review).where(Review.submission_id == submission.id))
        if previous:
            if previous.results != results:
                raise Problem(409, "REVIEW_EXISTS", "This attempt already has a different review")
            return serialize(previous), 200
        state(plan, "active")
        if {item["criterion_key"] for item in results} != set(submission.criterion_keys):
            raise Problem(422, "VALIDATION_ERROR", "Review must cover every submitted criterion exactly once")
        return self.save(
            Review(submission_id=submission.id, reviewer_actor_id=self.actor.id, results=results)
        ), 201

    def progress(self, id):
        plan = self.plan(id)
        criteria = {item["key"]: {"key": item["key"], "state": "unsubmitted"} for item in plan.criteria}
        # Ordered across the plan, even when two different activities target the same criterion.
        for submission in self.submission_history(plan):
            review = submission["review"]
            results = {item["criterion_key"]: item for item in review["results"]} if review else {}
            for key in submission["criterion_keys"]:
                criteria[key] = {
                    "key": key,
                    "state": results[key]["result"] if review else "waiting",
                    "submission_id": submission["id"],
                    "review_id": review["id"] if review else None,
                }
        return {
            "criteria": list(criteria.values()),
            "completed_count": sum(item["state"] == "confirmed" for item in criteria.values()),
            "total_count": len(criteria),
        }

    def respond(self, id, body):
        row = self.plan(id)
        self.owner(row)
        revision(row, body.expected_revision)
        state(row, "proposed")
        row.status = "active" if body.decision == "accept" else "returned"
        row.decision_note = body.note
        changed(row)
        if row.status == "active":
            self.department_actor(row.manager_actor_id, row.owner_actor_id)
            self.department_actor(row.reviewer_actor_id, row.owner_actor_id)
            row.agreed_revision = row.revision
        return self.save(row)

    def close(self, id, body):
        plan = self.plan(id)
        if self.actor.id not in {plan.owner_actor_id, plan.manager_actor_id}:
            missing()
        if self.actor.id == plan.manager_actor_id:
            self.department_actor(self.actor.id, plan.owner_actor_id)
        revision(plan, body.expected_revision)
        state(plan, "active")
        progress = {item["key"]: item for item in self.progress(id)["criteria"]}
        snapshot = [{**deepcopy(criterion), **progress[criterion["key"]]} for criterion in plan.criteria]
        if body.outcome == "reached" and any(
            item["required"] and item["state"] != "confirmed" for item in snapshot
        ):
            raise Problem(409, "REQUIRED_CRITERIA_OPEN", "All required criteria must be confirmed")
        plan.closure = {
            "outcome": body.outcome,
            "reason": body.reason,
            "actor_id": self.actor.id,
            "closed_at": iso(now()),
            "criteria_snapshot": snapshot,
        }
        plan.status = "closed"
        changed(plan)
        return self.save(plan)

    @staticmethod
    def package_view(package):
        result = serialize(package)
        result["package_id"] = result.pop("id")
        return result

    def share_result(self, id, body):
        plan = self.plan(id)
        self.owner(plan)
        state(plan, "closed")
        criteria = {item["key"]: item for item in plan.closure["criteria_snapshot"]}
        if not set(body.criterion_keys) <= criteria.keys():
            raise Problem(422, "VALIDATION_ERROR", "Unknown criterion in this plan")
        if any(criteria[key]["state"] != "confirmed" for key in body.criterion_keys):
            raise Problem(409, "RESULT_NOT_CONFIRMED", "Only confirmed results can be selected")
        items, mutable = [], []
        for key in body.criterion_keys:
            criterion = criteria[key]
            submission = self.session.get(Submission, criterion["submission_id"])
            review = self.session.get(Review, criterion["review_id"])
            items.append(
                {
                    "criterion_key": key,
                    "criterion_text": criterion["text"],
                    "result": "confirmed",
                    "source_submission_id": submission.id,
                    "source_author_actor_id": submission.created_by,
                    "review_id": review.id,
                    "reviewer_actor_id": review.reviewer_actor_id,
                    "reviewed_at": iso(review.created_at),
                }
            )
            if submission.artifact["mutable_source"]:
                mutable.append(key)
        package = ResultPackage(
            organization_id=plan.organization_id,
            plan_id=plan.id,
            owner_actor_id=plan.owner_actor_id,
            purpose=body.purpose,
            items=items,
            limitations={
                "plan_outcome": plan.closure["outcome"],
                "delivery_status": "not_sent",
                "mutable_source_criterion_keys": mutable,
                "note": "Prepared for manual transfer; source access is not granted. "
                "This is evidence for selected criteria, not an overall competence level.",
            },
        )
        self.save(package)
        return self.package_view(package)

    def package(self, id):
        package = owned(self.session, ResultPackage, id, self.actor.organization_id)
        self.owner(package)
        return self.package_view(package)
