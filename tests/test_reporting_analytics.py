"""Regression checks for grouped reports, distinct counts and the time-to-contact cohort."""
import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.reporting.analytics import AnalyticsQuery, catalog, query_report
from app.reporting.engine import generate
from app.reporting.loader import Application, Interview, Interval, digest, load_package
from app.reporting.schema import Snapshot


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/reporting/demo"


def report():
    return generate(load_package(FIXTURE), 2025)


def query(snapshot, **params):
    return query_report(snapshot, AnalyticsQuery(**params))


def test_coverage_period_and_nonadditive_groups():
    r = report()
    selected = query(r, metrics=["phone_interviews_held", "applications_with_phone_interview", "repeat_interviews"],
                     group_by=["month", "outcome"], start_month=1, end_month=2)
    assert len(selected["rows"]) == 6
    assert selected["totals"]["phone_interviews_held"]["value"] == 4
    assert selected["totals"]["applications_with_phone_interview"]["value"] == 2
    assert selected["totals"]["repeat_interviews"]["value"] == 2
    assert sum(row["metrics"]["applications_with_phone_interview"]["value"] for row in selected["rows"]) == 4
    continued = query(r, metrics=["phone_interviews_held", "applications_with_phone_interview", "repeat_interviews"],
                      outcomes=["continue"], vacancy_keys=["consultant"], group_by=["quarter"])
    assert [cell["value"] for cell in continued["rows"][0]["metrics"].values()] == [2, 1, 1]


def test_cohort_denominators_and_latency_change_with_period():
    r = report()
    totals = query(r, metrics=["phone_within_14d_pct", "median_days_to_first_call", "continuation_pct"])["totals"]
    assert totals["phone_within_14d_pct"]["value"] == 50
    assert totals["phone_within_14d_pct"]["numerator"] == 1
    assert totals["phone_within_14d_pct"]["denominator"] == 2
    assert totals["median_days_to_first_call"]["value"] == 4
    assert totals["median_days_to_first_call"]["denominator"] == 1
    assert totals["continuation_pct"]["value"] == 66.67
    assert (totals["continuation_pct"]["numerator"], totals["continuation_pct"]["denominator"]) == (2, 3)

    p = load_package(FIXTURE)
    p.interviews["late"] = Interview("late", "C", date(2025, 3, 5), "stop")
    r = generate(p, 2025)
    selected = query(r, metrics=["median_days_to_first_call"], start_month=1, end_month=2)
    assert selected["totals"]["median_days_to_first_call"]["value"] == 4
    selected = query(r, metrics=["median_days_to_first_call"])
    assert selected["totals"]["median_days_to_first_call"]["value"] == 17


def test_mature_cutoff_and_exactly_fourteen_days():
    p = load_package(FIXTURE)
    p.applications["E"] = Application("E", "engineer", date(2026,1,1))
    p.applications["F"] = Application("F", "engineer", date(2026,1,25))
    p.interviews["e"] = Interview("e", "E", date(2026,1,15), "continue")
    r = generate(p, 2026)
    cell = query(r, metrics=["phone_within_14d_pct"], start_month=1, end_month=1)["totals"]["phone_within_14d_pct"]
    assert (cell["numerator"], cell["denominator"], cell["immature"]) == (1, 2, 1)
    assert cell["value"] == 50
    assert cell["comparison_reason"] == "immature_cohort"


def test_absent_events_and_coverage_across_month_boundary():
    p = load_package(FIXTURE)
    p.applications["late"] = Application("late", "engineer", date(2025,1,31))
    p.manifest.sources.phone_interviews.complete_intervals = [Interval.model_validate({"from":"2025-01-01","to":"2025-02-01"})]
    r = generate(p, 2025)
    january = query(r, start_month=1,end_month=1, metrics=["phone_within_14d_pct","median_days_to_first_call"])
    sla = january["totals"]["phone_within_14d_pct"]
    assert sla["value"] is None and "followup_coverage_gap" in sla["reason_codes"]
    assert january["totals"]["median_days_to_first_call"]["value"] == 4
    p.manifest.sources.phone_interviews.complete_intervals = []
    p.interviews.clear()
    r = generate(p, 2025)
    totals = query(r, metrics=["applications_received","continuation_pct","median_days_to_first_call"])["totals"]
    assert totals["applications_received"]["value"] == 3
    assert totals["median_days_to_first_call"]["value"] is None
    assert totals["continuation_pct"]["status"] == "unavailable"


def test_groups_vacancy_and_yearly_comparisons():
    r = report()
    result = query(r, group_by=["quarter", "vacancy"], metrics=["applications_received"], end_month=5)
    assert len(result["rows"]) == 4
    assert {row["dimensions"]["quarter"] for row in result["rows"]} == {1, 2}
    cell = result["totals"]["applications_received"]
    assert cell["value"] == 2 and cell["previous"] == 0 and cell["comparison_reason"] == "zero_baseline"
    cell = query(r)["totals"]["applications_received"]
    assert (cell["previous"], cell["delta"], cell["percent_change"]) == (1,1,100)
    cell = query(r, compare_previous=False)["totals"]["applications_received"]
    assert cell["previous"] is None and cell["comparison_reason"] is None


def test_invalid_requests_and_legacy():
    for options in ({"metrics":["unknown"]}, {"start_month":12, "end_month":1},
                    {"group_by":["month", "quarter"]}, {"group_by":["total", "vacancy"]},
                    {"metrics":["continuation_pct"], "outcomes":["stop"]},
                    {"metrics":["applications_received"], "group_by":["outcome"]},
                    {"group_by":[]}, {"metrics":[]}):
        with pytest.raises(ValidationError):
            AnalyticsQuery(**options)
    r = report()
    with pytest.raises(ValueError, match="Неизвестная вакансия"):
        query(r, vacancy_keys=["ghost"])
    r.pop("analytics_index")
    with pytest.raises(LookupError):
        query(r)


def test_quality_presets_and_integrity_of_private_aggregates():
    r = report()
    for preset in catalog()["presets"]:
        assert query(r, **preset["query"])["rows"]
    raw = json.loads(json.dumps(r))
    public = Snapshot.model_validate(raw).model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert public.pop("snapshot_id") == digest(public)
    assert "analytics_index" not in public
    assert digest(raw["analytics_index"]) == raw["analytics_sha256"]
    index = json.dumps(raw["analytics_index"])
    for key in ('"A"', '"B"', '"p1"', '"p4"'):
        assert key not in index
    assert query(raw, metrics=["median_days_to_first_call"]) == query(r, metrics=["median_days_to_first_call"])
