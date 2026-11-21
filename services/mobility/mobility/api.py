"""Stage 1 mobility API. All identities and assignments are marked training data."""
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .core import (Problem, Settings, Store, check_revision, close_proposals,
                   has_role, in_state, read_interest, require, visible)
from .schemas import InterestIn, OpportunityIn, Reason, Revision

PREFIX = "/api/v1/mobility"


def get_actor(request: Request, authorization: Annotated[str | None, Header()] = None):
    return request.app.state.store.authenticate(authorization)


ActorDep = Annotated[dict, Depends(get_actor)]


def create_app(settings=None):
    store = Store(settings or Settings())

    @asynccontextmanager
    async def lifespan(_app):
        yield
        store.engine.dispose()

    app = FastAPI(title="Internal mobility", version="4C", lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(Problem)
    async def problem(_request, exc):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _exc):
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Проверьте поля запроса."}})

    @app.get("/health")
    def health():
        with store.engine.connect() as connection:
            connection.execute(text("SELECT count(*) FROM mobility_resources"))
        return {"status": "ok", "implementation_stage": 1, "auth_mode": "fixture", "source_mode": "synthetic"}

    @app.post(PREFIX + "/opportunities", status_code=201)
    def create_opportunity(body: OpportunityIn, actor: ActorDep):
        require(has_role(actor, "owner") and str(body.organization_id) == actor["organization_id"]
                and str(body.owner_actor_id) == actor["actor_id"])
        with store.transaction(actor, True) as unit:
            return unit.save("opportunity", {**body.model_dump(mode="json"), "status": "draft"}, "created")

    @app.post(PREFIX + "/opportunities/{ident}/open")
    def open_opportunity(ident: UUID, body: Revision, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row = unit.get("opportunity", ident)
            require(has_role(actor, "owner") and row["owner_actor_id"] == actor["actor_id"])
            check_revision(row, body.expected_revision)
            in_state(row, "draft")
            row["status"] = "open"
            return unit.save("opportunity", row, "opened")

    def opportunity_visible(actor, row):
        return row["owner_actor_id"] == actor["actor_id"] or (has_role(actor, "employee") and row["status"] == "open")

    @app.get(PREFIX + "/opportunities")
    def opportunities(actor: ActorDep):
        with store.transaction(actor) as unit:
            return {"items": [r for r in unit.all("opportunity") if opportunity_visible(actor, r)]}

    @app.get(PREFIX + "/opportunities/{ident}")
    def opportunity(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = unit.get("opportunity", ident)
            visible(opportunity_visible(actor, row))
            return row

    @app.post(PREFIX + "/opportunities/{ident}/interests", status_code=201)
    def interest(ident: UUID, body: InterestIn, actor: ActorDep):
        require(has_role(actor, "employee"))
        with store.transaction(actor, True) as unit:
            row = unit.get("opportunity", ident)
            in_state(row, "open")
            existing = next((i for i in unit.all("interest") if i["opportunity_id"] == str(ident)
                and i["employee_actor_id"] == actor["actor_id"] and i["status"] in {"submitted", "selected"}), None)
            if existing:
                return existing
            return unit.save("interest", {**body.model_dump(), "opportunity_id": str(ident),
                "employee_actor_id": actor["actor_id"], "status": "submitted", "reason": None}, "submitted")

    @app.get(PREFIX + "/interests/{ident}")
    def get_interest(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row, _ = read_interest(unit, ident)
            return {**row, "history": unit.history(ident)}

    @app.get(PREFIX + "/opportunities/{ident}/interests")
    def interests(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = unit.get("opportunity", ident)
            visible(opportunity_visible(actor, row))
            return {"items": [i for i in unit.all("interest") if i["opportunity_id"] == str(ident)
                and (row["owner_actor_id"] == actor["actor_id"] or i["employee_actor_id"] == actor["actor_id"])]}

    @app.post(PREFIX + "/interests/{ident}/withdraw")
    def withdraw(ident: UUID, body: Reason, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row, _ = read_interest(unit, ident)
            require(row["employee_actor_id"] == actor["actor_id"])
            check_revision(row, body.expected_revision)
            in_state(row, "submitted", "selected")
            close_proposals(unit, row["id"], body.reason)
            row.update(status="withdrawn", reason=body.reason)
            return unit.save("interest", row, "withdrawn")

    @app.post(PREFIX + "/interests/{ident}/select")
    def select(ident: UUID, body: Revision, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row, opportunity = read_interest(unit, ident)
            require(opportunity["owner_actor_id"] == actor["actor_id"])
            check_revision(row, body.expected_revision)
            in_state(opportunity, "open")
            in_state(row, "submitted")
            row["status"] = "selected"
            return unit.save("interest", row, "selected")

    @app.post(PREFIX + "/interests/{ident}/decline")
    def decline(ident: UUID, body: Reason, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            row, opportunity = read_interest(unit, ident)
            require(opportunity["owner_actor_id"] == actor["actor_id"])
            check_revision(row, body.expected_revision)
            in_state(row, "submitted", "selected")
            close_proposals(unit, row["id"], body.reason)
            row.update(status="not_selected", reason=body.reason)
            return unit.save("interest", row, "not_selected")

    @app.get(PREFIX + "/session")
    def session(actor: ActorDep):
        return actor

    @app.get(PREFIX + "/colleagues")
    def colleagues(actor: ActorDep):
        return {"items": [
            {k: item[k] for k in ("actor_id", "login", "roles")}
            for item in store.context()["actors"]
            if item["active"] and item["organization_id"] == actor["organization_id"]
        ]}

    @app.get(PREFIX + "/manager-assignments")
    def manager_assignments(actor: ActorDep):
        with store.transaction(actor) as unit:
            owned = {o["id"] for o in unit.all("opportunity") if o["owner_actor_id"] == actor["actor_id"]}
            applicants = {i["employee_actor_id"] for i in unit.all("interest") if i["opportunity_id"] in owned}
        return {"items": [a for a in store.context()["manager_assignments"]
            if a["active"] and a["organization_id"] == actor["organization_id"]
            and (a["employee_actor_id"] == actor["actor_id"] or a["employee_actor_id"] in applicants)]}

    @app.get(PREFIX + "/interests")
    def my_interests(actor: ActorDep):
        with store.transaction(actor) as unit:
            opportunities = {r["id"]: r for r in unit.all("opportunity")}
            return {"items": [r for r in unit.all("interest")
                if r["employee_actor_id"] == actor["actor_id"]
                or opportunities[r["opportunity_id"]]["owner_actor_id"] == actor["actor_id"]]}

    from .agreements import register_agreements
    from .participation import register_participation
    register_agreements(app, store)
    register_participation(app, store)
    return app
