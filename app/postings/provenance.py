"""Deterministic package identity and append-only application source observations."""
import hashlib
import json
import unicodedata
import uuid
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.enums import ApplicationSource, Channel
from app.db.models import Application, ApplicationPostingSource

if TYPE_CHECKING:
    from app.ingest.package import InputFile


def normalized_source_path(path: str) -> str:
    return unicodedata.normalize("NFC", path.replace("\\", "/"))


def dataset_fingerprint(files: Iterable["InputFile"]) -> str:
    """Hash the complete input inventory, including failed/missing originals.

    Extraction output and processing order do not affect identity. Duplicate input
    records remain in the inventory. Missing bytes are represented by JSON null;
    an unsupported file with bytes still contributes its real SHA-256.
    """
    inventory = [{"source_path": normalized_source_path(item.source_path), "sha256": item.sha256} for item in files]
    inventory.sort(key=lambda record: (record["source_path"], record["sha256"] or ""))
    canonical = json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_source(
    session: Session,
    application_id: uuid.UUID,
    dataset_id: str,
    dataset_sha256: str,
    item: "InputFile",
    channel: Channel | str,
) -> None:
    """Record an actual RESPONSE import, never source-document inferred evidence."""
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must be a nonempty string")
    application = session.get(Application, application_id)
    if application is None or application.source != ApplicationSource.RESPONSE:
        raise ValueError("posting source requires an existing response application")
    if item.sha256 is None:
        raise ValueError("posting source requires original file bytes")
    source_path = normalized_source_path(item.source_path)
    session.execute(
        insert(ApplicationPostingSource).values(
            application_id=application_id,
            dataset_id=dataset_id,
            dataset_sha256=dataset_sha256,
            channel=str(channel),
            source_path=source_path,
            source_folder=PurePosixPath(source_path).parent.name,
            source_sha256=item.sha256,
        ).on_conflict_do_nothing(constraint="uq_application_posting_sources_origin")
    )
