"""Time agreements: each response belongs to the displayed revision and recipient."""
from uuid import UUID

from .api import ActorDep, PREFIX
from .core import (check_revision, fail, has_participation, in_state, now,
                   read_interest, require, visible)
from .schemas import ManagerResponse, ProposalIn, ProposalPatch, Response


def manager_current(store, row):
    return store.manager_assignment(row["organization_id"], row["employee_actor_id"],
                                    row["manager_actor_id"], row["manager_source_reference"]) is not None


def require_assignment(store, row):
    if not manager_current(store, row):
        fail("MANAGER_ASSIGNMENT_UNCONFIRMED", "Нужно действующее назначение другого согласующего из источника.", 422)


def read_proposal(unit, store, ident):
    row = unit.get("proposal", ident)
    direct = unit.actor["actor_id"] in {row["owner_actor_id"], row["employee_actor_id"]}
    manager = (unit.actor["actor_id"] == row["manager_actor_id"] and manager_current(store, row)
               and row["employee_response"] == "accepted")
    visible(direct or manager)
    return row


def editable(unit, row):
    in_state(row, "awaiting_employee", "awaiting_manager", "agreed", "declined")
    if has_participation(unit, row["id"]):
        fail("PARTICIPATION_EXISTS", "Условия начатого участия зафиксированы.")
    interest = unit.get("interest", row["interest_id"])
    in_state(interest, "selected")
    in_state(unit.get("opportunity", interest["opportunity_id"]), "open")


def register_agreements(app, store):
    @app.get(PREFIX + "/proposals")
    def proposals(actor: ActorDep):
        with store.transaction(actor) as unit:
            return {"items": [r for r in unit.all("proposal")
                if actor["actor_id"] in {r["owner_actor_id"], r["employee_actor_id"]}
                or (actor["actor_id"] == r["manager_actor_id"] and manager_current(store, r)
                    and r["employee_response"] == "accepted")]}

    @app.post(PREFIX + "/interests/{ident}/proposal", status_code=201)
    def propose(ident: UUID, body: ProposalIn, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            interest, opportunity = read_interest(unit, ident)
            require(actor["actor_id"] == opportunity["owner_actor_id"])
            in_state(interest, "selected")
            in_state(opportunity, "open")
            data = {**body.model_dump(mode="json"), "interest_id": str(ident),
                    "employee_actor_id": interest["employee_actor_id"],
                    "owner_actor_id": opportunity["owner_actor_id"], "organization_id": actor["organization_id"]}
            require_assignment(store, data)
            previous = next((p for p in unit.all("proposal") if p["interest_id"] == str(ident)
                             and p["status"] != "withdrawn"), None)
            if previous:
                fields = ("starts_on", "ends_on", "time_percent", "manager_actor_id", "manager_source_reference")
                if all(previous[key] == data[key] for key in fields):
                    return previous
                editable(unit, previous)
                if all(previous[key] == data[key] for key in ("manager_actor_id", "manager_source_reference")):
                    fail("PROPOSAL_EXISTS", "Используйте PATCH существующего предложения для изменения условий.")
                # A new confirmed appointment is a new attempt; it never inherits consent.
                previous.update(status="withdrawn", reason="Подтверждён новый адресат или источник назначения")
            data.update(status="awaiting_employee", employee_response=None, manager_response=None, reason=None,
                        employee_response_record=None, manager_response_record=None,
                        conditions_revision=1, supersedes_id=previous["id"] if previous else None)
            new = unit.save("proposal", data, "proposed")
            if previous:
                previous["superseded_by"] = new["id"]
                unit.save("proposal", previous, "manager_reassigned")
            return new

    @app.get(PREFIX + "/proposals/{ident}")
    def proposal(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = read_proposal(unit, store, ident)
            history = unit.history(ident)
            if actor["actor_id"] not in {row["owner_actor_id"], row["employee_actor_id"]}:
                history = [h for h in history if h["snapshot"]["employee_response"] == "accepted"
                           and h["snapshot"]["manager_actor_id"] == actor["actor_id"]
                           and h["snapshot"]["manager_source_reference"] == row["manager_source_reference"]]
            return {**row, "history": history}

    @app.post(PREFIX + "/proposals/{ident}/employee-response")
    def employee_response(ident: UUID, body: Response, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row = unit.get("proposal", ident)
            visible(actor["actor_id"] == row["employee_actor_id"])
            check_revision(row, body.expected_revision)
            editable(unit, row)
            in_state(row, "awaiting_employee")
            require_assignment(store, row)
            row.update(employee_response="accepted" if body.accepted else "declined",
                       status="awaiting_manager" if body.accepted else "declined", reason=body.reason,
                       employee_response_record={"actor_id": actor["actor_id"], "accepted": body.accepted,
                           "reason": body.reason, "conditions_revision": row["conditions_revision"],
                           "expected_revision": body.expected_revision, "recorded_at": now()})
            return unit.save("proposal", row, "employee_responded")

    @app.post(PREFIX + "/proposals/{ident}/manager-response")
    def manager_response(ident: UUID, body: ManagerResponse, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row = unit.get("proposal", ident)
            visible(actor["actor_id"] == row["manager_actor_id"] and manager_current(store, row))
            check_revision(row, body.expected_revision)
            editable(unit, row)
            in_state(row, "awaiting_manager")
            require(row["employee_response"] == "accepted" and actor["actor_id"] != row["employee_actor_id"])
            row.update(manager_response="accepted" if body.accepted else "declined",
                       status="agreed" if body.accepted else "declined", reason=body.reason,
                       manager_response_record={"actor_id": actor["actor_id"], "accepted": body.accepted,
                           "reason": body.reason, "conditions_revision": row["conditions_revision"],
                           "expected_revision": body.expected_revision, "recorded_at": now()})
            return unit.save("proposal", row, "manager_responded")

    @app.patch(PREFIX + "/proposals/{ident}")
    def amend(ident: UUID, body: ProposalPatch, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row = read_proposal(unit, store, ident)
            require(actor["actor_id"] == row["owner_actor_id"])
            check_revision(row, body.expected_revision)
            editable(unit, row)
            require_assignment(store, row)
            changes = body.model_dump(mode="json", exclude_unset=True, exclude={"expected_revision", "reason"})
            if not any(row[key] != value for key, value in changes.items()):
                fail("UNCHANGED_CONDITIONS", "Нужны изменённые условия.", 422)
            row.update(changes)
            if row["ends_on"] < row["starts_on"]:
                fail("INVALID_PERIOD", "Конец периода предшествует началу.", 422)
            row.update(status="awaiting_employee", employee_response=None, manager_response=None,
                       employee_response_record=None, manager_response_record=None, reason=body.reason,
                       conditions_revision=row["conditions_revision"] + 1)
            return unit.save("proposal", row, "conditions_changed")
