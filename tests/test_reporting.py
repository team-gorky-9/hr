import json
import os
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import httpx
import pytest
from fastapi.testclient import TestClient

from app.reporting import store
from app.reporting.api import create_app
from app.reporting.engine import generate
from app.reporting.loader import PackageError, load_package


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/reporting/demo"


@pytest.fixture
def package(tmp_path):
    return shutil.copytree(FIXTURE, tmp_path / "input")


def change_manifest(path, transform):
    manifest = path / "manifest.json"
    data = json.loads(manifest.read_bytes())
    transform(data)
    manifest.write_text(json.dumps(data), encoding="utf-8")


def run(path, year=2025):
    return generate(load_package(path), year)


def test_full_report(package):
    report = run(package)
    assert [metric["value"] for metric in report["totals"].values()] == [2, 4, 2]
    assert report["comparison"]["applications_received"]["percent"] == 100
    assert report["comparison"]["phone_interviews_held"] == {"delta": 4, "percent": None, "reason": "zero_baseline"}
    assert report["months"][0]["outcomes"]["continue"]["value"] == 1
    assert report["months"][0]["outcomes"]["pending"]["value"] == 1
    assert report["months"][0]["outcomes"]["stop"]["value"] == 1
    assert report["months"][0]["metrics"]["applications_with_phone_interview"]["value"] == 2
    assert report["months"][1]["metrics"]["applications_with_phone_interview"]["value"] == 1
    january = report["months"][0]["vacancies"]
    assert [row["vacancy_key"] for row in january] == ["consultant", "engineer"]
    assert january[1]["applications_received"]["value"] == 0
    assert january[1]["phone_interviews_held"]["value"] == 1


def test_missing_empty_and_coverage(package):
    interviews = package / "phone_interviews.csv"
    interviews.write_text("interview_key,application_key,held_on,result\n", encoding="utf-8")
    assert run(package)["totals"]["phone_interviews_held"]["value"] == 0
    change_manifest(package, lambda d: d["sources"]["phone_interviews"].update(complete_intervals=[]))
    assert run(package)["totals"]["phone_interviews_held"]["status"] == "unavailable"
    interviews.write_text("interview_key,application_key,held_on,result\ni,A,,stop\nj,A,2025-01-10,stop\n")
    report = run(package)
    assert report["quality"]["undated_interviews"] == 1
    assert report["totals"]["phone_interviews_held"]["status"] == "partial"
    assert report["months"][1]["metrics"]["phone_interviews_held"]["value"] is None
    assert report["months"][1]["metrics"]["applications_received"]["status"] == "complete"


def test_interim_and_leap_day(package):
    with (package / "applications.csv").open("a") as stream:
        stream.write("\nL,engineer,2024-02-29\n".lstrip("\n"))
    assert run(package, 2024)["months"][1]["metrics"]["applications_received"]["value"] == 1
    change_manifest(package, lambda d: d.update(observed_until="2026-01-20"))
    change_manifest(package, lambda d: [s.update(complete_intervals=[{"from":"2024-01-01","to":"2026-01-20"}])
                                        for s in d["sources"].values()])
    report = run(package, 2026)
    assert report["interim"] and report["period_end_exclusive"] == "2026-01-20"
    assert report["months"][0]["metrics"]["applications_received"]["value"] == 1
    assert report["months"][1]["metrics"]["applications_received"]["status"] == "future"
    assert report["comparison"]["applications_received"]["reason"] == "interim_period"


@pytest.mark.parametrize(("row", "error"), [
    ("p1,A,2025-01-11,continue", "conflicting_key"),
    ("new,unknown,2025-01-11,stop", "unknown_application"),
    ("new,A,2025-01-11,no_answer", "invalid_outcome"),
    ("new,A,2026-02-01,stop", "invalid_date"),
])
def test_rejected_rows(package, row, error):
    with (package / "phone_interviews.csv").open("a") as stream:
        stream.write(row + "\n")
    with pytest.raises(PackageError, match=error):
        load_package(package)


def test_idempotent_concurrent_and_correction(package, tmp_path):
    first = run(package)
    with ThreadPoolExecutor(4) as threads:
        ids = list(threads.map(lambda _: store.save(first, tmp_path), range(12)))
    assert len(set(ids)) == 1
    rows = package / "phone_interviews.csv"
    header, *values = rows.read_text().splitlines()
    rows.write_text("\n".join([header, *reversed(values)]) + "\n")
    assert run(package)["snapshot_id"] == ids[0]
    with rows.open("a") as stream:
        stream.write("new,A,2025-03-01,continue\n")
    second = run(package)
    assert store.save(second, tmp_path) != ids[0]
    assert second["totals"]["phone_interviews_held"]["value"] == 5
    assert store.read(ids[0], tmp_path)["totals"]["phone_interviews_held"]["value"] == 4


