"""Management reporting contract, exercised against the ordinary network entry point."""
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import httpx
import pytest

from app.reporting.engine import generate
from app.reporting.loader import load_package
from app.reporting import store

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/reporting"
TOKEN = "local-test-service-key"
QUERY = {"start_month": 1, "end_month": 2, "vacancy_keys": ["consultant"],
         "outcomes": ["continue"], "metrics": ["phone_interviews_held", "applications_with_phone_interview"],
         "group_by": ["month"], "compare_previous": False}


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    catalog = tmp_path_factory.mktemp("management-catalog")
    ids = {}
    report = generate(load_package(FIXTURES / "operations-demo"), 2025)
    ids["demo"] = store.save(report, catalog)
    old = generate(load_package(FIXTURES / "demo"), 2025)
    old.pop("analytics_index")
    old.pop("analytics_sha256")
    old["snapshot_id"] = store.digest(old)
    ids["legacy"] = store.save(old, catalog)
    for scope in ("city-a", "city-b"):
        source = load_package(FIXTURES / "demo")
        source.manifest.mode = "work"
        source.manifest.scope_id = scope
        ids[scope] = store.save(generate(source, 2025), catalog)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, HR_REPORTS_DIR=str(catalog), HR_REPORTS_WORK_SCOPE="city-a",
               HR_REPORTS_WORK_TOKEN=TOKEN)
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                "--port", str(port), "--log-level", "warning"], env=env, cwd=ROOT)
    try:
        address = f"http://127.0.0.1:{port}/api/v1/reports/annual"
        with httpx.Client(base_url=address + "/", timeout=10, trust_env=False, follow_redirects=True) as client:
            deadline = time.monotonic() + 20
            while True:
                try:
                    client.get("").raise_for_status()
                    break
                except httpx.ConnectError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise
                    time.sleep(.1)
            yield client, address, ids
    finally:
        process.terminate()
        process.wait(timeout=10)


def workbook_sheets(content):
    """Read the OOXML workbook as delivered, resolving sheet relationships and shared strings."""
    ns = {"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "p":"http://schemas.openxmlformats.org/package/2006/relationships"}
    result = {}
    with ZipFile(BytesIO(content)) as book:
        sst = ET.fromstring(book.read("xl/sharedStrings.xml"))
        strings = ["".join(part.text or "" for part in item.findall(".//m:t", ns)) for item in sst]
        refs = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.get("Id"): rel.get("Target") for rel in refs}
        sheets = ET.fromstring(book.read("xl/workbook.xml"))
        for sheet in sheets.findall(".//m:sheet", ns):
            target = targets[sheet.get("{" + ns["r"] + "}id")]
            rows = []
            xml = ET.fromstring(book.read("xl/" + target))
            for row in xml.findall(".//m:sheetData/m:row", ns):
                values = {}
                for cell in row.findall("m:c", ns):
                    raw = cell.findtext("m:v", namespaces=ns)
                    if raw is not None:
                        col = cell.get("r").rstrip("0123456789")
                        values[col] = strings[int(raw)] if cell.get("t") == "s" else float(raw)
                rows.append(values)
            result[sheet.get("name")] = rows
    return result


def test_contracts_and_repeatability(service):
    client, _, ids = service
    path = ids["demo"]
    report = client.get(path).json()
    assert "analytics_index" not in report and store.digest(report) == path
    catalog = client.get(path + "/catalog").json()
    assert catalog["snapshot_id"] == path and catalog["available"] and catalog["operations_available"]
    assert {key for key in catalog["departments"]} == {"hr", "it"}
    for preset in catalog["presets"]:
        assert client.post(path + "/query", json=preset["query"]).status_code == 200

    signals = client.get(path + "/signals").json()
    assert signals["snapshot_id"] == path
    assert len(signals["heatmap"]["cells"]) == 24
    assert signals["contributions"]["net_change"] == 1
    assert client.get(path + "/signals").json() == signals
    brief = client.get(path + "/brief").json()
    assert brief["snapshot_id"] == path and brief["findings"]
    assert all(item["evidence"] and item["statement"] for item in brief["findings"])

    result = client.post(path + "/query", json=QUERY).json()
    assert result == client.post(path + "/query", json=QUERY).json()
    assert result["totals"]["phone_interviews_held"]["value"] == 2
    assert result["totals"]["applications_with_phone_interview"]["value"] == 1
    assert [row["dimensions"]["month"] for row in result["rows"]] == [1, 2]
    specs = client.post(path + "/charts", json=QUERY).json()
    assert specs["query"] == result["query"] and specs["snapshot_id"] == path
    assert [c["metric"] for c in specs["charts"]] == QUERY["metrics"]
    for chart in specs["charts"]:
        values = chart["spec"]["data"]["values"]
        assert [item["value"] for item in values] == [r["metrics"][chart["metric"]]["value"] for r in result["rows"]]


