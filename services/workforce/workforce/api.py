import hashlib
import secrets
from datetime import UTC, date, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from alembic.script import ScriptDirectory
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from workforce import schemas as s
from workforce.config import Settings
from workforce.database import make_engine, migration_config, verify_password
from workforce.domain import (
    Problem,
    Workforce,
    actor_view,
    delivery_view,
    digest,
    lock_organization,
    owned,
    page,
    permitted,
    require,
    revision,
    serialize,
)
from workforce.models import (
    Actor,
    Assignment,
    Audit,
    Command,
    Delegation,
    Department,
    Employee,
    Intake,
    LoginSession,
    Outbox,
    SourceRef,
    now,
)

Limit = Annotated[int, Query(ge=1, le=100)]


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def expired(stored):
    # SQLite returns naive timestamps; PostgreSQL preserves the server's zone.
    # Attach UTC only to naive values, never relabel a zoned local timestamp.
    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now()


def authenticate(session, request):
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Problem(401, "AUTH_REQUIRED", "Bearer session required")
    if request.app.state.settings.auth_mode == "fixture" and token.startswith("fixture:"):
        actor = session.scalar(select(Actor).where(Actor.login == token[8:], Actor.active.is_(True)))
        if actor:
            return actor
    stored = session.get(LoginSession, token_hash(token))
    if stored is None or stored.revoked or expired(stored):
        raise Problem(401, "INVALID_SESSION", "Session expired or revoked")
    actor = session.get(Actor, stored.actor_id)
    if not actor or not actor.active:
        raise Problem(401, "INVALID_SESSION", "Actor is inactive")
    return actor


def command_key(request):
    try:
        return str(UUID(request.headers.get("Idempotency-Key", "")))
    except ValueError as exc:
        raise Problem(422, "VALIDATION_ERROR", "Idempotency-Key UUID is required", "Idempotency-Key") from exc


def execute(request, body, action, model=None, id=None, status=200, roles=("hr", "admin")):
    with Session(request.app.state.engine) as session, session.begin():
        actor = authenticate(session, request)
        lock_organization(session, actor.organization_id)
        require(actor, *roles)
        service = Workforce(session, actor)
        if model is Outbox:
            row = session.scalar(
                select(Outbox)
                .where(Outbox.event_id == str(id), Outbox.organization_id == actor.organization_id)
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "NOT_FOUND", "Delivery not found")
        else:
            row = service.get(model, id) if model else None
        key = command_key(request)
        scope = digest([actor.id, actor.organization_id, request.method, request.url.path, key])
        fingerprint = digest(body.model_dump(mode="json", exclude_unset=True))
        previous = session.get(Command, scope)
        if previous:
            if previous.fingerprint != fingerprint:
                raise Problem(409, "IDEMPOTENCY_CONFLICT", "Key belongs to a different command")
            return JSONResponse(
                previous.result, status_code=previous.status_code, headers={"Idempotency-Replayed": "true"}
            )
        if hasattr(body, "expected_revision"):
            revision(row, body.expected_revision)
        result = getattr(service, action)(body, row)
        session.add(Command(scope=scope, fingerprint=fingerprint, status_code=status, result=result))
        session.flush()
        return JSONResponse(result, status_code=status)


