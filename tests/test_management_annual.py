"""4B: годовой выпуск из фактов legacy-hr (wave-4-reporting-stage-1) существующим годовым модулем."""
from datetime import date

import pytest

from app.db import repository as repo
from app.db.models import AnnualReportRelease, Application, Interview
from tests.posting_helpers import posting_registry  # noqa: F401 (фикстура)
from tests.test_api import client  # noqa: F401 (фикстура)
from tests.test_api_interview import HR, case, training_profile

PATH = "/api/v1/management/annual-reports"
BODY = {"year": 2026, "observed_until": "2026-11-21", "contour": "training",
        "coverage": {"applications": {"complete_intervals": [{"from": "2026-11-01", "to": "2026-11-21"}],
                                      "comparable_to_previous_year": False}},
        "confirmation_basis": "Учебный журнал legacy-hr за ноябрь, заявлено кадровиком hr_demo"}


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("HR_REPORTS_DIR", str(tmp_path / "reports"))
    return tmp_path / "reports"


def meeting(session, client, profile, code, applied_on, result=None, occurred_at=None):  # noqa: F811
    data = case(session, profile, code)
    session.get(Application, data["application_id"]).applied_at = applied_on
    interview = repo.open_interview(session, data["application_id"], "phone")
    session.commit()
    if result:
        response = client.post(f"/api/v1/interviews/{interview.id}/outcome", headers=HR, json={
            "expected_revision": 1, "result": result, "occurred_at": occurred_at, "summary": "Учебный итог встречи"})
        assert response.status_code == 200, response.text
    return interview


def test_release_json_excel_partial_coverage_and_new_version(session, client, posting_registry, catalog):  # noqa: F811
    profile = training_profile(session)
    meeting(session, client, profile, "py-9601", date(2026, 11, 18), "continue", "2026-11-20T23:59:00+03:00")
    meeting(session, client, profile, "py-9602", date(2026, 11, 19), "no_answer", "2026-11-20T10:00:00+03:00")
    meeting(session, client, profile, "py-9603", date(2026, 11, 19))                     # открытая встреча
    late = meeting(session, client, profile, "py-9604", None)                            # отклик без даты
    session.get(Interview, late.id).result = "continue"                                  # итог без даты разговора
    session.commit()

    created = client.post(PATH, headers=HR, json=BODY)
    assert created.status_code == 201, created.text
    release = created.json()
    assert (release["mode"], release["year"], release["contour"]) == ("demo", 2026, "training")
    assert release["report_url"] == f"{PATH}/{release['snapshot_id']}"
    assert release["preparation"]["applications"] == 4 and release["preparation"]["phone_interviews"] == 4
    summary = release["coverage_summary"]
    assert summary["interim"] is True and summary["period"] == {"from": "2026-01-01", "to": "2026-11-21"}
    assert summary["totals_status"]["applications_received"] == "partial"  # полнота заявлена только за ноябрь
    assert summary["quality"]["undated_interviews"] == 1 and summary["quality"]["undated_applications"] == 1

    read = client.get(release["report_url"], headers=HR)
    assert read.status_code == 200
    report = read.json()["report"]
    assert report["snapshot_id"] == release["snapshot_id"] and report["mode"] == "demo"
    # no_answer не прибавляется к проведённым: один разговор (py-9601), нижняя граница при неполноте.
    held = report["totals"]["phone_interviews_held"]
    assert held == {"value": 1, "status": "partial", "reason_codes": ["missing_business_date", "coverage_gap"]}
    november = next(m for m in report["months"] if m["month"] == "2026-11")
    assert november["metrics"]["applications_received"]["value"] == 3
    assert november["outcomes"]["continue"]["value"] == 1 and november["outcomes"]["stop"]["value"] is None
    assert report["sources"]["phone_interviews"]["complete_intervals"] == []  # полнота не заявлена — не обещана
    assert "Мар" not in str(report)  # пакет без ФИО и текстов: только технические ключи
    xlsx = client.get(release["xlsx_url"], headers=HR)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")

    # Поздняя поправка источника: ещё один разговор → новый выпуск, прежний читается без изменений.
    meeting(session, client, profile, "py-9605", date(2026, 11, 20), "stop", "2026-11-20T15:00:00+03:00")
    second = client.post(PATH, headers=HR, json=BODY).json()
    assert second["snapshot_id"] != release["snapshot_id"]
    assert client.get(release["report_url"], headers=HR).json()["report"] == report
    assert session.query(AnnualReportRelease).count() == 2


def test_declared_coverage_gives_exact_interview_count(session, client, posting_registry, catalog):  # noqa: F811
    profile = training_profile(session)
    meeting(session, client, profile, "py-9611", date(2026, 1, 10), "continue", "2026-01-12T12:00:00+03:00")
    meeting(session, client, profile, "py-9612", date(2026, 1, 11), "no_answer", "2026-01-12T13:00:00+03:00")
    full = {"complete_intervals": [{"from": "2025-01-01", "to": "2026-11-21"}], "comparable_to_previous_year": True}
    body = BODY | {"coverage": {"applications": full, "phone_interviews": full}}
    release = client.post(PATH, headers=HR, json=body).json()
    report = client.get(release["report_url"], headers=HR).json()["report"]
    assert report["totals"]["phone_interviews_held"] == {"value": 1, "status": "complete", "reason_codes": []}
    assert report["totals"]["applications_received"]["value"] == 2


def test_rejections(session, client, catalog):  # noqa: F811
    assert client.post(PATH, headers={"X-User-Login": "dept_demo"}, json=BODY).status_code == 403
    future = client.post(PATH, headers=HR, json=BODY | {"observed_until": "2099-01-01"})
    assert (future.status_code, future.json()["error"]["code"]) == (422, "INVALID_OBSERVED_UNTIL")
    beyond = BODY | {"coverage": {"applications": {"complete_intervals": [{"from": "2026-11-01", "to": "2026-12-01"}]}}}
    failed = client.post(PATH, headers=HR, json=beyond)
    assert (failed.status_code, failed.json()["error"]["code"]) == (422, "PREPARATION_FAILED")
    assert client.post(PATH, headers=HR, json=BODY | {"confirmation_basis": ""}).status_code == 422
    assert client.get(f"{PATH}/{'a' * 64}", headers=HR).json()["error"]["code"] == "REPORT_NOT_FOUND"
    assert client.get(f"{PATH}/not-an-id", headers=HR).status_code == 422
    assert client.get(f"{PATH}/{'a' * 64}", headers={"X-User-Login": "dept_demo"}).status_code == 403
    assert session.query(AnnualReportRelease).count() == 0
    assert not list((catalog / "demo").glob("*.json")) if (catalog / "demo").exists() else True