def test_workbook_matches_query_and_filters(service):
    client, _, ids = service
    path = ids["demo"]
    result = client.post(path + "/query", json=QUERY).json()
    response = client.post(path + "/query/xlsx", json=QUERY)
    response.raise_for_status()
    assert "spreadsheetml.sheet" in response.headers["content-type"]
    workbook = workbook_sheets(response.content)
    passport = {row["A"]: row["B"] for row in workbook["Параметры"] if "A" in row and "B" in row}
    assert passport["Версия отчёта"] == path
    for key in ("vacancy_keys", "outcomes", "metrics", "group_by"):
        assert json.loads(passport[key]) == QUERY[key]
    assert int(passport["start_month"]) == 1 and int(passport["end_month"]) == 2
    detail = [row for row in workbook["Анализ"] if row.get("J") == "Полные данные"]
    assert [row["C"] for row in detail] == [
        row["metrics"][key]["value"] for key in QUERY["metrics"] for row in result["rows"]
    ]
    totals = [row for row in workbook["Сводка среза"] if row.get("A") in
              ("Телефонные интервью", "Отклики с разговором")]
    assert [float(row["B"]) for row in totals] == [result["totals"][k]["value"] for k in QUERY["metrics"]]


def test_department_workbook_uses_same_period_and_department(service):
    client, _, ids = service
    path = ids["demo"]
    params = {"start_month": 1, "end_month": 3, "departments": ["it"]}
    response = client.post(path + "/operations", json=params)
    response.raise_for_status()
    result = response.json()
    assert result["snapshot_id"] == path and result["available"]
    assert result["handoffs"]["median_response_days"]["value"] == 15.5
    assert len(result["by_department"]) == 1 and len(result["months"]) == 3
    workbook = workbook_sheets(client.post(path + "/operations/xlsx", json=params).content)
    passport = {row.get("A"): row.get("B") for row in workbook["Параметры"]}
    assert json.loads(passport["departments"]) == ["it"]
    assert int(passport["end_month"]) == 3
    numbers = {row["C"]: row.get("D") for row in workbook["Штат и передачи"] if row.get("A") == "За период"}
    assert numbers["Медиана срока ответа, дн."] == result["handoffs"]["median_response_days"]["value"]
    assert numbers["Сотрудников"] == result["workforce"]["headcount"]["value"]


def test_legacy_and_validation(service):
    client, _, ids = service
    old = ids["legacy"]
    legacy = client.get(old).json()
    assert "analytics_sha256" not in legacy and "operations" not in legacy and store.digest(legacy) == old
    assert client.get(old + "/catalog").json()["available"] is False
    for suffix in ("/query", "/charts", "/query/xlsx"):
        response = client.post(old + suffix, json={})
        assert response.status_code == 409 and response.json()["error"]["code"] == "REBUILD_FOR_ANALYTICS"
    assert client.get(old + "/brief").status_code == 200
    assert client.get(old + "/signals").status_code == 200
    assert client.post(old + "/operations", json={}).json()["available"] is False
    assert client.get(old + "/xlsx").content.startswith(b"PK")
    for suffix, bad in [
        ("/query", {"metrics":["continuation_pct"], "outcomes":["stop"]}),
        ("/charts", {"vacancy_keys":["absent"]}),
        ("/query/xlsx", {"start_month": 4,"end_month":1}),
        ("/operations", {"departments":["absent"]}),
        ("/operations/xlsx", {"start_month":0}),
    ]:
        response = client.post(ids["demo"] + suffix, json=bad)
        assert response.status_code == 422 and response.json()["error"]["code"]


