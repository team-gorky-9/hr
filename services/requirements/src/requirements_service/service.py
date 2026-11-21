"""Прикладная бизнес-логика сервиса подготовки и выпуска требований."""
from copy import deepcopy
from dataclasses import dataclass
import mimetypes
from pathlib import Path
import threading
from typing import Any, Callable, Literal
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import Actor, ActorDirectory, require_draft_reader, require_hr_or_admin, require_position_reader
from .config import Settings
from .db.base import utcnow
from .db.models import (
    ApprovedProfile,
    Document,
    Draft,
    DraftEvent,
    OutboxEvent,
    Position,
    Source,
    SourceTextRevision,
)
from .errors import ServiceError
from .extraction import extract_source_text, normalize_text
from .idempotency import IdempotencyScope, find_replay, make_scope, save_record
from .messaging.outbox import OutboxRelay
from .pagination import apply_cursor_filter, build_page
from .schemas import (
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
    PageOut,
    PositionCreateIn,
    PositionOut,
    ProfileReviseIn,
    SourceOut,
    SourceSnapshotOut,
    SourceTranscriptionIn,
)
from .storage import LocalFileStorage
from .validation import ProfileDraft, iter_all_rows, quote_in_document, validate_draft_content

ALLOWED_DOCUMENT_MIME_TYPES = frozenset({
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/json",
    "image/png",
    "image/jpeg",
    "application/octet-stream",
})
ALLOWED_DOCUMENT_EXTENSIONS = frozenset({
    ".txt",
    ".pdf",
    ".docx",
    ".doc",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
})
ALLOWED_DOCUMENT_KINDS = frozenset({
    "job_description",
    "competency_matrix",
    "vacancy_posting",
    "regulation",
    "other",
})


@dataclass(frozen=True)
class CommandResult:
    """Результат мутирующей команды с флагом идемпотентного повтора."""

    status_code: int
    body: dict[str, Any]
    replayed: bool = False


