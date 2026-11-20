"""Content-addressed catalogue with atomic publication of immutable versions."""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path


class InvalidSnapshot(ValueError):
    pass


def canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(snapshot: dict) -> str:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "analytics_index"}}
    return hashlib.sha256(canonical(payload)).hexdigest()


def valid_analytics(value: dict) -> bool:
    if "analytics_sha256" not in value:
        return "analytics_index" not in value
    return ("analytics_index" in value
            and hashlib.sha256(canonical(value["analytics_index"])).hexdigest() == value["analytics_sha256"])


def catalogue_dir() -> Path:
    return Path(os.environ.get("HR_REPORTS_DIR", Path.home() / ".hr-platform" / "annual-reports"))


def _valid_id(identifier: str) -> bool:
    return bool(re.fullmatch("[0-9a-f]{64}", identifier))


def _read(path: Path, mode: str) -> dict:
    try:
        value = json.loads(path.read_bytes())
        if (not isinstance(value, dict) or value.get("mode") != mode
                or value.get("snapshot_id") != path.stem or digest(value) != path.stem
                or not valid_analytics(value)):
            raise InvalidSnapshot("Нарушена целостность версии отчёта")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidSnapshot("Не удалось прочитать сохранённую версию отчёта") from exc
    return value


def save(snapshot: dict, root: Path) -> str:
    identifier = snapshot["snapshot_id"]
    mode = snapshot["mode"]
    if (mode not in {"work", "demo"} or not _valid_id(identifier)
            or digest(snapshot) != identifier or not valid_analytics(snapshot)):
        raise InvalidSnapshot("Неверная подпись или режим отчёта")
    directory = root / mode
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{identifier}.json"
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".annual-", delete=False) as file:
        temp = Path(file.name)
    try:
        with temp.open("wb") as stream:
            stream.write(canonical(snapshot))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            if os.name == "nt":
                # Windows rename refuses to replace an existing destination.
                os.rename(temp, destination)
            else:
                os.link(temp, destination)
        except FileExistsError:
            _read(destination, mode)
    finally:
        temp.unlink(missing_ok=True)
    return identifier


def read(identifier: str, root: Path, *, demo_only: bool = False, work_scope: str | None = None) -> dict:
    if _valid_id(identifier):
        for mode in (("demo",) if demo_only else ("work", "demo")):
            try:
                value = _read(root / mode / f"{identifier}.json", mode)
                if mode == "demo" or work_scope is None or value["scope_id"] == work_scope:
                    return value
            except FileNotFoundError:
                continue
    raise FileNotFoundError("Версия отчёта не найдена")


def list_versions(root: Path, year: int | None = None, *, demo_only: bool = False,
                  work_scope: str | None = None) -> list[dict]:
    rows = []
    for mode in (("demo",) if demo_only else ("work", "demo")):
        for path in (root / mode).glob("*.json"):
            value = _read(path, mode)
            if mode == "work" and work_scope is not None and value["scope_id"] != work_scope:
                continue
            if year is None or value["year"] == year:
                rows.append({key: value[key] for key in
                             ("snapshot_id", "year", "scope_label", "extracted_at", "mode")})
    return sorted(rows, key=lambda row: (datetime.fromisoformat(row["extracted_at"]),
                                         row["snapshot_id"]), reverse=True)