def test_every_endpoint_enforces_scope(service):
    client, _, ids = service
    authorized = {"Authorization": f"Bearer {TOKEN}"}
    invalid = {"Authorization": "Bearer invalid-test-key"}
    visible = lambda headers: {row["snapshot_id"] for row in client.get("", headers=headers).json()}
    assert visible({}) == {ids["demo"], ids["legacy"]}
    assert visible(authorized) == {ids["demo"], ids["legacy"], ids["city-a"]}
    assert client.get("", headers=invalid).status_code == 401
    routes = [("GET", suffix) for suffix in ("", "/xlsx", "/brief", "/signals", "/catalog")]
    routes += [("POST", suffix) for suffix in ("/query", "/charts", "/query/xlsx", "/operations", "/operations/xlsx")]
    for method, suffix in routes:
        body = {"json": {}} if method == "POST" else {}
        for key, headers, expected in [("city-a", {}, 404), ("city-a", invalid, 401),
                                        ("city-b", authorized, 404), ("city-a", authorized, 200)]:
            response = client.request(method, ids[key] + suffix, headers=headers, **body)
            assert response.status_code == expected, (suffix, key, response.status_code)
            if expected == 200:
                assert "no-store" in response.headers.get("Cache-Control", "")


def test_node_sdk_against_uvicorn(service, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise the JavaScript SDK")
    client, address, ids = service
    sdk = (ROOT / "integrations/reporting/client.mjs").as_uri()
    script = tmp_path / "check-sdk.mjs"
    script.write_text("""
import assert from 'node:assert/strict';
const [moduleUrl, base, demoId, workId, token] = process.argv.slice(2);
const {reportingClient} = await import(moduleUrl);
const client = reportingClient(base + '/');
assert.ok((await client.versions(2025)).some(x => x.snapshot_id === demoId));
assert.equal((await client.snapshot(demoId)).snapshot_id, demoId);
assert.ok((await client.catalog(demoId)).operations_available);
assert.ok((await client.brief(demoId)).findings.length);
assert.equal((await client.signals(demoId)).year, 2025);
const query = {start_month: 1, end_month: 2, vacancy_keys: ['consultant'], outcomes: ['continue'],
               metrics: ['phone_interviews_held'], group_by: ['month']};
assert.equal((await client.analyze(demoId, query)).totals.phone_interviews_held.value, 2);
assert.equal((await client.charts(demoId, query)).charts.length, 1);
const ops = {start_month: 1, end_month: 3, departments: ['it']};
assert.equal((await client.departments(demoId, ops)).handoffs.median_response_days.value, 15.5);
for (const blob of [await client.downloadReport(demoId), await client.downloadAnalysis(demoId, query),
                    await client.downloadDepartments(demoId, ops)]) {
  assert.match(blob.type, /spreadsheetml/);
  assert.equal(Buffer.from(await blob.arrayBuffer()).subarray(0, 2).toString(), 'PK');
}
await assert.rejects(client.analyze(demoId, {metrics:['unknown']}), e => e.status === 422 && !!e.code);
await assert.rejects(client.snapshot(workId), e => e.status === 404 && !!e.code);
const session = reportingClient(base, (url, opts) =>
  fetch(url, {...opts, headers:{...opts.headers, Authorization:'Bearer ' + token}}));
assert.equal((await session.snapshot(workId)).mode, 'work');
console.log('SDK integration passed');
""", encoding="utf-8")
    result = subprocess.run([node, str(script), sdk, address, ids["demo"], ids["city-a"], TOKEN],
                            capture_output=True, text=True, timeout=25, check=True)
    assert "SDK integration passed" in result.stdout
