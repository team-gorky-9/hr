"""Agreed participation, selected evidence and separate permanent-vacancy interest."""
from uuid import UUID

from .api import ActorDep, PREFIX
from .agreements import manager_current, read_proposal, require_assignment
from .core import (check_revision, has_participation, has_role, in_state,
                   now, require, visible)
from .schemas import Consideration, Feedback, Finish, PackageIn, Revision, VacancyInterestIn


def read_participation(unit, store, ident):
    row = unit.get("participation", ident)
    direct = unit.actor["actor_id"] in {row["employee_actor_id"], row["owner_actor_id"]}
    manager = unit.actor["actor_id"] == row["manager_actor_id"] and manager_current(store, row)
    visible(direct or manager)
    return row


def read_vacancy_interest(unit, ident):
    row = unit.get("vacancy_interest", ident)
    visible(unit.actor["actor_id"] == row["employee_actor_id"] or has_role(unit.actor, "hr"))
    return row


def register_participation(app, store):
    @app.get(PREFIX + "/participations")
    def participations(actor: ActorDep):
        with store.transaction(actor) as unit:
            return {"items": [r for r in unit.all("participation")
                if actor["actor_id"] in {r["employee_actor_id"], r["owner_actor_id"]}
                or (actor["actor_id"] == r["manager_actor_id"] and manager_current(store, r))]}

    @app.get(PREFIX + "/vacancy-interests")
    def vacancy_interests(actor: ActorDep):
        with store.transaction(actor) as unit:
            return {"items": [r for r in unit.all("vacancy_interest")
                if r["employee_actor_id"] == actor["actor_id"] or has_role(actor, "hr")]}

    @app.post(PREFIX + "/proposals/{ident}/start", status_code=201)
    def start(ident: UUID, body: Revision, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            proposal = read_proposal(unit, store, ident)
            require(actor["actor_id"] == proposal["owner_actor_id"])
            check_revision(proposal, body.expected_revision)
            existing = has_participation(unit, str(ident))
            if existing:
                return existing
            in_state(proposal, "agreed")
            require_assignment(store, proposal)
            interest = unit.get("interest", proposal["interest_id"])
            in_state(interest, "selected")
            opportunity = unit.get("opportunity", interest["opportunity_id"])
            in_state(opportunity, "open")
            require(proposal["employee_response"] == proposal["manager_response"] == "accepted")
            keys = ("employee_actor_id", "owner_actor_id", "manager_actor_id", "manager_source_reference",
                    "starts_on", "ends_on", "time_percent", "conditions_revision")
            return unit.save("participation", {**{k: proposal[k] for k in keys},
                "proposal_id": proposal["id"], "proposal_revision": proposal["revision"],
                "opportunity_id": opportunity["id"], "opportunity_title": opportunity["title"],
                "status": "active", "result_note": None, "owner_result": None, "employee_feedback": None}, "started")

    @app.get(PREFIX + "/participations/{ident}")
    def participation(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = read_participation(unit, store, ident)
            result = {**row, "history": unit.history(ident)}
            if actor["actor_id"] == row["employee_actor_id"]:
                result["result_packages"] = [p for p in unit.all("result_package") if p["participation_id"] == row["id"]]
            return result

    @app.post(PREFIX + "/participations/{ident}/finish")
    def finish(ident: UUID, body: Finish, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row = read_participation(unit, store, ident)
            require(actor["actor_id"] == row["owner_actor_id"])
            check_revision(row, body.expected_revision)
            in_state(row, "active")
            row.update(status=body.outcome, result_note=body.result_note,
                       owner_result={"actor_id": actor["actor_id"], "recorded_at": now(),
                                     "outcome": body.outcome, "result_note": body.result_note})
            return unit.save("participation", row, "finished")

    @app.post(PREFIX + "/participations/{ident}/employee-feedback")
    def feedback(ident: UUID, body: Feedback, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row = read_participation(unit, store, ident)
            require(actor["actor_id"] == row["employee_actor_id"])
            check_revision(row, body.expected_revision)
            in_state(row, "completed", "stopped")
            row["employee_feedback"] = {"actor_id": actor["actor_id"], "accepted": body.accepted,
                                        "note": body.note, "recorded_at": now()}
            return unit.save("participation", row, "employee_feedback")

    @app.post(PREFIX + "/participations/{ident}/result-package", status_code=201)
    def result_package(ident: UUID, body: PackageIn, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row = read_participation(unit, store, ident)
            require(actor["actor_id"] == row["employee_actor_id"])
            in_state(row, "completed", "stopped")
            existing = next((p for p in unit.all("result_package") if p["participation_id"] == row["id"]
                and p["participation_revision"] == row["revision"] and p["purpose"] == body.purpose
                and p["share_allowed"] == body.share_allowed), None)
            if existing:
                return existing
            # Explicit allowlist: personal interest and time-approval reasons are never exported.
            keys = ("employee_actor_id", "opportunity_id", "opportunity_title", "starts_on", "ends_on",
                    "time_percent", "status", "owner_result", "employee_feedback")
            return unit.save("result_package", {**body.model_dump(), "participation_id": row["id"],
                "participation_revision": row["revision"], "source_mode": "mobility_result_snapshot",
                "delivery_status": "not_sent", "evidence": {k: row[k] for k in keys}}, "package_prepared")

    @app.post(PREFIX + "/vacancy-interests", status_code=201)
    def vacancy_interest(body: VacancyInterestIn, actor: ActorDep):
        require(has_role(actor, "employee"))
        with store.transaction(actor, True) as unit:
            existing = next((r for r in unit.all("vacancy_interest") if r["employee_actor_id"] == actor["actor_id"]
                and r["vacancy_ref"] == body.vacancy_ref and r["publication_revision"] == body.publication_revision), None)
            if existing:
                return existing
            return unit.save("vacancy_interest", {**body.model_dump(), "employee_actor_id": actor["actor_id"],
                "status": "prepared", "source_mode": "employee_statement", "consideration_ref": None,
                "confirmation_basis": None, "confirmed_by": None, "confirmed_at": None}, "prepared")

    @app.get(PREFIX + "/vacancy-interests/{ident}")
    def get_vacancy_interest(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = read_vacancy_interest(unit, ident)
            return {**row, "history": unit.history(ident)}

    @app.post(PREFIX + "/vacancy-interests/{ident}/record-consideration")
    def record_consideration(ident: UUID, body: Consideration, actor: ActorDep):
        require(has_role(actor, "hr"))
        with store.transaction(actor, True) as unit:
            row = read_vacancy_interest(unit, ident)
            check_revision(row, body.expected_revision)
            in_state(row, "prepared")
            row.update(status="recorded", source_mode="manual-confirmed", consideration_ref=body.consideration_ref,
                       confirmation_basis=body.confirmation_basis, confirmed_by=actor["actor_id"], confirmed_at=now())
            return unit.save("vacancy_interest", row, "consideration_recorded")
