"""Students HTTP API."""
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .core import (Problem, Settings, Store, active, check_revision, fail, mentor_available,
                   candidate, organizer, placement_visible, read_placement, require)
from .schemas import ApplicationIn, Assignment, OpportunityIn, Reason, Revision

PREFIX = "/api/v1/students"


def get_actor(request: Request, authorization: Annotated[str | None, Header()] = None):
    return request.app.state.store.authenticate(authorization)


ActorDep = Annotated[dict, Depends(get_actor)]


def create_app(settings=None):
    store = Store(settings or Settings())

    @asynccontextmanager
    async def lifespan(_app):
        yield
        store.engine.dispose()

    app = FastAPI(title="Student practice", version="3C", lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(Problem)
    async def problem(_request, exc):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _exc):
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Проверьте поля запроса."}})

    @app.get("/health")
    def health():
        return {"status": "ok", "implementation_stage": 1, "auth_mode": store.settings.auth_mode,
                "integration_mode": "standalone", "mentor_capacity": store.settings.mentor_capacity}

    @app.post(PREFIX + "/opportunities", status_code=201)
    def create_opportunity(body: OpportunityIn, actor: ActorDep):
        require(organizer(actor))
        store.mentor(actor, body.mentor_actor_id)
        with store.transaction(actor, True) as unit:
            return unit.save("opportunity", {**body.model_dump(mode="json"), "status": "draft", "is_synthetic": True}, "created")

    @app.post(PREFIX + "/opportunities/{ident}/publish")
    def publish(ident: UUID, body: Revision, actor: ActorDep):
        require(organizer(actor))
        with store.transaction(actor, True) as unit:
            opportunity = unit.get("opportunity", ident)
            check_revision(opportunity, body.expected_revision)
            if opportunity["status"] != "draft":
                fail("INVALID_STATE", "Можно опубликовать только черновик.")
            opportunity["status"] = "published"
            return unit.save("opportunity", opportunity, "published")

    @app.post(PREFIX + "/opportunities/{ident}/close")
    def close_opportunity(ident: UUID, body: Reason, actor: ActorDep):
        require(organizer(actor))
        with store.transaction(actor, True) as unit:
            opportunity = unit.get("opportunity", ident)
            check_revision(opportunity, body.expected_revision)
            if opportunity["status"] != "published":
                fail("INVALID_STATE", "Можно закрыть только опубликованное место.")
            for kind, status in (("application", "submitted"), ("placement", "active")):
                if any(row["opportunity_id"] == str(ident) and row["status"] == status for row in unit.all(kind)):
                    fail("OPPORTUNITY_IN_USE", "Сначала завершите открытые заявки или участия.")
            opportunity.update(status="closed", close_reason=body.reason)
            return unit.save("opportunity", opportunity, "closed")

    @app.get(PREFIX + "/opportunities")
    def opportunities(actor: ActorDep):
        require(organizer(actor) or candidate(actor))
        with store.transaction(actor) as unit:
            placements = unit.all("placement")
            items = []
            for opportunity in unit.all("opportunity"):
                used = sum(p["opportunity_id"] == opportunity["id"] for p in placements)
                opportunity["available_places"] = max(0, opportunity["capacity"] - used) if opportunity["status"] != "closed" else 0
                if organizer(actor) or (opportunity["status"] == "published" and opportunity["available_places"]):
                    items.append(opportunity)
            return {"items": items}

    @app.post(PREFIX + "/applications", status_code=201)
    def apply(body: ApplicationIn, actor: ActorDep):
        require(candidate(actor))
        with store.transaction(actor, True) as unit:
            opportunity = unit.get("opportunity", body.opportunity_id)
            if opportunity["status"] != "published":
                fail("INVALID_STATE", "Место не опубликовано.")
            existing = next((a for a in unit.all("application") if a["opportunity_id"] == str(body.opportunity_id)
                             and a["student_actor_id"] == actor["actor_id"] and a["status"] in {"submitted", "assigned"}), None)
            if existing:
                fail("APPLICATION_EXISTS", "На это место уже есть открытая заявка.")
            return unit.save("application", {**body.model_dump(mode="json"), "student_actor_id": actor["actor_id"],
                             "status": "submitted", "reason": None, "source_mode": "synthetic_student_statement"}, "submitted")

    def visible_application(unit, ident):
        row = unit.get("application", ident)
        if not organizer(unit.actor) and row["student_actor_id"] != unit.actor["actor_id"]:
            fail("NOT_FOUND", "Заявка не найдена.", 404)
        return row

    @app.get(PREFIX + "/applications")
    def applications(actor: ActorDep):
        with store.transaction(actor) as unit:
            return {"items": [a for a in unit.all("application") if organizer(actor) or a["student_actor_id"] == actor["actor_id"]]}

    @app.get(PREFIX + "/applications/{ident}")
    def application(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = visible_application(unit, ident)
            return {**row, "history": unit.history(ident)}

    def finish_application(ident, body, actor, withdrawal):
        with store.transaction(actor, True) as unit:
            row = visible_application(unit, ident)
            require(row["student_actor_id"] == actor["actor_id"] if withdrawal else organizer(actor))
            check_revision(row, body.expected_revision)
            if row["status"] != "submitted":
                fail("INVALID_STATE", "Заявка уже рассмотрена или отозвана.")
            row.update(status="withdrawn" if withdrawal else "not_assigned", reason=body.reason)
            return unit.save("application", row, row["status"])

    @app.post(PREFIX + "/applications/{ident}/withdraw")
    def withdraw(ident: UUID, body: Reason, actor: ActorDep):
        return finish_application(ident, body, actor, True)

    @app.post(PREFIX + "/applications/{ident}/decline")
    def decline(ident: UUID, body: Reason, actor: ActorDep):
        return finish_application(ident, body, actor, False)

    @app.post(PREFIX + "/applications/{ident}/assign")
    def assign(ident: UUID, body: Assignment, actor: ActorDep):
        require(organizer(actor))
        with store.transaction(actor, True) as unit:
            row = unit.get("application", ident)
            placements = unit.all("placement")
            previous = next((p for p in placements if p["application_id"] == str(ident)), None)
            if previous:
                return previous
            check_revision(row, body.expected_revision)
            if row["status"] != "submitted":
                fail("INVALID_STATE", "Назначить можно только поданную заявку.")
            opportunity = unit.get("opportunity", row["opportunity_id"])
            if opportunity["status"] != "published":
                fail("INVALID_STATE", "Место не опубликовано.")
            if sum(p["opportunity_id"] == opportunity["id"] for p in placements) >= opportunity["capacity"]:
                fail("CAPACITY_UNAVAILABLE", "Свободных мест нет; заявка сохранена.")
            store.mentor(actor, opportunity["mentor_actor_id"])
            mentor_available(unit, opportunity["mentor_actor_id"], opportunity["starts_on"], opportunity["ends_on"],
                             store.settings.mentor_capacity)
            placement = unit.save("placement", {"application_id": row["id"], "opportunity_id": opportunity["id"],
                "student_actor_id": row["student_actor_id"], "mentor_actor_id": opportunity["mentor_actor_id"],
                "starts_on": opportunity["starts_on"], "ends_on": opportunity["ends_on"], "status": "active",
                "confirmation_basis": body.confirmation_basis, "source_mode": "synthetic_manual_confirmation"}, "assigned")
            row["status"] = "assigned"
            unit.save("application", row, "assigned")
            return placement

    @app.get(PREFIX + "/placements")
    def placements(actor: ActorDep):
        with store.transaction(actor) as unit:
            return {"items": [p for p in unit.all("placement") if placement_visible(actor, p)]}

    @app.get(PREFIX + "/placements/{ident}")
    def placement(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            row = read_placement(unit, ident)
            from .work import work_state
            return {**row, "history": unit.history(ident), "work_state": work_state(unit, ident),
                    "university_result": row.get("university_result", {"result": "unknown"}),
                    "career_interest": row.get("career_interest", {"interested": False})}

    from .work import install
    install(app, store)
    from .results import install as install_results
    install_results(app, store)
    return app
