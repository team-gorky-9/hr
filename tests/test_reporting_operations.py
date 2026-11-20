import json
import shutil
from pathlib import Path

import pytest

from app.reporting.loader import PackageError, load_manifest
from app.reporting.operations import build_operations, query_operations, read_operations

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/reporting/operations-demo"


def snapshot(directory):
    manifest = load_manifest(directory / "manifest.json")
    operations = read_operations(directory, manifest)
    return {"operations": build_operations(operations, manifest, 2025)}


def test_stocks_flows_reply_median_and_historical_backlog():
    report = snapshot(FIXTURE)
    jan = query_operations(report, 1, 1, [])
    assert jan["workforce"]["occupied_fte"]["value"] == 16
    assert jan["handoffs"]["sent"]["value"] == 3
    assert jan["handoffs"]["answered"]["value"] == 1  # sent the previous year
    assert jan["handoffs"]["open"]["value"] == 3
    assert jan["handoffs"]["open_over_15"]["value"] == 2  # exactly 15 days is excluded
    assert jan["handoffs"]["median_response_days"]["value"] == 13
    first_quarter = query_operations(report, "2025-01", "2025-03", ["it", "hr"])
    assert first_quarter["workforce"]["authorized_fte"]["value"] == 20.5
    assert first_quarter["workforce"]["headcount"]["value"] == 20
    assert first_quarter["workforce"]["hires"]["value"] == 4
    assert first_quarter["workforce"]["exits"]["value"] == 1
    assert first_quarter["handoffs"]["open"]["value"] == 1
    # 0, 13, 31, 32; median is taken across all response events.
    assert first_quarter["handoffs"]["median_response_days"]["value"] == 22
    assert query_operations(report, 1, 3, ["it"])["handoffs"]["median_response_days"]["value"] == 15.5
    serialized = json.dumps(report)
    for forbidden in ("transfer-a", "2024-12-20", "2025-02-16", "handoff_key", "sent_on", "answered_on"):
        assert forbidden not in serialized


@pytest.fixture
def directory(tmp_path):
    target = tmp_path / "export"
    return shutil.copytree(FIXTURE, target)


def change_config(directory, update):
    file = directory / "operations.json"
    cfg = json.loads(file.read_text(encoding="utf-8"))
    update(cfg)
    file.write_text(json.dumps(cfg), encoding="utf-8")


def test_incomplete_sources_and_missing_workforce_month(directory):
    change_config(directory, lambda cfg: cfg["sources"]["handoffs"].update(complete_intervals=[]))
    file = directory / "workforce.csv"
    file.write_text("\n".join(row for row in file.read_text().splitlines() if "2025-02,it" not in row))
    period = query_operations(snapshot(directory), 1, 2, [])
    assert period["workforce"]["headcount"]["value"] is None
    assert period["workforce"]["headcount"]["status"] == "partial"
    assert period["workforce"]["hires"]["value"] == 3
    assert period["workforce"]["hires"]["status"] == "partial"
    assert period["handoffs"]["open"]["value"] is None
    assert period["handoffs"]["median_response_days"]["value"] is None
    assert period["handoffs"]["answered"]["value"] == 4
    assert period["handoffs"]["answered"]["status"] == "partial"


def test_missing_opening_balance_and_zero_vs_absent(directory):
    change_config(directory, lambda cfg: cfg["sources"]["handoffs"].update(includes_opening_balance=False))
    march = query_operations(snapshot(directory), 3, 3, ["hr"])
    assert march["handoffs"]["sent"]["value"] == 0
    assert march["handoffs"]["open"]["value"] is None
    assert march["handoffs"]["open"]["status"] == "partial"
    assert march["handoffs"]["median_response_days"]["value"] is None
    # Legacy packages continue to work; absent optional sources never imply zero.
    legacy = snapshot(FIXTURE.parent / "demo")
    response = query_operations(legacy, 1, 12, [])
    assert response["available"] is False and response["workforce"]["headcount"]["value"] is None


def test_closed_month_and_contradictions(directory):
    with (directory / "workforce.csv").open("a") as out:
        out.write("2025-02,it,8,7,8,1,0\n")
    with pytest.raises(PackageError, match="invalid_row workforce.csv"):
        snapshot(directory)


def test_invalid_transfers_and_scope(directory):
    with (directory / "handoffs.csv").open("a") as out:
        out.write("transfer-corrupt,hr,2025-01-12,2025-01-10\n")
    with pytest.raises(PackageError, match="invalid_row handoffs.csv") as err:
        snapshot(directory)
    assert "transfer-corrupt" not in str(err.value)
    change_config(directory, lambda cfg: cfg.update(mode="work"))
    with pytest.raises(PackageError, match="invalid_manifest"):
        snapshot(directory)


def test_empty_register_requires_declaration_and_preserves_nulls(directory):
    (directory / "handoffs.csv").write_text("handoff_key,department_key,sent_on,answered_on\n")
    may = query_operations(snapshot(directory), 5, 5, [])
    assert may["handoffs"]["open"]["value"] == 0
    assert may["handoffs"]["median_response_days"]["value"] is None
    change_config(directory, lambda cfg: cfg["sources"].pop("handoffs"))
    with pytest.raises(PackageError):
        snapshot(directory)
    (directory / "handoffs.csv").unlink()
    may = query_operations(snapshot(directory), 5, 5, [])
    assert may["handoffs"]["open"]["status"] == "unavailable"


@pytest.mark.parametrize("start,end,depts", [(3, 1, []), (0, 12, []), ("2024-01", 12, []), (1, 2, ["x"])])
def test_query_refuses_unknown_filters(start, end, depts):
    with pytest.raises(PackageError):
        query_operations(snapshot(FIXTURE), start, end, depts)
