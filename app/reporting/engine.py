"""Pure calculation from a validated export, with explicit coverage of every series."""
from collections import Counter, defaultdict
from datetime import date
from typing import Literal

from .loader import Package, PackageError, Source, digest
from .analytics import build_index

RECEIVED = "applications_received"
HELD = "phone_interviews_held"
REACHED = "applications_with_phone_interview"
OUTCOMES = ("continue", "stop", "pending")
Status = Literal["complete", "partial", "unavailable", "future"]


def completeness(source: Source, start, end, observed, undated) -> tuple[Status, list[str]]:
    if start >= end:
        return "future", ["outside_period"]
    cursor = start
    overlaps = False
    for interval in source.complete_intervals:
        if interval.end <= start or interval.start >= end:
            continue
        overlaps = True
        if interval.start <= cursor:
            cursor = max(cursor, interval.end)
    if cursor >= end and not undated:
        return "complete", []
    reasons = []
    if undated:
        reasons.append("missing_business_date")
    if cursor < end:
        reasons.append("coverage_gap" if overlaps or observed else "coverage_unknown")
    if observed or overlaps or undated:
        return "partial", reasons
    return "unavailable", reasons


def value(number, quality):
    status, reasons = quality
    return {"value": number if status == "complete" or number else None,
            "status": status, "reason_codes": reasons}


def summarize(package, start, upper, vacancies, quality):
    end = min(upper, package.manifest.observed_until)
    arrivals = Counter()
    outcomes = Counter()
    reached = defaultdict(set)
    held_by_vacancy = Counter()
    for app in package.applications.values():
        if app.day is not None and start <= app.day < end:
            arrivals[app.vacancy] += 1
    for interview in package.interviews.values():
        if interview.day is not None and start <= interview.day < end:
            outcomes[interview.result] += 1
            vacancy = package.applications[interview.application].vacancy
            reached[vacancy].add(interview.application)
            held_by_vacancy[vacancy] += 1
    sources = package.manifest.sources
    app_quality = completeness(sources.applications, start, end, arrivals.total(), quality["undated_applications"])
    phone_quality = completeness(sources.phone_interviews, start, end, outcomes.total(), quality["undated_interviews"])
    ranking = [
        {"vacancy_key": key, "label": label, RECEIVED: value(arrivals[key], app_quality),
         REACHED: value(len(reached[key]), phone_quality), HELD: value(held_by_vacancy[key], phone_quality)}
        for key, label in sorted(vacancies.items(), key=lambda item: (-arrivals[item[0]], item[0]))
    ]
    return {
        "metrics": {RECEIVED: value(arrivals.total(), app_quality),
                    HELD: value(outcomes.total(), phone_quality),
                    REACHED: value(sum(map(len, reached.values())), phone_quality)},
        "outcomes": {name: value(outcomes[name], phone_quality) for name in OUTCOMES},
        "vacancies": ranking,
    }


def compare(current, previous, comparable, interim):
    reason = None
    delta = percent = None
    if interim:
        reason = "interim_period"
    elif not comparable:
        reason = "incomparable_source"
    elif current["status"] != "complete" or previous["status"] != "complete":
        reason = "incomplete_coverage"
    else:
        delta = current["value"] - previous["value"]
        if previous["value"] == 0:
            reason = "zero_baseline"
        else:
            percent = round(100 * delta / previous["value"], 2)
    return {"delta": delta, "percent": percent, "reason": reason}


def generate(package: Package, year: int) -> dict:
    manifest = package.manifest
    if not 2 <= year <= 9998 or date(year, 1, 1) >= manifest.observed_until:
        raise PackageError("invalid_year")
    quality = {
        "undated_applications": sum(app.day is None for app in package.applications.values()),
        "undated_interviews": sum(i.day is None and i.result in {"continue", "stop"}
                                  for i in package.interviews.values()),
        "duplicates": package.duplicates,
    }
    vacancies = manifest.vacancies
    if vacancies is None:
        vacancies = {app.vacancy: app.vacancy for app in package.applications.values()}

    def period(start, end):
        return summarize(package, start, end, vacancies, quality)

    def months(period_year):
        result = []
        for month in range(1, 13):
            start = date(period_year, month, 1)
            end = date(period_year + 1, 1, 1) if month == 12 else date(period_year, month + 1, 1)
            result.append({"month": start.strftime("%Y-%m"), **period(start, end)})
        return result

    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    current = period(start, end)
    previous = period(date(year - 1, 1, 1), start)
    interim = end > manifest.observed_until
    comparison = {}
    for metric, cell in current["metrics"].items():
        source = manifest.sources.applications if metric == RECEIVED else manifest.sources.phone_interviews
        comparison[metric] = compare(cell, previous["metrics"][metric], source.comparable_to_previous_year, interim)
    snapshot = {
        "report_schema_version": 1, "metric_version": "recruitment-v1",
        **manifest.model_dump(mode="json", by_alias=True, exclude={"input_schema_version", "csv_delimiter", "vacancies"}),
        "year": year, "period_start": start.isoformat(), "period_end_exclusive": min(end, manifest.observed_until).isoformat(),
        "interim": interim, "input_sha256": package.fingerprint, "quality": quality,
        "totals": current["metrics"], "previous_totals": previous["metrics"],
        "months": months(year), "previous_months": months(year - 1),
        "comparison": comparison, "vacancies": current["vacancies"],
    }
    if package.operations is not None:
        from .operations import build_operations
        snapshot["operations"] = build_operations(package.operations, manifest, year)
    index = build_index(package, year)
    snapshot["analytics_sha256"] = digest(index)
    snapshot["snapshot_id"] = digest(snapshot)
    snapshot["analytics_index"] = index
    return snapshot