def create_app(settings=None):
    from workforce.development.api import router as development_router
    from workforce.onboarding.api import router as onboarding_router

    settings = settings or Settings()
    app = FastAPI(title="Workforce", version="1.0")
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.migration_head = ScriptDirectory.from_config(migration_config()).get_current_head()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(Problem)
    async def problem_response(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "field": exc.field,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_response(request, exc):
        errors = exc.errors()
        field = ".".join(str(item) for item in errors[0]["loc"]) if errors else None
        return await problem_response(
            request, Problem(422, "VALIDATION_ERROR", "Invalid request fields", field)
        )

    @app.exception_handler(IntegrityError)
    async def integrity_response(request, exc):
        return await problem_response(
            request, Problem(409, "INVALID_STATE", "Conflicting source, actor link or resource")
        )

    @app.exception_handler(OperationalError)
    async def database_response(request, exc):
        return await problem_response(
            request, Problem(503, "DEPENDENCY_UNAVAILABLE", "Database is unavailable")
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "auth_mode": settings.auth_mode}

    @app.get("/ready")
    def ready():
        with app.state.engine.connect() as connection:
            if not inspect(connection).has_table("alembic_version"):
                raise Problem(503, "DEPENDENCY_UNAVAILABLE", "Database migrations are not installed")
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if version != app.state.migration_head:
                raise Problem(503, "DEPENDENCY_UNAVAILABLE", "Database migrations are not current")
        from workforce.worker import broker_available

        return {"status": "ok", "broker": "available" if broker_available(settings) else "unavailable"}

    @app.post("/api/v1/sessions", status_code=201)
    def login(body: s.Login, request: Request):
        with Session(app.state.engine) as session, session.begin():
            actor = session.scalar(select(Actor).where(Actor.login == body.login))
            if actor is None or not actor.active or not verify_password(body.password, actor.password_hash):
                raise Problem(401, "INVALID_CREDENTIALS", "Invalid credentials")
            lock_organization(session, actor.organization_id)
            scope = digest([actor.id, actor.organization_id, "POST", request.url.path, command_key(request)])
            fingerprint = digest(body.model_dump(mode="json"))
            previous = session.get(Command, scope)
            if previous:
                if previous.fingerprint != fingerprint:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "Key belongs to another login request")
                stored = session.get(LoginSession, token_hash(previous.result["access_token"]))
                if stored is None or stored.revoked or expired(stored):
                    raise Problem(401, "INVALID_SESSION", "Replayed session is no longer valid")
                return JSONResponse(
                    previous.result, status_code=201, headers={"Idempotency-Replayed": "true"}
                )
            token = secrets.token_urlsafe(32)
            expires = now() + timedelta(hours=settings.session_hours)
            session.add(LoginSession(token_hash=token_hash(token), actor_id=actor.id, expires_at=expires))
            result = {
                "access_token": token,
                "token_type": "bearer",
                "expires_at": expires.isoformat(),
                "actor": actor_view(actor),
            }
            session.add(Command(scope=scope, fingerprint=fingerprint, status_code=201, result=result))
            return result

    @app.get("/api/v1/session")
    def current_session(request: Request):
        with Session(app.state.engine) as session:
            return actor_view(authenticate(session, request))

    @app.delete("/api/v1/session", status_code=204)
    def logout(request: Request):
        with Session(app.state.engine) as session, session.begin():
            actor = authenticate(session, request)
            lock_organization(session, actor.organization_id)
            token = request.headers["Authorization"].partition(" ")[2]
            row = session.get(LoginSession, token_hash(token))
            if row is None:
                raise Problem(409, "INVALID_STATE", "Fixture actors have no revocable session")
            row.revoked = True
        return Response(status_code=204)

    @app.get("/api/v1/actors")
    def actors(request: Request, role: str | None = None, limit: Limit = 50, cursor: str | None = None):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            statement = select(Actor).where(
                Actor.organization_id == actor.organization_id, Actor.active.is_(True)
            )
            if role:
                matching = [
                    r.id for r in session.scalars(statement) if any(g["role"] == role for g in r.grants)
                ]
                statement = statement.where(Actor.id.in_(matching))
            return page(
                session,
                statement,
                Actor,
                limit,
                cursor,
                digest([actor.organization_id, "actors", role]),
                actor_view,
            )

    @app.get("/api/v1/actors/{id}")
    def actor_get(id: UUID, request: Request):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            row = owned(session, Actor, id, actor.organization_id)
            if not row.active:
                raise Problem(404, "NOT_FOUND", "Actor not found")
            return actor_view(row)

    @app.get("/api/v1/departments")
    def departments(request: Request, limit: Limit = 50, cursor: str | None = None):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            return page(
                session,
                select(Department).where(Department.organization_id == actor.organization_id),
                Department,
                limit,
                cursor,
                digest([actor.organization_id, "departments"]),
            )

    @app.post("/api/v1/departments", status_code=201)
    def department_create(body: s.DepartmentCreate, request: Request):
        return execute(request, body, "department_create", status=201, roles=("admin",))

    @app.patch("/api/v1/departments/{id}")
    def department_patch(id: UUID, body: s.DepartmentPatch, request: Request):
        return execute(request, body, "department_patch", Department, id, roles=("admin",))

    @app.get("/api/v1/employees")
    def employees(request: Request, query: str | None = None, limit: Limit = 50, cursor: str | None = None):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            statement = select(Employee).where(Employee.organization_id == actor.organization_id)
            if query:
                sources = select(SourceRef.employee_id).where(
                    SourceRef.organization_id == actor.organization_id, SourceRef.source_id == query
                )
                statement = statement.where(
                    Employee.display_name.icontains(query, autoescape=True) | Employee.id.in_(sources)
                )
            return page(
                session,
                statement,
                Employee,
                limit,
                cursor,
                digest([actor.organization_id, "employees", query]),
                Workforce(session, actor).employee_view,
            )

    @app.get("/api/v1/employees/{id}")
    def employee_get(id: UUID, request: Request):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            service = Workforce(session, actor)
            row = service.get(Employee, id)
            staff = permitted(actor, ("hr", "admin"))
            self_grant = any(
                g["role"] == "employee" and g["scope_type"] == "self" and g["scope_id"] == actor.id
                for g in actor.grants
            )
            if not staff and not (self_grant and row.account_actor_id == actor.id):
                raise Problem(404, "NOT_FOUND", "Employee not found")
            return service.employee_view(row, detail=True, self_view=not staff)

    @app.post("/api/v1/employees", status_code=201)
    def employee_create(body: s.EmployeeCreate, request: Request):
        return execute(request, body, "employee_create", status=201)

    @app.patch("/api/v1/employees/{id}")
    def employee_patch(id: UUID, body: s.EmployeePatch, request: Request):
        return execute(request, body, "employee_patch", Employee, id)

    @app.post("/api/v1/employees/{id}/assignments", status_code=201)
    def assignment_create(id: UUID, body: s.AssignmentCreate, request: Request):
        return execute(request, body, "assignment_create", Employee, id, status=201)

    @app.post("/api/v1/assignments/{id}/end")
    def assignment_end(id: UUID, body: s.End, request: Request):
        return execute(request, body, "assignment_end", Assignment, id)

    @app.post("/api/v1/assignments/{id}/transfer")
    def assignment_transfer(id: UUID, body: s.Transfer, request: Request):
        return execute(request, body, "assignment_transfer", Assignment, id)

    @app.post("/api/v1/assignments/{id}/correct")
    def assignment_correct(id: UUID, body: s.Correct, request: Request):
        return execute(request, body, "assignment_correct", Assignment, id)

    @app.get("/api/v1/employees/{id}/history")
    def history(id: UUID, request: Request, limit: Limit = 50, cursor: str | None = None):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            owned(session, Employee, id, actor.organization_id)
            return page(
                session,
                select(Audit).where(
                    Audit.organization_id == actor.organization_id, Audit.employee_id == str(id)
                ),
                Audit,
                limit,
                cursor,
                digest([actor.organization_id, "history", str(id)]),
            )

    @app.post("/api/v1/delegations", status_code=201)
    def delegation_create(body: s.DelegationCreate, request: Request):
        return execute(request, body, "delegation_create", status=201)

    @app.get("/api/v1/delegations")
    def delegations(
        request: Request, department_id: UUID, as_of: date, limit: Limit = 50, cursor: str | None = None
    ):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            owned(session, Department, department_id, actor.organization_id)
            statement = select(Delegation).where(
                Delegation.organization_id == actor.organization_id,
                Delegation.department_id == str(department_id),
                Delegation.starts_on <= as_of,
                Delegation.ends_on >= as_of,
            )
            return page(
                session,
                statement,
                Delegation,
                limit,
                cursor,
                digest([actor.organization_id, "delegations", str(department_id), str(as_of)]),
            )

    @app.post("/api/v1/delegations/{id}/end")
    def delegation_end(id: UUID, body: s.End, request: Request):
        return execute(request, body, "delegation_end", Delegation, id)

    @app.get("/api/v1/intakes")
    def intakes(
        request: Request,
        status: Literal["received", "needs_review", "registered", "rejected"] | None = None,
        limit: Limit = 50,
        cursor: str | None = None,
    ):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            statement = select(Intake).where(Intake.organization_id == actor.organization_id)
            if status:
                statement = statement.where(Intake.status == status)
            return page(
                session, statement, Intake, limit, cursor, digest([actor.organization_id, "intakes", status])
            )

    @app.get("/api/v1/intakes/{id}")
    def intake_get(id: UUID, request: Request):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            return serialize(owned(session, Intake, id, actor.organization_id))

    @app.post("/api/v1/intakes/{id}/register")
    def intake_register(id: UUID, body: s.Register, request: Request):
        return execute(request, body, "intake_register", Intake, id)

    @app.post("/api/v1/intakes/{id}/reject")
    def intake_reject(id: UUID, body: s.Reject, request: Request):
        return execute(request, body, "intake_reject", Intake, id)

    @app.post("/api/v1/intakes/{id}/review")
    def intake_review(id: UUID, body: s.Review, request: Request):
        return execute(request, body, "intake_review", Intake, id)

    @app.post("/api/v1/intakes/{id}/resolve-correction")
    def intake_resolve_correction(id: UUID, body: s.Correction, request: Request):
        return execute(request, body, "intake_resolve_correction", Intake, id)

    @app.get("/api/v1/deliveries")
    def deliveries(
        request: Request,
        status: Literal["pending", "failed", "sent"] | None = None,
        limit: Limit = 50,
        cursor: str | None = None,
    ):
        with Session(app.state.engine) as session:
            actor = authenticate(session, request)
            require(actor, "hr", "admin")
            statement = select(Outbox).where(Outbox.organization_id == actor.organization_id)
            if status:
                statement = statement.where(Outbox.status == status)
            return page(
                session,
                statement,
                Outbox,
                limit,
                cursor,
                digest([actor.organization_id, "deliveries", status]),
                delivery_view,
            )

    @app.post("/api/v1/deliveries/{id}/retry")
    def delivery_retry(id: UUID, body: s.Revision, request: Request):
        return execute(request, body, "delivery_retry", Outbox, id)

    app.include_router(onboarding_router)
    app.include_router(development_router)
    return app
