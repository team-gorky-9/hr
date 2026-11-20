"""Маршруты HTTP API сервиса требований (/api/v1, /health, /ready)."""
import hashlib
from typing import Annotated, Literal
from urllib.parse import quote
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import Actor
from ..config import Settings
from ..errors import ServiceError
from ..idempotency import parse_idempotency_key
from ..schemas import (
    ApprovedProfileOut,
    DeliveryOut,
    DocumentOut,
    DraftApproveIn,
    DraftCreateIn,
    DraftEventOut,
    DraftOut,
    DraftPatchIn,
    DraftReviewIn,
    DraftSubmitIn,
    HealthOut,
    PageOut,
    PositionCreateIn,
    PositionOut,
    ProfileReviseIn,
    ReadyOut,
    SourceOut,
    SourceTranscriptionIn,
)
from ..service import CommandResult, RequirementsService

EXPECTED_ALEMBIC_HEAD = "0001_initial_requirements"

health_router = APIRouter()
api_router = APIRouter(prefix="/api/v1")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_service(request: Request) -> RequirementsService:
    return request.app.state.service


def get_db_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def get_current_actor(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    return request.app.state.actor_directory.authenticate_bearer(authorization)


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> uuid.UUID:
    return parse_idempotency_key(idempotency_key)


def get_correlation_id(
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-Id")] = None,
) -> uuid.UUID:
    if x_correlation_id:
        try:
            return uuid.UUID(x_correlation_id.strip())
        except ValueError:
            pass
    return uuid.uuid4()


SettingsDep = Annotated[Settings, Depends(get_settings)]
ServiceDep = Annotated[RequirementsService, Depends(get_service)]
SessionDep = Annotated[Session, Depends(get_db_session)]
ActorDep = Annotated[Actor, Depends(get_current_actor)]
IdempotencyKeyDep = Annotated[uuid.UUID, Depends(get_idempotency_key)]
CorrelationIdDep = Annotated[uuid.UUID, Depends(get_correlation_id)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


def _command_response(result: CommandResult) -> JSONResponse:
    headers = {"Idempotency-Replayed": "true"} if result.replayed else {}
    return JSONResponse(status_code=result.status_code, content=result.body, headers=headers)


async def _read_upload_bounded(upload: UploadFile, max_bytes: int) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    hasher = hashlib.sha256()
    while True:
        chunk = await upload.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ServiceError(
                413,
                "FILE_TOO_LARGE",
                f"Размер файла превышает допустимый предел ({max_bytes} байт).",
                field="file",
            )
        hasher.update(chunk)
        chunks.append(chunk)
    return b"".join(chunks), hasher.hexdigest()


# --- Health & Ready -----------------------------------------------------------


@health_router.get("/health", response_model=HealthOut)
@api_router.get("/health", response_model=HealthOut)
def health(settings: SettingsDep) -> HealthOut:
    return HealthOut(
        status="ok",
        service=settings.service_name,
        auth_mode=settings.auth_mode,
    )


@health_router.get("/ready", response_model=ReadyOut, responses={503: {"model": ReadyOut}})
@api_router.get("/ready", response_model=ReadyOut, responses={503: {"model": ReadyOut}})
def ready(request: Request, session: SessionDep, settings: SettingsDep):
    db_status = "unavailable"
    migrations_status = "unavailable"
    try:
        session.execute(text("SELECT 1"))
        db_status = "ok"
        version = session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        if version == EXPECTED_ALEMBIC_HEAD:
            migrations_status = "ok"
        else:
            migrations_status = "pending"
    except SQLAlchemyError:
        pass

    broker_ok = False
    try:
        broker_ok = bool(request.app.state.publisher.check_health())
    except Exception:
        broker_ok = False

    broker_status = "ok" if broker_ok else "unavailable"
    is_ready = db_status == "ok" and migrations_status == "ok"
    payload = ReadyOut(
        status="ok" if is_ready else "unavailable",
        db=db_status,
        migrations=migrations_status,
        broker=broker_status,
        auth_mode=settings.auth_mode,
    )
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content=payload.model_dump(mode="json"),
    )


# --- Positions ----------------------------------------------------------------


@api_router.post("/positions", status_code=201, response_model=PositionOut)
def create_position(
    request: Request,
    body: PositionCreateIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
):
    result = service.create_position(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        body=body,
    )
    return _command_response(result)


@api_router.get("/positions", response_model=PageOut[PositionOut])
def list_positions(
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
    limit: LimitQuery = 50,
    cursor: str | None = None,
) -> PageOut[PositionOut]:
    return service.list_positions(session, actor=actor, limit=limit, cursor=cursor)


# --- Documents ----------------------------------------------------------------


@api_router.post("/documents", status_code=201, response_model=DocumentOut)
async def upload_document(
    request: Request,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    kind: str = Form(...),
):
    data, sha256 = await _read_upload_bounded(file, settings.file_max_bytes)
    result = service.upload_document(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        kind=kind,
        original_name=file.filename,
        media_type=file.content_type,
        data=data,
        sha256=sha256,
    )
    return _command_response(result)


@api_router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
) -> DocumentOut:
    return service.get_document(session, actor=actor, document_id=document_id)


@api_router.get("/documents/{document_id}/content")
def get_document_content(
    document_id: uuid.UUID,
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
) -> Response:
    doc, content_bytes = service.get_document_content(
        session,
        actor=actor,
        document_id=document_id,
    )
    encoded_name = quote(doc.original_name)
    return Response(
        content=content_bytes,
        media_type=doc.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "X-Content-SHA256": doc.sha256,
        },
    )


# --- Sources ------------------------------------------------------------------


