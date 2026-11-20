"""Original files on disk under FILE_ROOT/<organization_id>/<document_id>.

The file is written to a temporary name, flushed to disk and renamed before the database row
exists, so the API never points at a half-written file. A temporary name is never served."""
import hashlib
import os
import uuid
from pathlib import Path

from hiring.errors import Problem

CHUNK = 1024 * 1024

# Accepted originals and their leading bytes. The media type is taken from the content,
# not from the client's Content-Type, so a renamed executable is not stored as a PDF.
SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def sniff(head: bytes) -> str | None:
    for prefix, media_type in SIGNATURES:
        if head.startswith(prefix):
            return media_type
    return None


class StoredFile:
    def __init__(self, key: str, size: int, sha256: str, media_type: str):
        self.key, self.size, self.sha256, self.media_type = key, size, sha256, media_type


def save(root: Path, organization_id: uuid.UUID, document_id: uuid.UUID, stream, max_bytes: int) -> StoredFile:
    folder = root / str(organization_id)
    folder.mkdir(parents=True, exist_ok=True)
    key = f"{organization_id}/{document_id}"
    final = root / key
    temporary = folder / f".{document_id}.part"
    digest, size, head = hashlib.sha256(), 0, b""
    try:
        with open(temporary, "wb") as out:
            while chunk := stream.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise Problem(413, "FILE_TOO_LARGE", f"File is larger than {max_bytes} bytes", "file")
                if len(head) < 16:
                    head += chunk[: 16 - len(head)]
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if size == 0:
            raise Problem(422, "VALIDATION_ERROR", "File is empty", "file")
        media_type = sniff(head)
        if media_type is None:
            raise Problem(422, "VALIDATION_ERROR", "Only PDF, JPEG and PNG originals are accepted", "file")
        os.replace(temporary, final)
        directory = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return StoredFile(key, size, digest.hexdigest(), media_type)


def remove(root: Path, key: str) -> None:
    """Used only when the database row could not be committed: the file has no owner yet."""
    (root / key).unlink(missing_ok=True)


def path_of(root: Path, key: str) -> Path:
    return root / key
