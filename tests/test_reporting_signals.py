from datetime import date
from pathlib import Path

from app.reporting.engine import generate
from app.reporting.loader import Application, Interval, load_package
from app.reporting.signals import build_signals

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/reporting/demo"


def add_month(pkg, year, month, vacancy, count):
    for i in range(count):
        key = f"{year}-{month}-{vacancy}-{i}"
        pkg.applications[key] = Application(key, vacancy, date(year, month, 1))


def test_vacancy_contributions_reconcile_even_if_citywide_delta_is_zero():
    pkg = load_package(FIXTURE)
    pkg.applications.clear()
    pkg.interviews.clear()
    for year, a, b in [(2024, 10, 1), (2025, 7, 4)]:
        add_month(pkg, year, 7, "consultant", a)
        add_month(pkg, year, 8, "engineer", b)
    report = generate(pkg, 2025)
    result = build_signals(report)
    changes = result["contributions"]
    assert changes["current"] == changes["previous"] == 11
    assert changes["gross_change"] == 6 and changes["net_change"] == 0
    assert [row["delta"] for row in changes["rows"]] == [-3, 3]
    assert [row["share_of_net_pct"] for row in changes["rows"]] == [None,None]
    assert [row["share_of_gross_pct"] for row in changes["rows"]] == [50,50]
    heat = result["heatmap"]["cells"]
    assert len(heat) == 24 and sum(cell["value"] for cell in heat) == 11
    assert all(cell["status"] == "complete" for cell in heat)
    assert all(s["evidence"]["snapshot_id"] == report["snapshot_id"] for s in result["signals"])


def test_signal_ranks_against_past_only_with_robust_scale():
    pkg = load_package(FIXTURE)
    pkg.applications.clear()
    pkg.interviews.clear()
    for month, volume in enumerate([3,4,5,6,5,6,3,4,5,6,5,6], 1):
        add_month(pkg, 2024, month, "consultant", volume)
    add_month(pkg, 2025, 1, "consultant", 25)
    add_month(pkg, 2025, 9, "consultant", 100)
    result = build_signals(generate(pkg, 2025))
    january = result["unusual_volume"]["months"][0]
    assert january["status"] == "unusual"
    assert january["baseline_n"] == 12
    assert january["median"] == 5 and january["mad"] == 1
    assert january["deviation"] == 20 and january["score"] == round(20 / 1.4826, 4)
    assert max(january["baseline_months"]) == "2024-12"
    assert any(s["section"] == "unusual_volume" and s["evidence"]["month"] == "2025-01" for s in result["signals"])


def test_incomparable_years_excluded_and_minimum_six_months():
    pkg = load_package(FIXTURE)
    pkg.manifest.sources.applications.comparable_to_previous_year = False
    pkg.applications.clear()
    pkg.interviews.clear()
    add_month(pkg, 2025, 7, "consultant", 2)
    result = build_signals(generate(pkg, 2025))
    assert result["contributions"]["reason"] == "incomparable_source"
    january, june, july = [result["unusual_volume"]["months"][n] for n in (0,5,6)]
    assert january["baseline_n"] == 0
    assert june["baseline_n"] == 5 and june["status"] == "insufficient_history"
    assert july["status"] == "flat_baseline_change" and july["baseline_n"] == 6
    assert july["score"] is None and july["median"] == july["mad"] == 0


def test_tied_median_with_variation_and_incomplete_history():
    pkg = load_package(FIXTURE)
    # Eleven fully observed zero months and one nonzero month give MAD zero despite variation.
    result = build_signals(generate(pkg, 2025))
    assert result["unusual_volume"]["months"][0]["status"] == "zero_mad"
    pkg.manifest.sources.applications.complete_intervals = [
        Interval.model_validate({"from":"2024-12-01","to":"2025-01-01"}),
        Interval.model_validate({"from":"2025-02-01","to":"2025-12-01"}),
    ]
    result = build_signals(generate(pkg, 2025))
    january = result["unusual_volume"]["months"][0]
    assert january["status"] == "incomplete_target"
    assert january["baseline_months"] == ["2024-12"]
    assert result["contributions"]["reason"] == "incomplete_coverage"
    assert any(c["status"] == "partial" and c["value"] == 1 for c in result["heatmap"]["cells"])
    assert all(c["value"] is None for c in result["heatmap"]["cells"] if c["month"] == "2025-12")


def test_month_to_date_cannot_be_flagged_as_anomaly():
    pkg = load_package(FIXTURE)
    pkg.manifest.observed_until = date(2026,1,19)
    result = build_signals(generate(pkg, 2026))
    january = result["unusual_volume"]["months"][0]
    assert january["coverage"] == "complete"
    assert january["status"] == "open_or_future_month"
    assert result["contributions"]["reason"] == "interim_period"
