"""Query annual reporting aggregates with exact distinct counts in each selected slice."""
from collections import Counter, defaultdict
from datetime import date
from itertools import product
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .loader import Package

RECEIVED = "applications_received"
HELD = "phone_interviews_held"
REACHED = "applications_with_phone_interview"
REPEAT = "repeat_interviews"
RATE = "continuation_pct"
CONTACT = "phone_within_14d_pct"
MEDIAN = "median_days_to_first_call"
OUTCOMES = ("continue", "stop", "pending")
GROUPS = ("total", "month", "quarter", "vacancy", "outcome")
OUTCOME_METRICS = {HELD, REACHED, REPEAT}
METRICS = {
    RECEIVED: ("Поступившие отклики", "отклики", "Разные отклики по дате поступления."),
    HELD: ("Телефонные интервью", "разговоры", "Разные состоявшиеся разговоры по дате проведения."),
    REACHED: ("Отклики с разговором", "отклики", "Один отклик учитывается единожды во всём выбранном срезе."),
    REPEAT: ("Повторные разговоры в срезе", "разговоры", "Число разговоров сверх первого с одним откликом внутри выбранного среза."),
    RATE: ("Продолжили отбор", "%", "Разговоры с исходом «Продолжили» среди разговоров с решениями «Продолжили» и «Завершили»."),
    CONTACT: ("Первый разговор за 14 дней", "%", "Среди откликов выбранного периода с полным окном наблюдения — доля состоявшихся первых разговоров в дни 0–13 после поступления."),
    MEDIAN: ("Медиана до первого разговора", "дни", "Дни от поступления до первого разговора среди откликов периода, с которыми поговорили до конца выбранного интервала."),
}


class AnalyticsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_month: int = Field(default=1, strict=True, ge=1, le=12)
    end_month: int = Field(default=12, strict=True, ge=1, le=12)
    vacancy_keys: list[str] = Field(default_factory=list)
    outcomes: list[Literal["continue", "stop", "pending"]] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=lambda: [RECEIVED, HELD, REACHED], min_length=1)
    group_by: list[Literal["total", "month", "quarter", "vacancy", "outcome"]] = Field(default_factory=lambda: ["total"], min_length=1)
    compare_previous: bool = True

    @model_validator(mode="after")
    def compatible(self):
        if self.start_month > self.end_month:
            raise ValueError("start_month должен предшествовать end_month или совпадать с ним")
        for values in (self.vacancy_keys, self.metrics, self.outcomes, self.group_by):
            if len(values) != len(set(values)):
                raise ValueError("Повторяющиеся параметры")
        if set(self.metrics) - METRICS.keys():
            raise ValueError("Неизвестный показатель")
        if "total" in self.group_by and len(self.group_by) > 1:
            raise ValueError("total используется отдельно")
        if {"month", "quarter"}.issubset(self.group_by):
            raise ValueError("Выберите одну единицу времени")
        if (self.outcomes or "outcome" in self.group_by) and set(self.metrics) - OUTCOME_METRICS:
            raise ValueError("Для выбранного показателя недоступен разрез по исходам")
        return self


def catalog():
    dimensions = dict(zip(GROUPS, ["Весь срез", "Месяц", "Квартал", "Вакансия", "Исход разговора"]))
    scenarios = [
        ("monthly", "Динамика подбора", [RECEIVED, HELD, REACHED], ["month"]),
        ("outcomes", "Исходы по кварталам", [HELD, REACHED], ["quarter", "outcome"]),
        ("vacancies", "Подбор по вакансиям", [RECEIVED, REACHED], ["vacancy"]),
        ("contact_speed", "Скорость первого контакта", [CONTACT, MEDIAN], ["month"]),
        ("repeats", "Повторные разговоры и решения", [REPEAT, RATE], ["quarter"]),
    ]
    return {"version": 1, "quality_scope": "source_package", "filters": [
        {"key": "start_month", "label": "С месяца", "min": 1, "max": 12},
        {"key": "end_month", "label": "По месяц включительно", "min": 1, "max": 12},
        {"key": "vacancy_keys", "label": "Вакансии", "values_from": "snapshot.vacancies"},
        {"key": "outcomes", "label": "Исходы разговора", "values": list(OUTCOMES)}],
        "metrics": [
        {"key": key, "label": attrs[0], "unit": attrs[1], "definition": attrs[2],
         "groups": [g for g in GROUPS if g != "outcome" or key in OUTCOME_METRICS],
         "allow_outcome_filter": key in OUTCOME_METRICS} for key, attrs in METRICS.items()],
        "dimensions": [{"key": key, "label": label} for key, label in dimensions.items()],
        "presets": [{"key": key, "label": label,
                     "query": AnalyticsQuery(metrics=metrics, group_by=groups).model_dump()}
                    for key, label, metrics, groups in scenarios]}


def _covered(intervals, start, end):
    """All calendar days in the half-open business interval are accounted for."""
    cursor = start
    for segment in intervals:
        if segment.start <= cursor:
            cursor = max(cursor, segment.end)
    return cursor >= end


