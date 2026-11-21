"""Separate host/university outcomes and consent-bound career packages."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from .api import ActorDep, PREFIX
from .core import active, check_revision, fail, now, organizer, read_placement, require
from .schemas import Input, Nonempty, Reason, Revision
from .work import latest_results


class CompletionIn(Reason):
    outcome: Literal["completed", "partial", "stopped"]


class UniversityIn(Revision):
    result: Literal["passed", "not_passed", "unknown"]
    source_reference: Nonempty
    source_author: Nonempty
    occurred_on: date


class InterestIn(Revision):
    interested: StrictBool
    note: str


class PackageIn(Input):
    criterion_keys: list[Nonempty] = Field(min_length=1)
    purpose: Nonempty
    contact_basis: Nonempty

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.criterion_keys)) != len(self.criterion_keys):
            raise ValueError("Критерии повторяются")
        return self


def evidence(unit, placement_id):
    task, submission, review = latest_results(unit, placement_id)
    if task is None:
        return []
    results = {r["criterion_key"]: r for r in review["results"]} if review else {}
    return [{"criterion_key": criterion["key"], "text": criterion["text"], "required": criterion["required"],
             "result": results.get(criterion["key"], {}).get("result", "not_verified"),
             "reason": results.get(criterion["key"], {}).get("reason", "Нет подтверждённого отзыва последней попытки"),
             "task_version_id": task["id"], "task_version": task["version"],
             "submission_id": submission["id"] if submission else None,
             "review_id": review["id"] if review else None,
             "reviewed_by": review["reviewed_by"] if review else None,
             "reviewed_at": review["reviewed_at"] if review else None} for criterion in task["criteria"]]


def install(app, store):
    @app.post(PREFIX + "/placements/{ident}/complete")
    def complete(ident: UUID, body: CompletionIn, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            placement = read_placement(unit, ident)
            require(organizer(actor) or placement["mentor_actor_id"] == actor["actor_id"])
            check_revision(placement, body.expected_revision)
            active(placement)
            snapshot = evidence(unit, ident)
            if body.outcome == "completed" and (not snapshot or any(
                    c["required"] and c["result"] != "confirmed" for c in snapshot)):
                fail("REQUIRED_CRITERIA_UNCONFIRMED", "Обязательные критерии последней попытки не подтверждены.")
            placement["completion"] = {"outcome": body.outcome, "reason": body.reason,
                "actor_id": actor["actor_id"], "completed_at": now(), "criteria_snapshot": snapshot}
            placement["status"] = "stopped" if body.outcome == "stopped" else "completed"
            return unit.save("placement", placement, "completed_" + body.outcome)

    @app.post(PREFIX + "/placements/{ident}/university-result")
    def university(ident: UUID, body: UniversityIn, actor: ActorDep):
        require(organizer(actor))
        with store.transaction(actor, True) as unit:
            placement = read_placement(unit, ident)
            check_revision(placement, body.expected_revision)
            placement["university_result"] = {**body.model_dump(mode="json", exclude={"expected_revision"}),
                "recorded_by": actor["actor_id"], "recorded_at": now(), "source_mode": "registered_external_statement"}
            return unit.save("placement", placement, "university_result_recorded")

    @app.post(PREFIX + "/placements/{ident}/career-interest")
    def interest(ident: UUID, body: InterestIn, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            placement = read_placement(unit, ident)
            require(placement["student_actor_id"] == actor["actor_id"])
            check_revision(placement, body.expected_revision)
            placement["career_interest"] = {"interested": body.interested, "note": body.note,
                                            "actor_id": actor["actor_id"], "recorded_at": now()}
            saved = unit.save("placement", placement, "interest_recorded" if body.interested else "interest_withdrawn")
            if not body.interested:
                for package in unit.all("package"):
                    if package["placement_id"] == str(ident) and not package["interest_withdrawn"]:
                        package["interest_withdrawn"] = True
                        package["interest_withdrawn_at"] = now()
                        unit.save("package", package, "interest_withdrawn")
            return saved

    @app.post(PREFIX + "/placements/{ident}/career-package")
    def package(ident: UUID, body: PackageIn, actor: ActorDep):
        require(organizer(actor))
        with store.transaction(actor, True) as unit:
            placement = read_placement(unit, ident)
            if not placement.get("career_interest", {}).get("interested"):
                fail("CAREER_INTEREST_REQUIRED", "Нет действующего интереса студента.")
            allowed = {r["criterion_key"]: r for r in evidence(unit, ident) if r["result"] == "confirmed"}
            if not set(body.criterion_keys) <= allowed.keys():
                fail("UNCONFIRMED_RESULTS", "Выберите только подтверждённые результаты последней попытки.", 422)
            import uuid
            ident_package = str(uuid.uuid4())
            return unit.save("package", {"id": ident_package, "package_id": ident_package,
                "placement_id": str(ident), "student_actor_id": placement["student_actor_id"],
                "selected_results": [allowed[key] for key in body.criterion_keys],
                "university_result": placement.get("university_result", {"result": "unknown"}),
                "education_status": "unconfirmed", "purpose": body.purpose, "contact_basis": body.contact_basis,
                "transfer_status": "prepared", "interest_withdrawn": False,
                "interest_snapshot": placement["career_interest"]}, "career_package_prepared")

    @app.get(PREFIX + "/career-packages/{ident}")
    def read_package(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = unit.get("package", ident)
            if not organizer(actor) and row["student_actor_id"] != actor["actor_id"]:
                fail("NOT_FOUND", "Пакет не найден.", 404)
            return {**row, "history": unit.history(ident)}
