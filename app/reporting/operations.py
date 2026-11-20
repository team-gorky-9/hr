"""Optional workforce and department workflows. Persist only monthly department aggregates."""
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool

from .loader import Interval, Manifest, PackageError, Schema, read_date, rows, unique_members


class Register(Schema):
    source_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    complete_intervals: list[Interval]


class TransferRegister(Register):
    # Includes every unresolved transfer at the start of each complete interval.
    includes_opening_balance: StrictBool


class Registers(Schema):
    workforce: Register | None = None
    handoffs: TransferRegister | None = None


class OperationsManifest(Schema):
    schema_version: Literal[1]
    scope_id: str
    scope_revision: str
    mode: Literal["demo", "work"]
    departments: dict[str, str] = Field(min_length=1)
    sources: Registers


STOCK = ("authorized_fte", "occupied_fte", "headcount")
FLOWS = ("hires", "exits")
TRANSFERS = ("sent", "answered", "open", "open_over_15", "median_response_days")


@dataclass
class OperationsInput:
    settings: OperationsManifest
    workforce: dict[tuple[str, str], dict]
    transfers: dict[str, tuple[str, date, date | None]]


def _month(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("invalid month")
    return date.fromisoformat(value + "-01")


def _next_month(first: date) -> date:
    if first.month == 12:
        return date(first.year + 1, 1, 1)
    return date(first.year, first.month + 1, 1)


def _n(value: str, *, fractional: bool):
    pattern = r"[0-9]{1,9}(\.[0-9]{1,2})?" if fractional else r"[0-9]{1,9}"
    if not re.fullmatch(pattern, value):
        raise ValueError("invalid nonnegative quantity")
    return float(Decimal(value)) if fractional else int(value)


def read_operations(directory: Path, manifest: Manifest) -> OperationsInput | None:
    directory = Path(directory)
    metadata = directory / "operations.json"
    files = {name: (directory / f"{name}.csv").exists() for name in ("workforce", "handoffs")}
    if not metadata.exists():
        if any(files.values()):
            raise PackageError("missing_manifest operations.json")
        return None
    try:
        config = json.loads(metadata.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_members)
        if type(config.get("schema_version") if isinstance(config, dict) else None) is not int:
            raise ValueError("invalid version")
        settings = OperationsManifest.model_validate(config)
        if (settings.scope_id, settings.scope_revision, settings.mode) != (
            manifest.scope_id, manifest.scope_revision, manifest.mode
        ):
            raise ValueError("scope mismatch")
        if any(not key.strip() or not label.strip() for key, label in settings.departments.items()):
            raise ValueError("empty department")
        for name, exists in files.items():
            register = getattr(settings.sources, name)
            if (register is not None) != exists:
                raise ValueError("declared files mismatch")
            if register:
                register.complete_intervals.sort(key=lambda span: (span.start, span.end))
                if any(not span.start < span.end <= manifest.observed_until for span in register.complete_intervals):
                    raise ValueError("invalid coverage")
    except (OSError, ValueError) as exc:
        raise PackageError("invalid_manifest operations.json") from exc
    workforce = {}
    transfers = {}
    if files["workforce"]:
        headings = ["month", "department_key", *STOCK, *FLOWS]
        for line_no, (month, dept, *quantities) in rows(directory, "workforce.csv", headings, manifest.csv_delimiter):
            try:
                if dept not in settings.departments or _next_month(_month(month)) > manifest.observed_until:
                    raise ValueError("unexpected department or month")
                values = {key: _n(raw, fractional=key.endswith("_fte"))
                          for key, raw in zip(headings[2:], quantities, strict=True)}
                if values["occupied_fte"] > values["authorized_fte"]:
                    raise ValueError("occupied FTE exceeds authorised FTE")
                if (dept, month) in workforce and workforce[dept, month] != values:
                    raise ValueError("conflicting rows")
                workforce[dept, month] = values
            except (ValueError, OverflowError) as exc:
                raise PackageError(f"invalid_row workforce.csv:{line_no}") from exc
    if files["handoffs"]:
        headings = ["handoff_key", "department_key", "sent_on", "answered_on"]
        for line_no, (key, dept, sent, answered) in rows(directory, "handoffs.csv", headings, manifest.csv_delimiter):
            try:
                sent_on = read_date(sent)
                answered_on = read_date(answered) if answered else None
                if dept not in settings.departments or sent_on >= manifest.observed_until:
                    raise ValueError("unexpected department or date")
                if answered_on and not sent_on <= answered_on < manifest.observed_until:
                    raise ValueError("invalid answer date")
                record = dept, sent_on, answered_on
                if key in transfers and transfers[key] != record:
                    raise ValueError("conflicting rows")
                transfers[key] = record
            except ValueError as exc:
                raise PackageError(f"invalid_row handoffs.csv:{line_no}") from exc
    return OperationsInput(settings, workforce, transfers)


def _coverage(source, start, end, observed):
    if start >= end:
        return "future"
    cursor = start
    touched = False
    for span in source.complete_intervals if source else []:
        if span.end <= start or span.start >= end:
            continue
        touched = True
        if span.start <= cursor:
            cursor = max(cursor, span.end)
    if cursor >= end:
        return "complete"
    return "partial" if touched or observed else "unavailable"


def _cell(value, status, *, additive=False, reason=None):
    reasons = {"complete": [], "partial": [reason or "coverage_gap"],
               "unavailable": [reason or "coverage_unknown"], "future": ["outside_period"]}
    show = status == "complete" or (status == "partial" and additive and value)
    return {"value": value if show else None, "status": status, "reason_codes": reasons[status]}


def _workforce(data, dept, month, start, end, upper):
    source = data.settings.sources.workforce
    record = data.workforce.get((dept, month))
    result = {}
    for key in (*STOCK, *FLOWS):
        # The stock is measured on the final day of the closed month.
        left = upper - timedelta(days=1) if key in STOCK and end == upper else start
        status = _coverage(source, left, end, record is not None)
        if record is None and status == "complete":
            status = "partial"
        result[key] = _cell(record[key] if record else None, status, additive=key in FLOWS,
                            reason="missing_monthly_return" if record is None and source else None)
    return result


def _handoffs(records, source, start, end):
    sent = answered = pending = aged = 0
    waits = Counter()
    if end > start:
        for sent_on, answered_on in records:
            sent += start <= sent_on < end
            if answered_on and start <= answered_on < end:
                answered += 1
                waits[(answered_on - sent_on).days] += 1
            if sent_on < end and (answered_on is None or answered_on >= end):
                pending += 1
                aged += (end - timedelta(days=1) - sent_on).days > 15
    status = _coverage(source, start, end, sent or answered or pending)
    # A known opening balance at the start of a complete interval covers the stock at its end.
    balance_status = _coverage(source, end - timedelta(days=1), end, pending) if start < end else "future"
    missing_opening = balance_status == "complete" and not source.includes_opening_balance
    if missing_opening:
        balance_status = "partial"
    balance_reason = "opening_balance_unknown" if missing_opening else None
    result = {"sent": _cell(sent, status, additive=True), "answered": _cell(answered, status, additive=True),
              "open": _cell(pending, balance_status, reason=balance_reason),
              "open_over_15": _cell(aged, balance_status, reason=balance_reason),
              "median_response_days": _cell(_median(waits), status)}
    return result, dict(sorted(waits.items()))


def _median(histogram):
    size = sum(histogram.values())
    if not size:
        return None
    lower = (size - 1) // 2
    upper = size // 2
    position = 0
    middle = []
    for days, frequency in sorted(histogram.items()):
        for index in (lower, upper):
            if position <= index < position + frequency:
                middle.append(days)
        position += frequency
        if position > upper:
            break
    return sum(middle) / 2


def build_operations(data: OperationsInput | None, manifest: Manifest, year: int) -> dict | None:
    if data is None:
        return None
    if not 2 <= year <= 9998:
        raise PackageError("invalid_year")
    grouped = defaultdict(list)
    for dept, sent, answer in data.transfers.values():
        grouped[dept].append((sent, answer))
    months = []
    for number in range(1, 13):
        start = date(year, number, 1)
        stop = _next_month(start)
        end = min(stop, manifest.observed_until)
        month = start.isoformat()[:7]
        cells = {}
        for dept in sorted(data.settings.departments):
            transfers, waits = _handoffs(grouped[dept], data.settings.sources.handoffs, start, end)
            cells[dept] = {"workforce": _workforce(data, dept, month, start, end, stop),
                           "handoffs": transfers, "response_days_histogram": {str(k): v for k, v in waits.items()}}
        months.append({"month": month, "departments": cells})
    return {"year": year, "departments": dict(sorted(data.settings.departments.items())),
            "sources": data.settings.sources.model_dump(mode="json", by_alias=True), "months": months}


def _combined_status(cells):
    states = {cell["status"] for cell in cells}
    if states == {"future"}:
        return "future"
    states.discard("future")
    if states == {"complete"}:
        return "complete"
    return "unavailable" if states == {"unavailable"} else "partial"


def _aggregate(months, departments):
    all_rows = [month["departments"][key] for month in months for key in departments]
    # The historical cut is the last observed month of the requested range.
    elapsed = [month for month in months
               if month["departments"][departments[0]]["handoffs"]["sent"]["status"] != "future"]
    last = (elapsed or months)[-1]["departments"]
    last_rows = [last[key] for key in departments]
    sections = {"workforce": {}, "handoffs": {}}
    for section, metrics in (("workforce", (*STOCK, *FLOWS)), ("handoffs", TRANSFERS)):
        for metric in metrics:
            stock = metric in STOCK or metric in ("open", "open_over_15")
            selected = last_rows if stock else all_rows
            cells = [row[section][metric] for row in selected]
            status = _combined_status(cells)
            if metric == "median_response_days":
                hist = Counter()
                for row in selected:
                    hist.update({int(k): v for k, v in row["response_days_histogram"].items()})
                number = _median(hist)
            else:
                number = round(sum(cell["value"] or 0 for cell in cells), 2)
            combined = _cell(number, status, additive=not stock and metric != "median_response_days")
            if status == "partial":
                combined["reason_codes"] = sorted({reason for cell in cells if cell["status"] != "future"
                                                   for reason in cell["reason_codes"]}) or ["coverage_gap"]
            if metric == "median_response_days" and status == "complete" and number is None:
                combined["reason_codes"] = ["no_answers"]
            sections[section][metric] = combined
    return sections


def _select_month(value, year):
    if type(value) is int and 1 <= value <= 12:
        return value
    if isinstance(value, str) and re.fullmatch(fr"{year:04d}-(0[1-9]|1[0-2])", value):
        return int(value[-2:])
    raise PackageError("invalid_operations_period")


def query_operations(snapshot: dict, start_month, end_month, departments: list[str]) -> dict:
    ops = snapshot.get("operations")
    if ops is None:
        return {"available": False, "departments": [], "months": [], "by_department": [],
                "workforce": {k: _cell(None, "unavailable") for k in (*STOCK, *FLOWS)},
                "handoffs": {k: _cell(None, "unavailable") for k in TRANSFERS}}
    first, last = (_select_month(m, ops["year"]) for m in (start_month, end_month))
    if first > last:
        raise PackageError("invalid_operations_period")
    keys = list(dict.fromkeys(departments)) or sorted(ops["departments"])
    if any(key not in ops["departments"] for key in keys):
        raise PackageError("unknown_department")
    months = ops["months"][first - 1:last]
    options = [{"key": key, "label": ops["departments"][key]} for key in keys]
    return {"available": True, "departments": options, **_aggregate(months, keys),
            "months": [{"month": m["month"], **_aggregate([m], keys)} for m in months],
            "by_department": [{**item, **_aggregate(months, [item["key"]])} for item in options]}