def build_index(package: Package, year: int):
    """Histograms of identical anonymous patterns. Source record keys never leave memory."""
    by_app = defaultdict(list)
    for i in package.interviews.values():
        if i.day:
            by_app[i.application].append((i.day, i.result))
    patterns = Counter()
    cohorts = Counter()
    years = (year - 1, year)
    intervals = package.manifest.sources.phone_interviews.complete_intervals
    cutoff = package.manifest.observed_until
    for key, app in package.applications.items():
        calls = by_app[key]
        for y in years:
            frequency = Counter((day.month, outcome) for day, outcome in calls if day.year == y)
            if frequency:
                pattern = tuple(sorted((month, outcome, count) for (month, outcome), count in frequency.items()))
                patterns[(y, app.vacancy, pattern)] += 1
        if app.day is None or app.day.year not in years:
            continue
        first = min((day for day, _ in calls), default=None)
        lag = (first - app.day).days if first is not None else None
        first_month = (first.year * 12 + first.month) if first is not None else 0
        # Use day ordinals here to avoid date overflow on the final supported calendar year.
        window_end = app.day.toordinal() + 14
        mature = window_end <= cutoff.toordinal()
        phone_covered = mature and _covered(intervals, app.day, date.fromordinal(window_end))
        cohort = (app.day.year, app.day.month, app.vacancy, first_month, lag, mature, phone_covered)
        cohorts[cohort] += 1
    return {"version": 1,
            "patterns": [[y, vacancy, pattern, n] for (y, vacancy, pattern), n in sorted(patterns.items())],
            "cohorts": [[*cohort, n] for cohort, n in sorted(cohorts.items(), key=lambda pair: (
                pair[0][0], pair[0][1], pair[0][2], pair[0][3], pair[0][4] or 0, pair[0][5], pair[0][6]))]}


def _weighted_median(hist):
    total = hist.total()
    if not total:
        return None
    left, right = (total - 1) // 2, total // 2
    count = 0
    lower = None
    for days, n in sorted(hist.items()):
        count += n
        if lower is None and count > left:
            lower = days
        if count > right:
            return (lower + days) / 2


class QueryData:
    def __init__(self, report):
        self.report = report
        self.year = report["year"]
        self.sources = report["sources"]
        self.labels = {row["vacancy_key"]: row["label"] for row in report["vacancies"]}
        self.history = {self.year: report["months"], self.year - 1: report["previous_months"]}
        self.cutoff = date.fromisoformat(report["observed_until"])
        self.patterns = defaultdict(list)
        self.cohorts = defaultdict(list)
        index = report.get("analytics_index", {})
        if index.get("version") != 1:
            raise LookupError("Эта версия отчёта создана до появления конструктора. Сформируйте новую версию.")
        for year, vacancy, pattern, quantity in index["patterns"]:
            self.patterns[year, vacancy].append((pattern, quantity))
        for year, month, vacancy, first, lag, mature, covered, quantity in index["cohorts"]:
            self.cohorts[year, vacancy].append((month, first, lag, mature, covered, quantity))

    def source_status(self, year, months, metric):
        cells = [self.history[year][month - 1]["metrics"][metric] for month in months]
        observed = [c for c in cells if c["status"] != "future"]
        if not observed:
            return "future", ["outside_period"]
        states = {c["status"] for c in observed}
        if states == {"complete"}:
            return "complete", []
        reasons = sorted({r for c in observed for r in c["reason_codes"]})
        return ("unavailable" if states == {"unavailable"} else "partial"), reasons

    def calculate(self, year, months, vacancies, outcomes):
        arrivals = talks = reached = matured = within = immature = decided = continued = 0
        window_gap = invalid_history = False
        median_hist = Counter()
        end_month = year * 12 + max(months)
        for vacancy in vacancies:
            for pattern, quantity in self.patterns[year, vacancy]:
                calls = 0
                for month, outcome, count in pattern:
                    if month in months and outcome in outcomes:
                        calls += count
                        if outcome in {"continue", "stop"}:
                            decided += quantity * count
                        if outcome == "continue":
                            continued += quantity * count
                talks += quantity * calls
                reached += quantity * int(calls > 0)
            for month, first, lag, mature, covered, quantity in self.cohorts[year, vacancy]:
                if month not in months:
                    continue
                arrivals += quantity
                if lag is not None and lag < 0:
                    invalid_history = True
                if lag is not None and lag >= 0 and first <= end_month:
                    median_hist[lag] += quantity
                if mature:
                    matured += quantity
                    window_gap |= not covered
                    if lag is not None and 0 <= lag < 14:
                        within += quantity
                else:
                    immature += quantity

        app_state, app_reasons = self.source_status(year, months, RECEIVED)
        phone_state, phone_reasons = self.source_status(year, months, HELD)

        def cell(number, status, reasons, numerator=None, denominator=None):
            return {"value": number, "status": status, "reason_codes": reasons,
                    "numerator": numerator, "denominator": denominator}

        result = {}
        for key, number, state, reasons in ((RECEIVED, arrivals, app_state, app_reasons),
                (HELD, talks, phone_state, phone_reasons), (REACHED, reached, phone_state, phone_reasons),
                (REPEAT, talks - reached, phone_state, phone_reasons)):
            result[key] = cell(number if number or state == "complete" else None, state, reasons)

        def calculated(key, number, state, reasons, numerator, denominator, empty_reason):
            if state == "complete" and not denominator:
                state, reasons = "unavailable", [empty_reason]
            result[key] = cell(number if state == "complete" else None, state, reasons, numerator, denominator)

        calculated(RATE, round(100 * continued / decided, 2) if decided else None,
                   phone_state, phone_reasons, continued, decided, "no_decided_interviews")
        for key, denom, val, numerator in (
            (MEDIAN, median_hist.total(), _weighted_median(median_hist), None),
            (CONTACT, matured, round(100 * within / matured, 2) if matured else None, within),
        ):
            states = [app_state]
            reasons = list(app_reasons)
            if key == MEDIAN:
                states.append(phone_state)
                reasons.extend(phone_reasons)
            elif window_gap or self.report["quality"]["undated_interviews"]:
                states.append("partial")
                reasons.append("followup_coverage_gap")
            if invalid_history:
                states.append("partial")
                reasons.append("call_before_application")
            if app_state == "future":
                state = "future"
            elif "unavailable" in states:
                state = "unavailable"
            elif "partial" in states:
                state = "partial"
            else:
                state = "complete"
            calculated(key, val, state, sorted(set(reasons)), numerator, denom,
                       "no_mature_applications" if key == CONTACT else "no_reached_applications")
        result[CONTACT]["immature"] = immature
        return result

    def compare(self, key, current, previous, months, enabled):
        current.update(previous=None, delta=None, percent_change=None, comparison_reason=None)
        if not enabled:
            return
        streams = {RECEIVED: ("applications",), CONTACT: ("applications", "phone_interviews"),
                   MEDIAN: ("applications", "phone_interviews")}.get(key, ("phone_interviews",))
        last = max(months)
        period_end = date(self.year + int(last == 12), last % 12 + 1, 1)
        if self.cutoff < period_end:
            current["comparison_reason"] = "interim_period"
        elif any(not self.sources[s]["comparable_to_previous_year"] for s in streams):
            current["comparison_reason"] = "incomparable_source"
        elif key == CONTACT and (current["immature"] or previous["immature"]):
            current["comparison_reason"] = "immature_cohort"
        elif current["status"] != "complete" or previous["status"] != "complete":
            current["comparison_reason"] = "incomplete_or_undefined"
        else:
            baseline = previous["value"]
            delta = round(current["value"] - baseline, 4)
            current.update(previous=baseline, delta=delta)
            if baseline:
                current["percent_change"] = round(100 * delta / baseline, 2)
            else:
                current["comparison_reason"] = "zero_baseline"