def test_hidden_work_and_corrupt_catalog(package, tmp_path):
    api = TestClient(create_app(tmp_path))
    base = "/api/v1/reports/annual"
    assert api.get(base).json() == []
    change_manifest(package, lambda d: d.update(mode="work"))
    identifier = store.save(run(package), tmp_path)
    assert api.get(base).json() == []
    assert api.get(f"{base}/{identifier}").status_code == 404
    assert api.get(f"{base}/{identifier}/xlsx").status_code == 404
    assert api.get(f"{base}/bad").status_code == 422
    change_manifest(package, lambda d: d.update(mode="demo"))
    identifier = store.save(run(package), tmp_path)
    (tmp_path / "demo" / f"{identifier}.json").write_text("{}")
    assert api.get(f"{base}/{identifier}").json()["error"]["code"] == "CORRUPT_REPORT"


def test_duplicate_rows_and_scope_metadata(package):
    applications = package / "applications.csv"
    with applications.open("a") as stream:
        stream.write("A,consultant,2025-01-04\n")
    assert run(package)["quality"]["duplicates"] == 1
    assert run(package)["totals"]["applications_received"]["value"] == 2
    change_manifest(package, lambda d: d["sources"]["applications"].update(comparable_to_previous_year=False))
    assert run(package)["comparison"]["applications_received"]["reason"] == "incomparable_source"
    change_manifest(package, lambda d: d["vacancies"].pop("consultant"))
    with pytest.raises(PackageError, match="unknown_vacancy"):
        run(package)


def test_partial_export_preserves_empty_and_bounds(package, tmp_path):
    change_manifest(package, lambda d: d["sources"]["applications"].update(complete_intervals=[]))
    report = run(package)
    identifier = store.save(report, tmp_path)
    api = TestClient(create_app(tmp_path))
    response = api.get(f"/api/v1/reports/annual/{identifier}/xlsx")
    response.raise_for_status()
    with ZipFile(BytesIO(response.content)) as book:
        xml = ET.fromstring(book.read("xl/worksheets/sheet2.xml"))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        assert xml.find(".//s:c[@r='B2']/s:v", ns).text == "1"
        assert xml.find(".//s:c[@r='B4']/s:v", ns) is None
        assert "Не менее" in book.read("xl/sharedStrings.xml").decode("utf-8")
        assert "A6ABB2" in book.read("xl/charts/chart3.xml").decode("utf-8")


def test_cli_to_http_excel(package, tmp_path):
    env = dict(os.environ, HR_REPORTS_DIR=str(tmp_path / "catalog"))
    def cli(*args, success=True):
        command = [sys.executable, "-m", "app.reporting", *map(str, args)]
        result = subprocess.run(command, env=env, capture_output=True, check=success)
        return json.loads(result.stdout) if success else result.returncode

    assert cli("validate", package)["applications"] == 4
    identifier = cli("generate", package, "--year", 2025)["snapshot_id"]
    assert cli("generate", package, "--year", 2025)["snapshot_id"] == identifier
    assert cli("list")[0]["snapshot_id"] == identifier
    destination = tmp_path / "report.xlsx"
    cli("export", identifier, "--output", destination)
    assert cli("generate", package, "--year", 2027, success=False) != 0
    assert len(cli("list")) == 1

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port),
                                "--host", "127.0.0.1", "--log-level", "warning"], env=env)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            base = "/api/v1/reports/annual"
            deadline = time.monotonic() + 15
            while True:
                try:
                    response = client.get(base)
                    break
                except httpx.ConnectError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise
                    time.sleep(0.15)
            assert response.json()[0]["snapshot_id"] == identifier
            assert client.get(base, params={"year":2024}).json() == []
            report = client.get(f"{base}/{identifier}").json()
            assert report["snapshot_id"] == store.digest(report)
            download = client.get(f"{base}/{identifier}/xlsx")
            download.raise_for_status()
            assert "spreadsheetml.sheet" in download.headers["content-type"]
            with ZipFile(BytesIO(download.content)) as book, ZipFile(destination) as from_cli:
                content = book.read("xl/worksheets/sheet1.xml")
                assert from_cli.read("xl/worksheets/sheet1.xml") == content
                root = ET.fromstring(content)
                ns = {"sheet":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                numbers = [root.find(f".//sheet:c[@r='B{row}']/sheet:v", ns).text for row in (8,9,10)]
                assert numbers == ["2", "4", "2"]
                assert len([n for n in book.namelist() if n.startswith("xl/charts/chart")]) == 3
                assert identifier in book.read("xl/sharedStrings.xml").decode("utf-8")
    finally:
        process.terminate()
        process.wait(timeout=8)