class _PositionLockRegistry:
    """Реестр внутрипроцессных блокировок по (organization_id, position_code)."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[tuple[uuid.UUID, str], threading.Lock] = {}

    def lock_for(self, organization_id: uuid.UUID, position_code: str) -> threading.Lock:
        key = (organization_id, position_code)
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock


def _sanitize_filename(original_name: str | None) -> str:
    base = Path(original_name or "document.bin").name.strip()
    return base or "document.bin"


def _normalize_media_type(raw_media_type: str | None, filename: str) -> str:
    base = (raw_media_type or "").split(";", 1)[0].strip().lower()
    if not base:
        guessed, _ = mimetypes.guess_type(filename)
        base = (guessed or "application/octet-stream").lower()
    return base


def _validate_upload_metadata(filename: str, media_type: str, kind: str, data: bytes) -> str:
    if kind not in ALLOWED_DOCUMENT_KINDS:
        raise ServiceError(
            422,
            "VALIDATION_ERROR",
            "Недопустимый вид документа kind.",
            field="kind",
        )
    if len(data) == 0:
        raise ServiceError(422, "VALIDATION_ERROR", "Файл не может быть пустым.", field="file")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS or media_type not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise ServiceError(
            422,
            "VALIDATION_ERROR",
            "Неподдерживаемый тип или расширение файла.",
            field="file",
        )
    return ext


def _serialize_position(pos: Position) -> PositionOut:
    return PositionOut(
        id=pos.id,
        organization_id=pos.organization_id,
        code=pos.code,
        title=pos.title,
        revision=pos.revision,
        created_at=pos.created_at,
        updated_at=pos.updated_at,
    )


def _serialize_document(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        organization_id=doc.organization_id,
        kind=doc.kind,
        original_name=doc.original_name,
        media_type=doc.media_type,
        size_bytes=doc.size_bytes,
        sha256=doc.sha256,
        revision=doc.revision,
        uploaded_by=doc.uploaded_by,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _serialize_source(source: Source) -> SourceOut:
    doc = source.document
    return SourceOut(
        id=source.id,
        organization_id=source.organization_id,
        kind=doc.kind,
        original_name=doc.original_name,
        media_type=doc.media_type,
        size_bytes=doc.size_bytes,
        sha256=doc.sha256,
        revision=source.revision,
        uploaded_by=doc.uploaded_by,
        position_code=source.position_code,
        extraction_status=source.extraction_status,
        extracted_text=source.extracted_text,
        text_origin=source.text_origin,
        transcription_basis=source.transcription_basis,
        reason=source.reason,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _serialize_draft(draft: Draft) -> DraftOut:
    return DraftOut(
        id=draft.id,
        organization_id=draft.organization_id,
        position_code=draft.position_code,
        contour=draft.contour,
        status=draft.status,
        revision=draft.revision,
        content_revision=draft.content_revision,
        content=draft.content,
        review_note=draft.review_note,
        assigned_reviewer_actor_id=draft.assigned_reviewer_actor_id,
        accepted_content_revision=draft.accepted_content_revision,
        accepted_source_revisions=draft.accepted_source_revisions,
        accepted_by_actor_id=draft.accepted_by_actor_id,
        accepted_at=draft.accepted_at,
        created_by_actor_id=draft.created_by_actor_id,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def _serialize_draft_event(event: DraftEvent) -> DraftEventOut:
    return DraftEventOut(
        id=event.id,
        draft_id=event.draft_id,
        organization_id=event.organization_id,
        actor_id=event.actor_id,
        action=event.action,
        draft_revision=event.draft_revision,
        content_revision=event.content_revision,
        reason=event.reason,
        details=event.details,
        created_at=event.created_at,
    )


def _serialize_profile(profile: ApprovedProfile) -> ApprovedProfileOut:
    return ApprovedProfileOut(
        id=profile.id,
        draft_id=profile.draft_id,
        organization_id=profile.organization_id,
        position_code=profile.position_code,
        version=profile.version,
        contour=profile.contour,
        revision=profile.revision,
        content=profile.content,
        sources_snapshot=[SourceSnapshotOut.model_validate(item) for item in profile.sources_snapshot],
        approval_basis=profile.approval_basis,
        approved_by_actor_id=profile.approved_by_actor_id,
        approved_at=profile.approved_at,
        is_current=profile.is_current,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _serialize_delivery(event: OutboxEvent) -> DeliveryOut:
    return DeliveryOut(
        event_id=event.event_id,
        event_type=event.event_type,
        status=event.status,
        attempts=event.attempts,
        last_error=event.last_error,
        next_attempt_at=event.next_attempt_at,
        sent_at=event.sent_at,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


class RequirementsService:
    """Координатор сценариев требований, идемпотентности, версий и outbox."""

    def __init__(
        self,
        *,
        settings: Settings,
        storage: LocalFileStorage,
        actor_directory: ActorDirectory,
        outbox_relay: OutboxRelay | None = None,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._actor_directory = actor_directory
        self._outbox_relay = outbox_relay
        self._position_locks = _PositionLockRegistry()

    def _run_idempotent(
        self,
        session: Session,
        *,
        scope: IdempotencyScope,
        status_code: int,
        action: Callable[[], dict[str, Any]],
        on_rollback: Callable[[], None] | None = None,
    ) -> CommandResult:
        replay = find_replay(session, scope)
        if replay is not None:
            replayed_status, replayed_body = replay
            return CommandResult(status_code=replayed_status, body=replayed_body, replayed=True)

        try:
            body = action()
            save_record(session, scope, status_code=status_code, response_body=body)
            session.commit()
            return CommandResult(status_code=status_code, body=body, replayed=False)
        except IntegrityError as exc:
            session.rollback()
            if on_rollback is not None:
                on_rollback()
            replay_after = find_replay(session, scope)
            if replay_after is not None:
                replayed_status, replayed_body = replay_after
                return CommandResult(status_code=replayed_status, body=replayed_body, replayed=True)
            raise ServiceError(
                409,
                "ALREADY_EXISTS",
                "Операция конфликтует с существующей записью.",
            ) from exc
        except Exception:
            session.rollback()
            if on_rollback is not None:
                on_rollback()
            raise

    def _load_org_position(
        self,
        session: Session,
        organization_id: uuid.UUID,
        position_code: str,
        *,
        for_update: bool = False,
    ) -> Position:
        stmt = select(Position).where(
            Position.organization_id == organization_id,
            Position.code == position_code,
        )
        if for_update and session.bind is not None and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        position = session.scalar(stmt)
        if position is None:
            raise ServiceError(404, "NOT_FOUND", "Должность не найдена.", field="position_code")
        return position

    def _load_org_sources_for_draft(
        self,
        session: Session,
        organization_id: uuid.UUID,
        validated: ProfileDraft,
    ) -> dict[uuid.UUID, Source]:
        source_ids = [s.source_document_id for s in validated.sources]
        if not source_ids:
            return {}
        rows = list(
            session.scalars(
                select(Source).where(
                    Source.organization_id == organization_id,
                    Source.id.in_(source_ids),
                )
            )
        )
        by_id = {row.id: row for row in rows}
        for source_id in source_ids:
            if source_id not in by_id:
                raise ServiceError(
                    422,
                    "SOURCE_NOT_FOUND",
                    "Указанный исходный документ не найден в организации.",
                    field="content.sources",
                )
        return by_id

    def _verify_draft_quotes(
        self,
        validated: ProfileDraft,
        sources_by_id: dict[uuid.UUID, Source],
    ) -> None:
        for row in iter_all_rows(validated):
            for ref in row.source_refs:
                source = sources_by_id.get(ref.source_document_id)
                if source is None:
                    raise ServiceError(
                        422,
                        "SOURCE_NOT_FOUND",
                        "Источник ссылки не указан в списке sources профиля.",
                        field="content.source_refs",
                    )
                if source.extraction_status != "ready" or not source.extracted_text:
                    raise ServiceError(
                        409,
                        "SOURCE_NOT_READY",
                        "Исходный документ ещё не готов для проверки цитат; проверьте статус или добавьте ручную транскрипцию.",
                        field="content.sources",
                    )
                if not quote_in_document(ref.quote, source.extracted_text):
                    raise ServiceError(
                        422,
                        "SOURCE_MISMATCH",
                        "Цитата не найдена в выбранной редакции исходного документа.",
                        field="content.source_refs",
                    )

    def _department_can_access_source(
        self,
        session: Session,
        actor: Actor,
        source_id: uuid.UUID,
    ) -> bool:
        assigned_drafts = list(
            session.scalars(
                select(Draft).where(
                    Draft.organization_id == actor.organization_id,
                    Draft.assigned_reviewer_actor_id == actor.actor_id,
                )
            )
        )
        target_str = str(source_id)
        for draft in assigned_drafts:
            for src in draft.content.get("sources", []):
                if str(src.get("source_document_id")) == target_str:
                    return True
        return False

    # --- Positions ----------------------------------------------------------------

    def create_position(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        body: PositionCreateIn,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload=body.model_dump(mode="json"),
        )

        def _execute() -> dict[str, Any]:
            existing = session.scalar(
                select(Position).where(
                    Position.organization_id == actor.organization_id,
                    Position.code == body.code,
                )
            )
            if existing is not None:
                raise ServiceError(
                    409,
                    "ALREADY_EXISTS",
                    "Должность с таким кодом уже существует в организации.",
                    field="code",
                )
            now = utcnow()
            pos = Position(
                organization_id=actor.organization_id,
                code=body.code,
                title=body.title,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            session.add(pos)
            session.flush()
            return _serialize_position(pos).model_dump(mode="json")

        return self._run_idempotent(session, scope=scope, status_code=201, action=_execute)

    def list_positions(
        self,
        session: Session,
        *,
        actor: Actor,
        limit: int,
        cursor: str | None,
    ) -> PageOut[PositionOut]:
        require_position_reader(actor)
        stmt = select(Position).where(Position.organization_id == actor.organization_id)
        stmt = apply_cursor_filter(stmt, Position.created_at, Position.id, cursor).limit(limit + 1)
        rows = list(session.scalars(stmt))
        items, next_cursor = build_page(rows, limit=limit, serializer=_serialize_position)
        return PageOut(items=items, next_cursor=next_cursor)

    # --- Documents & Sources ------------------------------------------------------

    def upload_document(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        kind: str,
        original_name: str | None,
        media_type: str | None,
        data: bytes,
        sha256: str,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        safe_name = _sanitize_filename(original_name)
        normalized_mime = _normalize_media_type(media_type, safe_name)
        _validate_upload_metadata(safe_name, normalized_mime, kind.strip(), data)

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload={
                "kind": kind.strip(),
                "original_name": safe_name,
                "media_type": normalized_mime,
                "sha256": sha256,
                "size_bytes": len(data),
            },
        )
        saved_keys: list[str] = []

        def _execute() -> dict[str, Any]:
            doc_id = uuid.uuid4()
            stored = self._storage.save_bytes(
                organization_id=actor.organization_id,
                document_id=doc_id,
                data=data,
            )
            saved_keys.append(stored.storage_key)
            now = utcnow()
            doc = Document(
                id=doc_id,
                organization_id=actor.organization_id,
                kind=kind.strip(),
                original_name=safe_name,
                media_type=normalized_mime,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                storage_key=stored.storage_key,
                revision=1,
                uploaded_by=actor.actor_id,
                created_at=now,
                updated_at=now,
            )
            session.add(doc)
            session.flush()
            return _serialize_document(doc).model_dump(mode="json")

        def _cleanup() -> None:
            for key in saved_keys:
                self._storage.delete_by_key(key)

        return self._run_idempotent(
            session,
            scope=scope,
            status_code=201,
            action=_execute,
            on_rollback=_cleanup,
        )

    def get_document(
        self,
        session: Session,
        *,
        actor: Actor,
        document_id: uuid.UUID,
    ) -> DocumentOut:
        require_draft_reader(actor)
        doc = session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == actor.organization_id,
            )
        )
        if doc is None:
            raise ServiceError(404, "NOT_FOUND", "Документ не найден.")
        if not actor.has_any_role("hr", "admin"):
            if not self._department_can_access_source(session, actor, document_id):
                raise ServiceError(403, "FORBIDDEN", "Нет доступа к данному документу.")
        return _serialize_document(doc)

    def get_document_content(
        self,
        session: Session,
        *,
        actor: Actor,
        document_id: uuid.UUID,
    ) -> tuple[Document, bytes]:
        require_draft_reader(actor)
        doc = session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == actor.organization_id,
            )
        )
        if doc is None:
            raise ServiceError(404, "NOT_FOUND", "Документ не найден.")
        if not actor.has_any_role("hr", "admin"):
            if not self._department_can_access_source(session, actor, document_id):
                raise ServiceError(403, "FORBIDDEN", "Нет доступа к содержимому данного документа.")
        content_bytes = self._storage.read_bytes(doc.storage_key)
        return doc, content_bytes

    def upload_source(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        position_code: str,
        kind: str,
        original_name: str | None,
        media_type: str | None,
        data: bytes,
        sha256: str,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        clean_code = position_code.strip()
        if not clean_code:
            raise ServiceError(422, "VALIDATION_ERROR", "Укажите код должности.", field="position_code")
        clean_kind = kind.strip() or "job_description"
        safe_name = _sanitize_filename(original_name)
        normalized_mime = _normalize_media_type(media_type, safe_name)
        ext = _validate_upload_metadata(safe_name, normalized_mime, clean_kind, data)

        self._load_org_position(session, actor.organization_id, clean_code)

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload={
                "position_code": clean_code,
                "kind": clean_kind,
                "original_name": safe_name,
                "media_type": normalized_mime,
                "sha256": sha256,
                "size_bytes": len(data),
            },
        )
        saved_keys: list[str] = []

        def _execute() -> dict[str, Any]:
            doc_id = uuid.uuid4()
            stored = self._storage.save_bytes(
                organization_id=actor.organization_id,
                document_id=doc_id,
                data=data,
            )
            saved_keys.append(stored.storage_key)
            outcome = extract_source_text(data, ext)
            now = utcnow()

            doc = Document(
                id=doc_id,
                organization_id=actor.organization_id,
                kind=clean_kind,
                original_name=safe_name,
                media_type=normalized_mime,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                storage_key=stored.storage_key,
                revision=1,
                uploaded_by=actor.actor_id,
                created_at=now,
                updated_at=now,
            )
            source = Source(
                id=doc_id,
                organization_id=actor.organization_id,
                position_code=clean_code,
                extraction_status=outcome.status,
                extracted_text=outcome.extracted_text,
                text_origin="extracted" if outcome.status == "ready" else None,
                transcription_basis=None,
                reason=outcome.reason,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            text_rev = SourceTextRevision(
                source_id=doc_id,
                revision=1,
                extraction_status=outcome.status,
                text_origin="extracted" if outcome.status == "ready" else None,
                text=outcome.extracted_text,
                basis=None,
                reason=outcome.reason,
                actor_id=actor.actor_id,
                created_at=now,
            )
            source.document = doc
            session.add(doc)
            session.flush()
            session.add(source)
            session.flush()
            session.add(text_rev)
            session.flush()
            return _serialize_source(source).model_dump(mode="json")

        def _cleanup() -> None:
            for key in saved_keys:
                self._storage.delete_by_key(key)

        return self._run_idempotent(
            session,
            scope=scope,
            status_code=201,
            action=_execute,
            on_rollback=_cleanup,
        )

    def get_source(
        self,
        session: Session,
        *,
        actor: Actor,
        source_id: uuid.UUID,
    ) -> SourceOut:
        require_draft_reader(actor)
        source = session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.organization_id == actor.organization_id,
            )
        )
        if source is None:
            raise ServiceError(404, "NOT_FOUND", "Источник не найден.")
        if not actor.has_any_role("hr", "admin"):
            if not self._department_can_access_source(session, actor, source_id):
                raise ServiceError(403, "FORBIDDEN", "Нет доступа к данному источнику.")
        return _serialize_source(source)

    def transcribe_source(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        source_id: uuid.UUID,
        body: SourceTranscriptionIn,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        source = session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.organization_id == actor.organization_id,
            )
        )
        if source is None:
            raise ServiceError(404, "NOT_FOUND", "Источник не найден.")

        normalized_text = normalize_text(body.text)
        if "\x00" in normalized_text or not normalized_text.strip():
            raise ServiceError(
                422,
                "VALIDATION_ERROR",
                "Текст транскрипции должен быть непустым и без нулевых символов.",
                field="text",
            )
        if not body.transcription_basis.strip():
            raise ServiceError(
                422,
                "VALIDATION_ERROR",
                "Укажите основание ручного ввода текста.",
                field="transcription_basis",
            )

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload={
                "expected_revision": body.expected_revision,
                "text": normalized_text,
                "transcription_basis": body.transcription_basis.strip(),
            },
        )

        def _execute() -> dict[str, Any]:
            if source.revision != body.expected_revision:
                raise ServiceError(
                    409,
                    "STALE_REVISION",
                    "Ревизия источника устарела; обновите данные и повторите попытку.",
                    field="expected_revision",
                )
            now = utcnow()
            source.revision += 1
            source.extraction_status = "ready"
            source.extracted_text = normalized_text
            source.text_origin = "manual_transcription"
            source.transcription_basis = body.transcription_basis.strip()
            source.reason = None
            source.updated_at = now

            session.add(
                SourceTextRevision(
                    source_id=source.id,
                    revision=source.revision,
                    extraction_status="ready",
                    text_origin="manual_transcription",
                    text=normalized_text,
                    basis=source.transcription_basis,
                    reason=None,
                    actor_id=actor.actor_id,
                    created_at=now,
                )
            )
            session.flush()
            return _serialize_source(source).model_dump(mode="json")

        return self._run_idempotent(session, scope=scope, status_code=200, action=_execute)

    # --- Drafts & Lifecycle -------------------------------------------------------

    def create_draft(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        body: DraftCreateIn,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        validated = validate_draft_content(body.content)
        if validated.position_code != body.position_code:
            raise ServiceError(
                422,
                "VALIDATION_ERROR",
                "Код должности в content.position_code должен совпадать с position_code.",
                field="content.position_code",
            )
        self._load_org_position(session, actor.organization_id, body.position_code)
        normalized_content = validated.model_dump(mode="json")

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload={
                "position_code": body.position_code,
                "content": normalized_content,
            },
        )

        def _execute() -> dict[str, Any]:
            sources_by_id = self._load_org_sources_for_draft(session, actor.organization_id, validated)
            self._verify_draft_quotes(validated, sources_by_id)
            contour: Literal["training", "working"] = "training" if validated.is_synthetic else "working"
            now = utcnow()
            draft = Draft(
                organization_id=actor.organization_id,
                position_code=body.position_code,
                contour=contour,
                status="editing",
                revision=1,
                content_revision=1,
                content=normalized_content,
                created_by_actor_id=actor.actor_id,
                created_at=now,
                updated_at=now,
            )
            session.add(draft)
            session.flush()
            session.add(
                DraftEvent(
                    draft_id=draft.id,
                    organization_id=actor.organization_id,
                    actor_id=actor.actor_id,
                    action="created",
                    draft_revision=1,
                    content_revision=1,
                    reason=None,
                    details={
                        "contour": contour,
                        "source_revisions": {str(sid): src.revision for sid, src in sources_by_id.items()},
                    },
                    created_at=now,
                )
            )
            session.flush()
            return _serialize_draft(draft).model_dump(mode="json")

        return self._run_idempotent(session, scope=scope, status_code=201, action=_execute)

    def list_drafts(
        self,
        session: Session,
        *,
        actor: Actor,
        status: str | None,
        position_code: str | None,
        limit: int,
        cursor: str | None,
    ) -> PageOut[DraftOut]:
        require_draft_reader(actor)
        stmt = select(Draft).where(Draft.organization_id == actor.organization_id)
        if not actor.has_any_role("hr", "admin"):
            stmt = stmt.where(Draft.assigned_reviewer_actor_id == actor.actor_id)
        if status is not None:
            stmt = stmt.where(Draft.status == status)
        if position_code is not None:
            stmt = stmt.where(Draft.position_code == position_code)
        stmt = apply_cursor_filter(stmt, Draft.created_at, Draft.id, cursor).limit(limit + 1)
        rows = list(session.scalars(stmt))
        items, next_cursor = build_page(rows, limit=limit, serializer=_serialize_draft)
        return PageOut(items=items, next_cursor=next_cursor)

    def _get_draft_for_actor(
        self,
        session: Session,
        actor: Actor,
        draft_id: uuid.UUID,
        *,
        allow_department_if_assigned: bool = False,
    ) -> Draft:
        draft = session.scalar(
            select(Draft).where(
                Draft.id == draft_id,
                Draft.organization_id == actor.organization_id,
            )
        )
        if draft is None:
            raise ServiceError(404, "NOT_FOUND", "Черновик не найден.")
        if actor.has_any_role("hr", "admin"):
            return draft
        if allow_department_if_assigned and actor.has_any_role("department"):
            if draft.assigned_reviewer_actor_id == actor.actor_id:
                return draft
        raise ServiceError(403, "FORBIDDEN", "Нет прав на доступ к этому черновику.")

    def get_draft(
        self,
        session: Session,
        *,
        actor: Actor,
        draft_id: uuid.UUID,
    ) -> DraftOut:
        require_draft_reader(actor)
        draft = self._get_draft_for_actor(
            session,
            actor,
            draft_id,
            allow_department_if_assigned=True,
        )
        return _serialize_draft(draft)

    def get_draft_history(
        self,
        session: Session,
        *,
        actor: Actor,
        draft_id: uuid.UUID,
        limit: int,
        cursor: str | None,
    ) -> PageOut[DraftEventOut]:
        require_draft_reader(actor)
        self._get_draft_for_actor(
            session,
            actor,
            draft_id,
            allow_department_if_assigned=True,
        )
        stmt = select(DraftEvent).where(
            DraftEvent.draft_id == draft_id,
            DraftEvent.organization_id == actor.organization_id,
        )
        stmt = apply_cursor_filter(stmt, DraftEvent.created_at, DraftEvent.id, cursor).limit(limit + 1)
        rows = list(session.scalars(stmt))
        items, next_cursor = build_page(rows, limit=limit, serializer=_serialize_draft_event)
        return PageOut(items=items, next_cursor=next_cursor)

    def patch_draft(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        draft_id: uuid.UUID,
        body: DraftPatchIn,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        draft = self._get_draft_for_actor(session, actor, draft_id)
        validated = validate_draft_content(body.content)
        if validated.position_code != draft.position_code:
            raise ServiceError(
                422,
                "VALIDATION_ERROR",
                "Код должности в content.position_code должен совпадать с должностью черновика.",
                field="content.position_code",
            )
        normalized_content = validated.model_dump(mode="json")

        scope = make_scope(
            actor=actor,
            method="PATCH",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload={
                "expected_revision": body.expected_revision,
                "change_reason": body.change_reason,
                "content": normalized_content,
            },
        )

        def _execute() -> dict[str, Any]:
            if draft.revision != body.expected_revision:
                raise ServiceError(
                    409,
                    "STALE_REVISION",
                    "Версия черновика устарела; загрузите актуальное состояние.",
                    field="expected_revision",
                )
            if draft.status not in ("editing", "returned"):
                raise ServiceError(
                    409,
                    "INVALID_STATE",
                    "Изменять содержимое можно только в статусах editing или returned.",
                )
            sources_by_id = self._load_org_sources_for_draft(session, actor.organization_id, validated)
            self._verify_draft_quotes(validated, sources_by_id)

            now = utcnow()
            draft.content = normalized_content
            draft.contour = "training" if validated.is_synthetic else "working"
            draft.revision += 1
            draft.content_revision += 1
            draft.accepted_content_revision = None
            draft.accepted_source_revisions = None
            draft.accepted_by_actor_id = None
            draft.accepted_at = None
            draft.updated_at = now

            session.add(
                DraftEvent(
                    draft_id=draft.id,
                    organization_id=actor.organization_id,
                    actor_id=actor.actor_id,
                    action="edited",
                    draft_revision=draft.revision,
                    content_revision=draft.content_revision,
                    reason=body.change_reason,
                    details={
                        "source_revisions": {str(sid): src.revision for sid, src in sources_by_id.items()},
                    },
                    created_at=now,
                )
            )
            session.flush()
            return _serialize_draft(draft).model_dump(mode="json")

        return self._run_idempotent(session, scope=scope, status_code=200, action=_execute)

    def submit_draft(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        draft_id: uuid.UUID,
        body: DraftSubmitIn,
        authorization_header: str | None = None,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        draft = self._get_draft_for_actor(session, actor, draft_id)

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload=body.model_dump(mode="json"),
        )

        def _execute() -> dict[str, Any]:
            if draft.revision != body.expected_revision:
                raise ServiceError(
                    409,
                    "STALE_REVISION",
                    "Версия черновика устарела; загрузите актуальное состояние.",
                    field="expected_revision",
                )
            if draft.status not in ("editing", "returned"):
                raise ServiceError(
                    409,
                    "INVALID_STATE",
                    "Направить на согласование можно только черновик в статусе editing или returned.",
                )
            reviewer = self._actor_directory.get_actor_in_organization(
                body.reviewer_actor_id,
                actor.organization_id,
                authorization_header=authorization_header,
            )
            if reviewer is None or not reviewer.has_any_role("department", "hr", "admin"):
                raise ServiceError(
                    422,
                    "VALIDATION_ERROR",
                    "Указан недоступный или неуполномоченный согласующий для этой организации.",
                    field="reviewer_actor_id",
                )

            now = utcnow()
            draft.status = "in_review"
            draft.assigned_reviewer_actor_id = reviewer.actor_id
            draft.revision += 1
            draft.accepted_content_revision = None
            draft.accepted_source_revisions = None
            draft.accepted_by_actor_id = None
            draft.accepted_at = None
            draft.updated_at = now

            session.add(
                DraftEvent(
                    draft_id=draft.id,
                    organization_id=actor.organization_id,
                    actor_id=actor.actor_id,
                    action="submitted",
                    draft_revision=draft.revision,
                    content_revision=draft.content_revision,
                    reason=None,
                    details={"reviewer_actor_id": str(reviewer.actor_id)},
                    created_at=now,
                )
            )
            session.flush()
            return _serialize_draft(draft).model_dump(mode="json")

        return self._run_idempotent(session, scope=scope, status_code=200, action=_execute)

    def review_draft(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        draft_id: uuid.UUID,
        body: DraftReviewIn,
    ) -> CommandResult:
        require_draft_reader(actor)
        draft = session.scalar(
            select(Draft).where(
                Draft.id == draft_id,
                Draft.organization_id == actor.organization_id,
            )
        )
        if draft is None:
            raise ServiceError(404, "NOT_FOUND", "Черновик не найден.")

        is_assigned = draft.assigned_reviewer_actor_id == actor.actor_id
        if not is_assigned:
            if not actor.has_any_role("admin"):
                raise ServiceError(
                    403,
                    "FORBIDDEN",
                    "Согласовать или вернуть черновик может только назначенный согласующий либо администратор с причиной замещения.",
                )
            if not body.override_reason or not body.override_reason.strip():
                raise ServiceError(
                    422,
                    "VALIDATION_ERROR",
                    "При замещении согласующего администратор обязан указать override_reason.",
                    field="override_reason",
                )

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload=body.model_dump(mode="json"),
        )

        def _execute() -> dict[str, Any]:
            if draft.revision != body.expected_revision:
                raise ServiceError(
                    409,
                    "STALE_REVISION",
                    "Версия черновика устарела; загрузите актуальное состояние.",
                    field="expected_revision",
                )
            if draft.status != "in_review":
                raise ServiceError(
                    409,
                    "INVALID_STATE",
                    "Решение согласующего возможно только в статусе in_review.",
                )

            now = utcnow()
            draft.revision += 1
            draft.review_note = body.note
            draft.updated_at = now

            if body.result == "returned":
                draft.status = "returned"
                draft.accepted_content_revision = None
                draft.accepted_source_revisions = None
                draft.accepted_by_actor_id = None
                draft.accepted_at = None
                action_name = "review_returned"
                details: dict[str, Any] = {"override_reason": body.override_reason}
            else:
                validated = validate_draft_content(draft.content)
                sources_by_id = self._load_org_sources_for_draft(session, actor.organization_id, validated)
                accepted_sources = {str(sid): src.revision for sid, src in sources_by_id.items()}
                draft.status = "in_review"
                draft.accepted_content_revision = draft.content_revision
                draft.accepted_source_revisions = accepted_sources
                draft.accepted_by_actor_id = actor.actor_id
                draft.accepted_at = now
                action_name = "review_accepted"
                details = {
                    "accepted_content_revision": draft.content_revision,
                    "accepted_source_revisions": accepted_sources,
                    "override_reason": body.override_reason,
                }

            session.add(
                DraftEvent(
                    draft_id=draft.id,
                    organization_id=actor.organization_id,
                    actor_id=actor.actor_id,
                    action=action_name,
                    draft_revision=draft.revision,
                    content_revision=draft.content_revision,
                    reason=body.note,
                    details=details,
                    created_at=now,
                )
            )
            session.flush()
            return _serialize_draft(draft).model_dump(mode="json")

        return self._run_idempotent(session, scope=scope, status_code=200, action=_execute)

    def approve_draft(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        draft_id: uuid.UUID,
        body: DraftApproveIn,
        correlation_id: uuid.UUID,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        initial_draft = self._get_draft_for_actor(session, actor, draft_id)
        position_code = initial_draft.position_code
        # Закрыть read-транзакцию до ожидания внутрипроцессной блокировки, чтобы исключить
        # конфликт читателя/писателя в SQLite при конкурентных вызовах approve.
        session.rollback()

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload=body.model_dump(mode="json"),
        )
        position_lock = self._position_locks.lock_for(actor.organization_id, position_code)

        def _execute() -> dict[str, Any]:
            self._load_org_position(
                session,
                actor.organization_id,
                position_code,
                for_update=True,
            )
            draft = self._get_draft_for_actor(session, actor, draft_id)

            if draft.revision != body.expected_revision:
                raise ServiceError(
                    409,
                    "STALE_REVISION",
                    "Версия черновика устарела; загрузите актуальное состояние.",
                    field="expected_revision",
                )
            if draft.status != "in_review":
                raise ServiceError(
                    409,
                    "INVALID_STATE",
                    "Утвердить можно только черновик в статусе in_review.",
                )
            if (
                draft.accepted_content_revision is None
                or draft.accepted_content_revision != draft.content_revision
            ):
                raise ServiceError(
                    409,
                    "INVALID_STATE",
                    "Требуется положительное согласование текущей редакции содержимого.",
                )

            validated = validate_draft_content(draft.content)
            sources_by_id = self._load_org_sources_for_draft(session, actor.organization_id, validated)

            for source in sources_by_id.values():
                if source.extraction_status != "ready" or not source.extracted_text:
                    raise ServiceError(
                        409,
                        "SOURCE_NOT_READY",
                        "Нельзя утвердить профиль: один из источников не готов к проверке.",
                        field="content.sources",
                    )

            expected_revs = {str(sid): src.revision for sid, src in sources_by_id.items()}
            if (draft.accepted_source_revisions or {}) != expected_revs:
                raise ServiceError(
                    409,
                    "INVALID_STATE",
                    "Ревизия исходного документа изменилась после согласования; требуется повторное согласование.",
                )

            self._verify_draft_quotes(validated, sources_by_id)

            now = utcnow()
            current_profile = session.scalar(
                select(ApprovedProfile).where(
                    ApprovedProfile.organization_id == actor.organization_id,
                    ApprovedProfile.position_code == draft.position_code,
                    ApprovedProfile.contour == draft.contour,
                    ApprovedProfile.is_current.is_(True),
                )
            )
            if current_profile is not None:
                current_profile.is_current = False
                current_profile.updated_at = now
                session.flush()

            max_version = session.scalar(
                select(func.max(ApprovedProfile.version)).where(
                    ApprovedProfile.organization_id == actor.organization_id,
                    ApprovedProfile.position_code == draft.position_code,
                    ApprovedProfile.contour == draft.contour,
                )
            )
            next_version = (max_version or 0) + 1

            sources_snapshot = [
                {
                    "source_document_id": str(src.id),
                    "source_revision": src.revision,
                    "kind": src.document.kind,
                    "original_name": src.document.original_name,
                    "media_type": src.document.media_type,
                    "size_bytes": src.document.size_bytes,
                    "sha256": src.document.sha256,
                    "text_origin": src.text_origin,
                    "transcription_basis": src.transcription_basis,
                    "extracted_text": src.extracted_text,
                }
                for src in sources_by_id.values()
            ]

            profile_id = uuid.uuid4()
            approved = ApprovedProfile(
                id=profile_id,
                draft_id=draft.id,
                organization_id=actor.organization_id,
                position_code=draft.position_code,
                version=next_version,
                contour=draft.contour,
                revision=1,
                content=deepcopy(draft.content),
                sources_snapshot=sources_snapshot,
                approval_basis=body.approval_basis.strip(),
                approved_by_actor_id=actor.actor_id,
                approved_at=now,
                is_current=True,
                created_at=now,
                updated_at=now,
            )
            session.add(approved)

            draft.status = "approved"
            draft.revision += 1
            draft.updated_at = now

            session.add(
                DraftEvent(
                    draft_id=draft.id,
                    organization_id=actor.organization_id,
                    actor_id=actor.actor_id,
                    action="approved",
                    draft_revision=draft.revision,
                    content_revision=draft.content_revision,
                    reason=body.approval_basis.strip(),
                    details={
                        "approved_profile_id": str(profile_id),
                        "version": next_version,
                        "contour": draft.contour,
                    },
                    created_at=now,
                )
            )

            event_id = uuid.uuid4()
            envelope = {
                "event_id": str(event_id),
                "event_type": "requirements.approved",
                "schema_version": "1.0",
                "producer": self._settings.service_name,
                "organization_id": str(actor.organization_id),
                "aggregate_id": str(profile_id),
                "aggregate_revision": 1,
                "occurred_at": now.isoformat(),
                "correlation_id": str(correlation_id),
                "payload": {
                    "profile_id": str(profile_id),
                    "position_code": draft.position_code,
                    "profile_version": next_version,
                    "contour": draft.contour,
                    "approved_by_actor_id": str(actor.actor_id),
                    "approval_basis": body.approval_basis.strip(),
                    "source_document_ids": [str(s.source_document_id) for s in validated.sources],
                },
            }
            session.add(
                OutboxEvent(
                    event_id=event_id,
                    organization_id=actor.organization_id,
                    aggregate_id=profile_id,
                    aggregate_revision=1,
                    event_type="requirements.approved",
                    exchange=self._settings.outbox_exchange,
                    routing_key="requirements.approved",
                    correlation_id=correlation_id,
                    envelope=envelope,
                    status="pending",
                    attempts=0,
                    attempts_since_reset=0,
                    last_error=None,
                    next_attempt_at=now,
                    sent_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            return _serialize_profile(approved).model_dump(mode="json")

        with position_lock:
            result = self._run_idempotent(session, scope=scope, status_code=201, action=_execute)
        if not result.replayed and self._outbox_relay is not None:
            self._outbox_relay.wakeup()
        return result

    # --- Approved Profiles --------------------------------------------------------

    def revise_profile(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        profile_id: uuid.UUID,
        body: ProfileReviseIn,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        profile = session.scalar(
            select(ApprovedProfile).where(
                ApprovedProfile.id == profile_id,
                ApprovedProfile.organization_id == actor.organization_id,
            )
        )
        if profile is None:
            raise ServiceError(404, "NOT_FOUND", "Утверждённый профиль не найден.")

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload=body.model_dump(mode="json"),
        )

        def _execute() -> dict[str, Any]:
            now = utcnow()
            new_draft = Draft(
                organization_id=actor.organization_id,
                position_code=profile.position_code,
                contour=profile.contour,
                status="editing",
                revision=1,
                content_revision=1,
                content=deepcopy(profile.content),
                created_by_actor_id=actor.actor_id,
                created_at=now,
                updated_at=now,
            )
            session.add(new_draft)
            session.flush()
            session.add(
                DraftEvent(
                    draft_id=new_draft.id,
                    organization_id=actor.organization_id,
                    actor_id=actor.actor_id,
                    action="revised_from_profile",
                    draft_revision=1,
                    content_revision=1,
                    reason=body.change_reason,
                    details={
                        "source_profile_id": str(profile.id),
                        "source_profile_version": profile.version,
                    },
                    created_at=now,
                )
            )
            session.flush()
            return _serialize_draft(new_draft).model_dump(mode="json")

        return self._run_idempotent(session, scope=scope, status_code=201, action=_execute)

    def get_profile(
        self,
        session: Session,
        *,
        actor: Actor,
        profile_id: uuid.UUID,
    ) -> ApprovedProfileOut:
        require_draft_reader(actor)
        profile = session.scalar(
            select(ApprovedProfile).where(
                ApprovedProfile.id == profile_id,
                ApprovedProfile.organization_id == actor.organization_id,
            )
        )
        if profile is None:
            raise ServiceError(404, "NOT_FOUND", "Утверждённый профиль не найден.")
        return _serialize_profile(profile)

    def get_current_approved_profile(
        self,
        session: Session,
        *,
        actor: Actor,
        position_code: str,
        contour: Literal["training", "working"],
    ) -> ApprovedProfileOut:
        require_draft_reader(actor)
        profile = session.scalar(
            select(ApprovedProfile).where(
                ApprovedProfile.organization_id == actor.organization_id,
                ApprovedProfile.position_code == position_code,
                ApprovedProfile.contour == contour,
                ApprovedProfile.is_current.is_(True),
            )
        )
        if profile is None:
            raise ServiceError(
                404,
                "NO_APPROVED_PROFILE",
                "Для указанной должности и контура нет утверждённого профиля.",
            )
        return _serialize_profile(profile)

    # --- Outbox Deliveries --------------------------------------------------------

    def list_deliveries(
        self,
        session: Session,
        *,
        actor: Actor,
        status: Literal["pending", "failed", "sent"] | None,
        limit: int,
        cursor: str | None,
    ) -> PageOut[DeliveryOut]:
        require_hr_or_admin(actor)
        stmt = select(OutboxEvent).where(OutboxEvent.organization_id == actor.organization_id)
        if status is not None:
            stmt = stmt.where(OutboxEvent.status == status)
        stmt = apply_cursor_filter(stmt, OutboxEvent.created_at, OutboxEvent.event_id, cursor).limit(limit + 1)
        rows = list(session.scalars(stmt))
        items, next_cursor = build_page(
            rows,
            limit=limit,
            serializer=_serialize_delivery,
            get_id=lambda row: row.event_id,
        )
        return PageOut(items=items, next_cursor=next_cursor)

    def retry_delivery(
        self,
        session: Session,
        *,
        actor: Actor,
        idempotency_key: uuid.UUID,
        path: str,
        event_id: uuid.UUID,
    ) -> CommandResult:
        require_hr_or_admin(actor)
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_id == event_id,
                OutboxEvent.organization_id == actor.organization_id,
            )
        )
        if event is None:
            raise ServiceError(404, "NOT_FOUND", "Событие доставки не найдено.")

        scope = make_scope(
            actor=actor,
            method="POST",
            path=path,
            idempotency_key=idempotency_key,
            canonical_payload={"event_id": str(event_id), "action": "retry"},
        )

        def _execute() -> dict[str, Any]:
            if event.status == "sent":
                raise ServiceError(
                    409,
                    "INVALID_STATE",
                    "Событие уже успешно доставлено.",
                )
            now = utcnow()
            event.status = "pending"
            event.attempts_since_reset = 0
            event.next_attempt_at = now
            event.updated_at = now
            session.flush()
            return _serialize_delivery(event).model_dump(mode="json")

        result = self._run_idempotent(session, scope=scope, status_code=200, action=_execute)
        if not result.replayed and self._outbox_relay is not None:
            if self._outbox_relay.deliver_event_by_id(event_id):
                session.expire_all()
                refreshed = session.get(OutboxEvent, event_id)
                if refreshed is not None:
                    return CommandResult(
                        status_code=200,
                        body=_serialize_delivery(refreshed).model_dump(mode="json"),
                        replayed=False,
                    )
        return result