def query_report(snapshot: dict, query: AnalyticsQuery):
    data = QueryData(snapshot)
    if set(query.vacancy_keys) - data.labels.keys():
        raise ValueError("Неизвестная вакансия")
    vacancies = sorted(query.vacancy_keys or data.labels)
    outcomes = list(query.outcomes or OUTCOMES)
    months = set(range(query.start_month, query.end_month + 1))
    dimensions = {
        "month": sorted(months),
        "quarter": sorted({(m - 1) // 3 + 1 for m in months}),
        "vacancy": vacancies,
        "outcome": outcomes,
        "total": [],
    }

    def aggregate(selected_months, selected_vacancies, selected_outcomes):
        current = data.calculate(data.year, selected_months, selected_vacancies, selected_outcomes)
        previous = (data.calculate(data.year - 1, selected_months, selected_vacancies, selected_outcomes)
                    if query.compare_previous else {})
        for key in query.metrics:
            data.compare(key, current[key], previous.get(key), selected_months, query.compare_previous)
        return {key: current[key] for key in query.metrics}

    totals = aggregate(months, vacancies, outcomes)
    rows = []
    warnings = set()
    groups = [g for g in query.group_by if g != "total"]
    for combination in product(*(dimensions[g] for g in groups)):
        row = dict(zip(groups, combination))
        selected_months = months
        if "month" in row:
            selected_months = {row["month"]}
        elif "quarter" in row:
            selected_months = {m for m in months if (m - 1) // 3 + 1 == row["quarter"]}
        cells = (aggregate(selected_months, [row["vacancy"]] if "vacancy" in row else vacancies,
                           [row["outcome"]] if "outcome" in row else outcomes) if groups else totals)
        rows.append({"dimensions": row, "metrics": cells})
        for metric in cells.values():
            warnings.update(metric["reason_codes"])
    basis = {key: snapshot[key] for key in (
        "metric_version", "scope_id", "scope_revision", "timezone", "observed_until", "extracted_at", "sources"
    )}
    basis["analytics_version"] = 1
    return {"snapshot_id": snapshot["snapshot_id"], "year": data.year, "query": query.model_dump(),
            "rows": rows, "totals": totals, "warnings": sorted(warnings), "basis": basis,
            "quality_scope": "source_package", "quality": snapshot["quality"]}
