"""Load a declared, scope-limited export and validate it before reporting."""
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator


class PackageError(ValueError):
    """Safe diagnostic. Never embeds source data."""


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)


def read_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("expected YYYY-MM-DD")
    return date.fromisoformat(value)


class Interval(Schema):
    start: date = Field(alias="from")
    end: date = Field(alias="to")
    _dates = field_validator("start", "end", mode="before")(read_date)


class Source(Schema):
    source_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    complete_intervals: list[Interval]
    comparable_to_previous_year: StrictBool


class Sources(Schema):
    applications: Source
    phone_interviews: Source


class Manifest(Schema):
    input_schema_version: Literal[1]
    csv_delimiter: Literal[",", ";"]
    scope_id: str = Field(min_length=1)
    scope_label: str = Field(min_length=1)
    scope_revision: str = Field(min_length=1)
    mode: Literal["demo", "work"]
    timezone: str
    extracted_at: datetime
    observed_until: date
    sources: Sources
    vacancies: dict[str, str] | None = None

    _day = field_validator("observed_until", mode="before")(read_date)

    @field_validator("extracted_at", mode="before")
    @classmethod
    def timestamp(cls, value):
        if not isinstance(value, str) or "T" not in value:
            raise ValueError("expected timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError("offset required")
        return parsed


@dataclass(frozen=True)
class Application:
    key: str
    vacancy: str
    day: date | None


@dataclass(frozen=True)
class Interview:
    key: str
    application: str
    day: date | None
    result: str


@dataclass
class Package:
    manifest: Manifest
    applications: dict[str, Application]
    interviews: dict[str, Interview]
    duplicates: int
    fingerprint: str
    operations: object | None = None


def digest(value) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_manifest(path: Path) -> Manifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_members)
        if not isinstance(data, dict) or type(data.get("input_schema_version")) is not int:
            raise ValueError("invalid version")
        manifest = Manifest.model_validate(data)
        cutoff = manifest.observed_until
        if cutoff > manifest.extracted_at.astimezone(ZoneInfo(manifest.timezone)).date():
            raise ValueError("invalid cutoff")
        if manifest.vacancies is not None and any(
            not key.strip() or not label.strip() for key, label in manifest.vacancies.items()
        ):
            raise ValueError("invalid vacancy")
        for source in (manifest.sources.applications, manifest.sources.phone_interviews):
            source.complete_intervals.sort(key=lambda interval: (interval.start, interval.end))
            if any(not i.start < i.end <= cutoff for i in source.complete_intervals):
                raise ValueError("invalid coverage")
        return manifest
    except (OSError, ValueError, ValidationError, ZoneInfoNotFoundError) as exc:
        raise PackageError("invalid_manifest manifest.json") from exc


def rows(directory, name, columns, delimiter):
    try:
        with (directory / name).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, delimiter=delimiter, strict=True)
            if next(reader, []) != columns:
                raise PackageError(f"invalid_header {name}:1")
            for values in reader:
                if len(values) != len(columns) or any(not v.strip() for v in values[:2]):
                    raise PackageError(f"invalid_row {name}:{reader.line_num}")
                yield reader.line_num, values
    except (OSError, csv.Error, UnicodeError) as exc:
        raise PackageError(f"unreadable_file {name}") from exc


def load_package(directory: Path | str) -> Package:
    directory = Path(directory)
    manifest = load_manifest(directory / "manifest.json")
    applications = {}
    interviews = {}
    duplicates = 0
    normalized = {}
    specifications = (
        ("applications", ["application_key", "vacancy_key", "applied_on"], applications),
        ("phone_interviews", ["interview_key", "application_key", "held_on", "result"], interviews),
    )
    for stream, columns, records in specifications:
        name = stream + ".csv"
        normalized[stream] = {}
        for number, values in rows(directory, name, columns, manifest.csv_delimiter):
            key, related, raw_day, *rest = values
            try:
                day = read_date(raw_day) if raw_day else None
                if day and day >= manifest.observed_until:
                    raise ValueError("after_cutoff")
            except ValueError as exc:
                raise PackageError(f"invalid_date {name}:{number}") from exc
            if stream == "applications":
                if manifest.vacancies is not None and related not in manifest.vacancies:
                    raise PackageError(f"unknown_vacancy {name}:{number}")
                record = Application(key, related, day)
            else:
                if related not in applications:
                    raise PackageError(f"unknown_application {name}:{number}")
                result = rest[0]
                if result not in {"pending", "continue", "stop", "no_answer"} or (day and result == "no_answer"):
                    raise PackageError(f"invalid_outcome {name}:{number}")
                record = Interview(key, related, day, result)
            if key in records:
                if records[key] != record:
                    raise PackageError(f"conflicting_key {name}:{number}")
                duplicates += 1
            records[key] = record
            normalized[stream][key] = values
    normalized["manifest"] = manifest.model_dump(mode="json", by_alias=True)
    from .operations import read_operations

    operations = read_operations(directory, manifest)
    return Package(manifest, applications, interviews, duplicates, digest(normalized), operations)