@api_router.post("/sources", status_code=201, response_model=SourceOut)
async def upload_source(
    request: Request,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    position_code: str = Form(...),
    kind: str = Form("job_description"),
):
    data, sha256 = await _read_upload_bounded(file, settings.file_max_bytes)
    result = service.upload_source(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        position_code=position_code,
        kind=kind,
        original_name=file.filename,
        media_type=file.content_type,
        data=data,
        sha256=sha256,
    )
    return _command_response(result)


@api_router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(
    source_id: uuid.UUID,
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
) -> SourceOut:
    return service.get_source(session, actor=actor, source_id=source_id)


@api_router.post("/sources/{source_id}/transcription", response_model=SourceOut)
def transcribe_source(
    source_id: uuid.UUID,
    request: Request,
    body: SourceTranscriptionIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
):
    result = service.transcribe_source(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        source_id=source_id,
        body=body,
    )
    return _command_response(result)


# --- Drafts -------------------------------------------------------------------


@api_router.post("/drafts", status_code=201, response_model=DraftOut)
def create_draft(
    request: Request,
    body: DraftCreateIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
):
    result = service.create_draft(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        body=body,
    )
    return _command_response(result)


@api_router.get("/drafts", response_model=PageOut[DraftOut])
def list_drafts(
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
    status: Literal["editing", "in_review", "returned", "approved"] | None = None,
    position_code: str | None = None,
    limit: LimitQuery = 50,
    cursor: str | None = None,
) -> PageOut[DraftOut]:
    return service.list_drafts(
        session,
        actor=actor,
        status=status,
        position_code=position_code,
        limit=limit,
        cursor=cursor,
    )


@api_router.get("/drafts/{draft_id}", response_model=DraftOut)
def get_draft(
    draft_id: uuid.UUID,
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
) -> DraftOut:
    return service.get_draft(session, actor=actor, draft_id=draft_id)


@api_router.patch("/drafts/{draft_id}", response_model=DraftOut)
def patch_draft(
    draft_id: uuid.UUID,
    request: Request,
    body: DraftPatchIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
):
    result = service.patch_draft(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        draft_id=draft_id,
        body=body,
    )
    return _command_response(result)


@api_router.post("/drafts/{draft_id}/submit", response_model=DraftOut)
def submit_draft(
    draft_id: uuid.UUID,
    request: Request,
    body: DraftSubmitIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
    authorization: Annotated[str | None, Header()] = None,
):
    result = service.submit_draft(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        draft_id=draft_id,
        body=body,
        authorization_header=authorization,
    )
    return _command_response(result)


@api_router.post("/drafts/{draft_id}/review", response_model=DraftOut)
def review_draft(
    draft_id: uuid.UUID,
    request: Request,
    body: DraftReviewIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
):
    result = service.review_draft(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        draft_id=draft_id,
        body=body,
    )
    return _command_response(result)


@api_router.post("/drafts/{draft_id}/approve", status_code=201, response_model=ApprovedProfileOut)
def approve_draft(
    draft_id: uuid.UUID,
    request: Request,
    body: DraftApproveIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    correlation_id: CorrelationIdDep,
    service: ServiceDep,
):
    result = service.approve_draft(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        draft_id=draft_id,
        body=body,
        correlation_id=correlation_id,
    )
    return _command_response(result)


@api_router.get("/drafts/{draft_id}/history", response_model=PageOut[DraftEventOut])
def get_draft_history(
    draft_id: uuid.UUID,
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
    limit: LimitQuery = 50,
    cursor: str | None = None,
) -> PageOut[DraftEventOut]:
    return service.get_draft_history(
        session,
        actor=actor,
        draft_id=draft_id,
        limit=limit,
        cursor=cursor,
    )


# --- Approved Profiles --------------------------------------------------------


@api_router.post("/profiles/{profile_id}/revise", status_code=201, response_model=DraftOut)
def revise_profile(
    profile_id: uuid.UUID,
    request: Request,
    body: ProfileReviseIn,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
):
    result = service.revise_profile(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        profile_id=profile_id,
        body=body,
    )
    return _command_response(result)


@api_router.get("/profiles/{profile_id}", response_model=ApprovedProfileOut)
def get_profile(
    profile_id: uuid.UUID,
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
) -> ApprovedProfileOut:
    return service.get_profile(session, actor=actor, profile_id=profile_id)


@api_router.get("/positions/{position_code}/approved-profile", response_model=ApprovedProfileOut)
def get_current_approved_profile(
    position_code: str,
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
    contour: Literal["training", "working"] = "working",
) -> ApprovedProfileOut:
    return service.get_current_approved_profile(
        session,
        actor=actor,
        position_code=position_code,
        contour=contour,
    )


# --- Deliveries (Outbox) ------------------------------------------------------


@api_router.get("/deliveries", response_model=PageOut[DeliveryOut])
def list_deliveries(
    session: SessionDep,
    actor: ActorDep,
    service: ServiceDep,
    status: Literal["pending", "failed", "sent"] | None = None,
    limit: LimitQuery = 50,
    cursor: str | None = None,
) -> PageOut[DeliveryOut]:
    return service.list_deliveries(
        session,
        actor=actor,
        status=status,
        limit=limit,
        cursor=cursor,
    )


@api_router.post("/deliveries/{event_id}/retry", response_model=DeliveryOut)
def retry_delivery(
    event_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: IdempotencyKeyDep,
    service: ServiceDep,
):
    result = service.retry_delivery(
        session,
        actor=actor,
        idempotency_key=idempotency_key,
        path=request.url.path,
        event_id=event_id,
    )
    return _command_response(result)
