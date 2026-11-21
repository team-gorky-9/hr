"""Resume intake without creating an application or selecting a vacancy."""
import base64
import hashlib
import os
from pathlib import Path

from sqlalchemy import select

from app.api.errors import ApiError
from app.db import repository as repo
from app.db.enums import AuditAction, Channel, DocumentKind, FileFormat
from app.db.models import Candidate
from app.ingest.extract import extract_text, ExtractError
from app.ingest.redact import redact, RedactionError, REDACTION_METHOD


def intake(session, body, user):
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (ValueError, TypeError):
        raise ApiError(422, "INVALID_FILE", "Некорректное содержимое файла") from None
    if not content or len(content) > 8 * 1024 * 1024:
        raise ApiError(422, "FILE_SIZE", "Размер файла должен быть от 1 байта до 8 МиБ")
    extension = Path(body.filename).suffix.lower()
    formats = {".txt": FileFormat.TXT, ".docx": FileFormat.DOCX, ".pdf": FileFormat.PDF}
    if extension not in formats:
        raise ApiError(422, "UNSUPPORTED_FORMAT", "Поддерживаются TXT, DOCX и PDF")
    digest = hashlib.sha256(content).hexdigest()
    folder = Path(os.environ.get("HR_RESUME_FILES", "data/resume-originals")).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (digest + extension)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise ApiError(409, "SOURCE_CONFLICT", "Контрольная сумма оригинала не совпадает")
    error = None
    try:
        raw = extract_text(content, extension)
    except ExtractError as exc:
        raw, error = "", exc.code
    document, _ = repo.add_source_document(session, kind=DocumentKind.RESUME, channel=Channel.OTHER,
        file_format=formats[extension], original_path=str(path), raw_text=raw, content=content,
        import_batch="resume-intake-v1")
    if document.kind != DocumentKind.RESUME:
        raise ApiError(409, "SOURCE_KIND_CONFLICT", "Этот оригинал сохранён как другой вид документа")
    candidate = session.scalar(select(Candidate).where(Candidate.source_document_id == document.id))
    if candidate is not None:
        if candidate.is_synthetic != (body.contour == "training"):
            raise ApiError(409, "CONTOUR_MISMATCH", "Файл уже принадлежит другому контуру")
        return {"status": "ready", "candidate_id": str(candidate.id), "document_id": str(document.id),
                "text_id": str(repo.get_current_text(session, candidate.id).id), "reused": True}
    if error:
        return {"status": "needs_review", "document_id": str(document.id), "reason": error,
                "candidate_id": None}
    try:
        cleaned = redact(raw, formats[extension])
    except RedactionError as exc:
        return {"status": "needs_review", "document_id": str(document.id), "reason": exc.code,
                "candidate_id": None}
    candidate = repo.create_candidate(session, code="rv-" + digest[:24], source_document_id=document.id,
        redacted_text=cleaned.text, redaction_method=REDACTION_METHOD, headline=cleaned.headline,
        pii=cleaned.pii, is_synthetic=body.contour == "training")
    repo.write_audit(session, action=AuditAction.OTHER, entity_type="resume_intake", entity_id=str(candidate.id),
                     details={"actor_id": str(user.id), "source_id": str(document.id)})
    return {"status": "ready", "candidate_id": str(candidate.id), "document_id": str(document.id),
            "text_id": str(repo.get_current_text(session, candidate.id).id), "reused": False}
