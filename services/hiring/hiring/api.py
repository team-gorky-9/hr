"""HTTP layer: authentication, one transaction per command, Idempotency-Key replay, error envelope."""
import hashlib
import json
import uuid
from typing import Annotated

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from hiring import schemas as s
from hiring import storage
from hiring.auth import authenticate
from hiring.config import Settings
from hiring.database import at_head, make_engine
from hiring.domain import Hiring, document_view
from hiring.portal import Portal
from hiring.portal import public_vacancies as portal_public_vacancies
from hiring.vacancy_catalog import list_publications, read_publication
from hiring.errors import Problem, forbidden
from hiring.models import Document, IdempotentCommand
from hiring.interaction_window import InteractionWindow

Limit = Annotated[int, Query(ge=1, le=100)]


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def problem_response(request: Request, status: int, code: str, message: str, field: str | None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "field": field,
                   "request_id": getattr(request.state, "request_id", None)}},
        status_code=status,
    )


def idempotency_key(request: Request) -> str | None:
    """Stage 1: the header is optional. When it is sent it must be a UUID and is honoured."""
    raw = request.headers.get("Idempotency-Key")
    if raw is None:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise Problem(422, "VALIDATION_ERROR", "Idempotency-Key must be a UUID", "Idempotency-Key") from exc


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Hiring service", version="1.0-stage-1",
                  description="Wave 1 hiring: cases, checklist, documents, start and manual HR confirmation.")
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url, connect_timeout=(
        settings.interaction_connect_seconds if settings.interaction_enabled else None))
    app.state.interaction_window = InteractionWindow(settings, app.state.engine)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1/interaction-window"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Problem)
    async def on_problem(request: Request, exc: Problem):
        return problem_response(request, exc.status, exc.code, exc.message, exc.field)

    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        location = [str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path")]
        return problem_response(request, 422, "VALIDATION_ERROR", first.get("msg", "Invalid input"),
                                ".".join(location) or None)

    def actor_of(request: Request):
        return authenticate(settings, request.headers.get("Authorization"))

    @app.get("/api/v1/interaction-window")
    async def interaction_window(request: Request, relation: str | None = None,
                                 subject_source: str | None = None, subject_kind: str | None = None,
                                 subject_id: uuid.UUID | None = None,
                                 portal_cursor: str | None = Query(default=None, max_length=8192),
                                 legacy_cursor: str | None = Query(default=None, max_length=8192), page_size: Limit = 25):
        # Workforce authentication is synchronous; do not block concurrent source reads.
        import asyncio
        actor = await asyncio.to_thread(actor_of, request)
        body, status = await app.state.interaction_window.read(
            actor, relation=relation, subject_source=subject_source, subject_kind=subject_kind,
            subject_id=str(subject_id) if subject_id else None,
            portal_cursor=portal_cursor, legacy_cursor=legacy_cursor, page_size=page_size)
        return JSONResponse(body, status_code=status)

    @app.api_route("/api/v1/interaction-window/legacy/{path:path}", methods=["GET", "POST"])
    async def interaction_legacy(request: Request, path: str):
        import asyncio
        actor = await asyncio.to_thread(actor_of, request)
        if request.query_params:
            raise Problem(422, "VALIDATION_ERROR", "Legacy action query is fixed by the server")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > settings.interaction_max_bytes:
                raise Problem(413, "BODY_TOO_LARGE", "Action body exceeds limit")
        body, status = await app.state.interaction_window.proxy(actor, request.method, path, bytes(content))
        return JSONResponse(body, status_code=status)

    def read(request: Request, action):
        actor = actor_of(request)
        with Session(app.state.engine) as session, session.begin():
            return JSONResponse(action(Hiring(session, actor, settings)))

    def command(request: Request, body, action, status: int = 200):
        """Runs one command in one transaction. With Idempotency-Key the stored result of the same
        command is returned before any revision check; a different command with the key is 409."""
        actor = actor_of(request)
        key = idempotency_key(request)
        scope = digest([str(actor.actor_id), str(actor.organization_id), request.method, request.url.path, key])
        fingerprint = digest(body.model_dump(mode="json", exclude_unset=True))
        for attempt in (1, 2):
            try:
                with Session(app.state.engine) as session, session.begin():
                    if key is not None:
                        previous = session.get(IdempotentCommand, scope)
                        if previous is not None:
                            if previous.fingerprint != fingerprint:
                                raise Problem(409, "IDEMPOTENCY_CONFLICT", "Key belongs to a different command",
                                              "Idempotency-Key")
                            return JSONResponse(previous.result, status_code=previous.status_code,
                                                headers={"Idempotency-Replayed": "true"})
                    result = action(Hiring(session, actor, settings))
                    code, payload = result if isinstance(result, tuple) else (status, result)
                    if key is not None:
                        session.add(IdempotentCommand(scope=scope, fingerprint=fingerprint,
                                                      status_code=code, result=payload))
                        session.flush()
                    return JSONResponse(payload, status_code=code)
            except IntegrityError:
                # The same key was committed by a parallel request; the second pass replays it.
                if key is None or attempt == 2:
                    raise
        raise AssertionError("unreachable")

    # ------------------------------------------------------------ service state

    @app.get("/health")
    def health():
        return {
            "status": "ok", "service": "hiring", "implementation_stage": 1, "integration_mode": "standalone",
            "auth_mode": settings.auth_mode, "transfer_mode": "manual", "source_mode": settings.source_mode,
        }

    @app.get("/ready")
    def ready():
        try:
            with app.state.engine.connect() as connection:
                connection.execute(text("select 1"))
            migrated = at_head(app.state.engine)
        except OperationalError:
            return JSONResponse({"status": "unavailable", "database": "unavailable"}, status_code=503)
        if not migrated:
            return JSONResponse({"status": "unavailable", "database": "migrations_pending"}, status_code=503)
        # Stage 1 has no broker: nothing in this service waits for RabbitMQ.
        return {"status": "ok", "database": "ok", "broker": "not_used"}

    # ------------------------------------------------------------ cases

    api = "/api/v1"

    @app.post(f"{api}/cases", status_code=201)
    def create_case(request: Request, body: s.CreateCase):
        return command(request, body, lambda h: h.create(body))

    @app.get(f"{api}/cases")
    def list_cases(request: Request, status: str | None = None, limit: Limit = 50, cursor: str | None = None):
        return read(request, lambda h: h.list_cases(status, limit, cursor))

    @app.get(f"{api}/cases/{{case_id}}")
    def get_case(request: Request, case_id: uuid.UUID):
        return read(request, lambda h: h.get(case_id))

    @app.get(f"{api}/cases/{{case_id}}/history")
    def case_history(request: Request, case_id: uuid.UUID):
        return read(request, lambda h: h.history(case_id))

    @app.get(f"{api}/cases/{{case_id}}/registration-data")
    def registration_data(request: Request, case_id: uuid.UUID):
        return read(request, lambda h: h.registration_data(case_id))

    @app.post(f"{api}/cases/{{case_id}}/request-documents")
    def request_documents(request: Request, case_id: uuid.UUID, body: s.RequestDocuments):
        return command(request, body, lambda h: h.request_documents(case_id, body))

    @app.post(f"{api}/cases/{{case_id}}/items/{{item_id}}/submit")
    def submit_item(request: Request, case_id: uuid.UUID, item_id: uuid.UUID, body: s.SubmitItem):
        return command(request, body, lambda h: h.submit(case_id, item_id, body))

    @app.post(f"{api}/cases/{{case_id}}/items/{{item_id}}/review")
    def review_item(request: Request, case_id: uuid.UUID, item_id: uuid.UUID, body: s.ReviewItem):
        return command(request, body, lambda h: h.review(case_id, item_id, body))

    @app.post(f"{api}/cases/{{case_id}}/ready")
    def mark_ready(request: Request, case_id: uuid.UUID, body: s.Ready):
        return command(request, body, lambda h: h.ready(case_id, body))

    @app.post(f"{api}/cases/{{case_id}}/start")
    def start(request: Request, case_id: uuid.UUID, body: s.Start):
        return command(request, body, lambda h: h.start(case_id, body))

    @app.post(f"{api}/cases/{{case_id}}/withdraw")
    def withdraw(request: Request, case_id: uuid.UUID, body: s.Withdraw):
        return command(request, body, lambda h: h.withdraw(case_id, body))

    @app.post(f"{api}/cases/{{case_id}}/link-account")
    def link_account(request: Request, case_id: uuid.UUID, body: s.LinkAccount):
        return command(request, body, lambda h: h.link_account(case_id, body))

    @app.post(f"{api}/cases/{{case_id}}/correct-start")
    def correct_start(request: Request, case_id: uuid.UUID, body: s.CorrectStart):
        return command(request, body, lambda h: h.correct_start(case_id, body))

    @app.post(f"{api}/cases/{{case_id}}/record-assignment")
    def record_assignment(request: Request, case_id: uuid.UUID, body: s.RecordAssignment):
        return command(request, body, lambda h: h.record_assignment(case_id, body))

    # ------------------------------------------------------------ candidate-portal (wave-5, 5A)

    def portal_read(request: Request, action):
        actor = actor_of(request)
        with Session(app.state.engine) as session, session.begin():
            return JSONResponse(action(Portal(session, actor, settings)))

    def portal_command(request: Request, body, action, status: int = 200):
        return command(request, body, lambda h: action(Portal(h.session, h.actor, h.settings)), status)

    @app.get(f"{api}/candidate-portal/public-vacancies")
    def list_portal_publications():
        return {"items": list_publications(settings)}

    @app.get(f"{api}/candidate-portal/public-vacancies/{{vacancy_id}}")
    def read_portal_publication(vacancy_id: uuid.UUID):
        return read_publication(settings, vacancy_id)

    @app.get(f"{api}/candidate-portal/vacancies")
    def portal_vacancies(request: Request):
        """Публичные вакансии для выбора цели: учебный снимок (source=training_snapshot)."""
        actor_of(request)
        data = portal_public_vacancies(settings)
        return {"source": data["source"], "observed_at": data["observed_at"], "is_synthetic": data["is_synthetic"],
                "items": [{"ref": v["ref"], "title": v["title"], "description": v["description"],
                           "position_code": v["position_code"], "status": v["status"]}
                          for v in data["vacancies"] if v["status"] == "published"]}

    @app.post(f"{api}/candidate-requests", status_code=201)
    def create_candidate_request(request: Request, body: s.CreateCandidateRequest):
        return portal_command(request, body, lambda p: p.create(body))

    @app.get(f"{api}/candidate-requests")
    def list_candidate_requests(request: Request, status: str | None = None):
        return portal_read(request, lambda p: p.list_requests(status))

    @app.get(f"{api}/candidate-requests/{{request_id}}")
    def get_candidate_request(request: Request, request_id: uuid.UUID):
        return portal_read(request, lambda p: p.get(request_id))

    @app.get(f"{api}/candidate-requests/{{request_id}}/history")
    def candidate_request_history(request: Request, request_id: uuid.UUID):
        return portal_read(request, lambda p: p.history(request_id))

    @app.patch(f"{api}/candidate-requests/{{request_id}}")
    def update_candidate_request(request: Request, request_id: uuid.UUID, body: s.UpdateCandidateRequest):
        return portal_command(request, body, lambda p: p.update(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/submit")
    def submit_candidate_request(request: Request, request_id: uuid.UUID, body: s.SubmitCandidateRequest):
        return portal_command(request, body, lambda p: p.submit(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/information-request")
    def candidate_request_information(request: Request, request_id: uuid.UUID, body: s.InformationRequest):
        return portal_command(request, body, lambda p: p.request_information(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/addendum")
    def candidate_request_addendum(request: Request, request_id: uuid.UUID, body: s.Addendum):
        return portal_command(request, body, lambda p: p.add_addendum(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/ready")
    def candidate_request_ready(request: Request, request_id: uuid.UUID, body: s.RequestReady):
        return portal_command(request, body, lambda p: p.mark_ready(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/choose-vacancy")
    def candidate_request_choose_vacancy(request: Request, request_id: uuid.UUID, body: s.ChooseVacancy):
        return portal_command(request, body, lambda p: p.choose_vacancy(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/record-consideration")
    def candidate_request_consideration(request: Request, request_id: uuid.UUID, body: s.RecordConsideration):
        return portal_command(request, body, lambda p: p.record_consideration(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/public-outcome")
    def candidate_request_outcome(request: Request, request_id: uuid.UUID, body: s.PublicOutcome):
        return portal_command(request, body, lambda p: p.publish_outcome(request_id, body))

    @app.post(f"{api}/candidate-requests/{{request_id}}/withdraw")
    def candidate_request_withdraw(request: Request, request_id: uuid.UUID, body: s.WithdrawRequest):
        return portal_command(request, body, lambda p: p.withdraw(request_id, body))

    @app.get(f"{api}/candidate-requests/{{request_id}}/messages")
    def candidate_request_messages(request: Request, request_id: uuid.UUID):
        return portal_read(request, lambda p: p.messages(request_id))

    @app.post(f"{api}/candidate-requests/{{request_id}}/messages/{{message_id}}/read")
    def candidate_request_message_read(request: Request, request_id: uuid.UUID, message_id: uuid.UUID):
        actor = actor_of(request)
        with Session(app.state.engine) as session, session.begin():
            return JSONResponse(Portal(session, actor, settings).mark_read(request_id, message_id))

    @app.post(f"{api}/candidate-requests/{{request_id}}/documents", status_code=201)
    def upload_request_document(request: Request, request_id: uuid.UUID, file: Annotated[UploadFile, File()],
                                kind: Annotated[str, Form()] = "candidate_resume"):
        """Резюме или дополнение своего обращения: новый неизменяемый документ, прежние сохраняются."""
        actor = actor_of(request)
        if kind not in s.REQUEST_DOCUMENT_KINDS:
            raise Problem(422, "VALIDATION_ERROR", f"kind must be one of {', '.join(s.REQUEST_DOCUMENT_KINDS)}", "kind")
        if not actor.is_candidate():
            raise forbidden("Only the author uploads documents of a candidate request")
        with Session(app.state.engine) as session, session.begin():
            Portal(session, actor, settings).own(request_id)  # чужое обращение — 404 до записи файла
        original_name = (file.filename or "document").replace("\\", "/").rsplit("/", 1)[-1][:255] or "document"
        document_id = uuid.uuid4()
        stored = storage.save(settings.file_root, actor.organization_id, document_id, file.file, settings.file_max_bytes)
        committed = False
        try:
            with Session(app.state.engine) as session, session.begin():
                document = Document(
                    id=document_id, organization_id=actor.organization_id, kind=kind, original_name=original_name,
                    media_type=stored.media_type, size_bytes=stored.size, sha256=stored.sha256, revision=1,
                    uploaded_by=actor.actor_id, uploaded_by_role=actor.role, storage_key=stored.key)
                payload = Portal(session, actor, settings).attach(request_id, document)
            committed = True
            return JSONResponse(payload, status_code=201)
        finally:
            if not committed:
                storage.remove(settings.file_root, stored.key)

    @app.get(f"{api}/candidate-requests/{{request_id}}/documents/{{document_id}}/content")
    def request_document_content(request: Request, request_id: uuid.UUID, document_id: uuid.UUID):
        actor = actor_of(request)
        with Session(app.state.engine) as session:
            document = Portal(session, actor, settings).document(request_id, document_id)
            path, media_type, name = storage.path_of(settings.file_root, document.storage_key), \
                document.media_type, document.original_name
        if not path.exists():
            raise Problem(503, "DEPENDENCY_UNAVAILABLE", "Stored original is not available")
        return FileResponse(path, media_type=media_type, filename=name)

    # ------------------------------------------------------------ documents

    @app.post(f"{api}/documents", status_code=201)
    def upload_document(request: Request, file: Annotated[UploadFile, File()], kind: Annotated[str, Form()]):
        actor = actor_of(request)
        key = idempotency_key(request)
        if kind not in s.DOCUMENT_KINDS:
            raise Problem(422, "VALIDATION_ERROR", f"kind must be one of {', '.join(s.DOCUMENT_KINDS)}", "kind")
        if not (actor.is_hr() or actor.is_candidate()):
            raise forbidden("Only hr, admin or a candidate can upload hiring documents")
        if not actor.is_hr() and kind == "employment_basis":
            raise forbidden("The employment basis is uploaded by HR")
        original_name = (file.filename or "document").replace("\\", "/").rsplit("/", 1)[-1][:255] or "document"
        document_id = uuid.uuid4()
        # The bytes are fully on disk before the row exists; on any failure below the file is removed.
        stored = storage.save(settings.file_root, actor.organization_id, document_id, file.file,
                              settings.file_max_bytes)
        scope = digest([str(actor.actor_id), str(actor.organization_id), "POST", request.url.path, key])
        fingerprint = digest([kind, original_name, stored.sha256])
        committed = False
        try:
            with Session(app.state.engine) as session, session.begin():
                if key is not None:
                    previous = session.get(IdempotentCommand, scope)
                    if previous is not None:
                        if previous.fingerprint != fingerprint:
                            raise Problem(409, "IDEMPOTENCY_CONFLICT", "Key belongs to a different upload",
                                          "Idempotency-Key")
                        return JSONResponse(previous.result, status_code=previous.status_code,
                                            headers={"Idempotency-Replayed": "true"})
                document = Document(
                    id=document_id, organization_id=actor.organization_id, kind=kind, original_name=original_name,
                    media_type=stored.media_type, size_bytes=stored.size, sha256=stored.sha256, revision=1,
                    uploaded_by=actor.actor_id, uploaded_by_role=actor.role, storage_key=stored.key,
                )
                session.add(document)
                session.flush()
                payload = document_view(document)
                if key is not None:
                    session.add(IdempotentCommand(scope=scope, fingerprint=fingerprint, status_code=201,
                                                  result=payload))
            committed = True
            return JSONResponse(payload, status_code=201)
        finally:
            if not committed:
                storage.remove(settings.file_root, stored.key)

    @app.get(f"{api}/documents/{{document_id}}")
    def document_metadata(request: Request, document_id: uuid.UUID):
        return read(request, lambda h: document_view(h.document(document_id)))

    @app.get(f"{api}/documents/{{document_id}}/content")
    def document_content(request: Request, document_id: uuid.UUID):
        actor = actor_of(request)
        with Session(app.state.engine) as session:
            document = Hiring(session, actor, settings).document(document_id)
            path, media_type, name = storage.path_of(settings.file_root, document.storage_key), \
                document.media_type, document.original_name
        if not path.exists():
            raise Problem(503, "DEPENDENCY_UNAVAILABLE", "Stored original is not available")
        return FileResponse(path, media_type=media_type, filename=name)

    return app
