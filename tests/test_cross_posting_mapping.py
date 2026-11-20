"""Cross-assessment must use resolved source roles and revalidate before cache reuse."""
import json
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.ai import FakeLLMClient
from app.assessment.cross import cross_assessments, run_cross_batch, select_pairs
from app.assessment.fixtures import create_fixture_profile
from app.assessment.service import assess_candidate
from app.db import repository as repo
from app.db.enums import ApplicationSource, Channel, DocumentKind, FileFormat, RequirementStatus
from app.db.models import AuditLog, Position, Vacancy
from app.ingest.package import InputFile
from app.postings.provenance import dataset_fingerprint, record_source
from tests.factories import approve
from tests.test_cross_assessment import AS_OF, BASE, FIXTURE, factory, responder, second_fixture


@pytest.fixture
def setup(session):
    """Start with no provenance; each test declares its own registry context."""
    python = create_fixture_profile(session, FIXTURE)
    hr = create_fixture_profile(session, second_fixture())
    approve(session, python)
    approve(session, hr)
    document, _ = repo.add_source_document(session, kind=DocumentKind.RESUME, channel=Channel.HH_RU,
        file_format=FileFormat.TXT, original_path="Синтетика/x-1.txt", raw_text="x-1\n" + BASE)
    candidate = repo.create_candidate(session, code="x-1", source_document_id=document.id, redacted_text=BASE,
        redaction_method="test", is_synthetic=True)
    vacancy = session.scalar(select(Vacancy).join(Position).where(Position.code == "python-dev"))
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
        vacancy_id=vacancy.id)
    return candidate, application, python, hr


def register(tmp_path, monkeypatch, session, application, *, target="hr-consultant", state="confirmed",
             version="v1", source_folder="source", append=False):
    item = InputFile(f"{source_folder}/resume.txt", b"cross-source", "text")
    fingerprint = dataset_fingerprint([item])
    record_source(session, application.id, "cross-test", fingerprint, item, "hh_ru")
    application.posting_title = "Original publication"
    session.flush()
    context = dict(dataset_id="cross-test", dataset_sha256=fingerprint, channel="hh_ru",
                   source_folder=source_folder, is_synthetic=True)
    rule = dict(id=f"decision-{source_folder}", context=context, match_kind="posting_title",
                posting_title="Original publication", decision_state=state)
    if state == "confirmed":
        rule.update(position_code=target, decision_author="Synthetic test owner", decision_date="2026-11-20",
                    decision_basis="Explicit synthetic mapping", evidence_refs=["fixture://cross"])
    root = tmp_path / "registry"
    (root / "versions").mkdir(parents=True, exist_ok=True)
    path = root / "versions" / f"{version}.json"
    rules = json.loads(path.read_text(encoding="utf-8"))["rules"] if append and path.exists() else []
    rules.append(rule)
    path.write_text(json.dumps(dict(schema_version="posting-register/1.0", version=version, rules=rules)), encoding="utf-8")
    (root / "current.json").write_text(json.dumps(dict(version=version)), encoding="utf-8")
    monkeypatch.setenv("POSTING_REGISTRY_DIR", str(root))


def test_confirmed_different_role_drives_primary_and_source_filter(session, setup, tmp_path, monkeypatch):
    candidate, application, _, _ = setup
    original_vacancy = application.vacancy_id
    register(tmp_path, monkeypatch, session, application)
    pairs, _ = select_pairs(session, technical=True, candidate_codes=[candidate.code])
    by_position = {pair.position_code: pair for pair in pairs}
    assert by_position["hr-consultant"].purpose == "primary"
    assert by_position["hr-consultant"].application_id == application.id
    assert by_position["python-dev"].purpose == "comparison"
    assert application.vacancy_id == original_vacancy
    selected, _ = select_pairs(session, technical=True, source_position_code="hr-consultant")
    assert {pair.candidate_id for pair in selected} == {candidate.id}
    excluded, _ = select_pairs(session, technical=True, source_position_code="python-dev")
    assert excluded == []


def test_missing_context_never_becomes_primary_from_imported_vacancy(session, setup, tmp_path, monkeypatch):
    candidate, application, _, _ = setup
    root = tmp_path / "registry"
    (root / "versions").mkdir(parents=True)
    (root / "versions" / "v1.json").write_text(
        '{"schema_version":"posting-register/1.0","version":"v1","rules":[]}', encoding="utf-8")
    (root / "current.json").write_text('{"version":"v1"}', encoding="utf-8")
    monkeypatch.setenv("POSTING_REGISTRY_DIR", str(root))
    pairs, _ = select_pairs(session, technical=True, candidate_codes=[candidate.code])
    assert {pair.purpose for pair in pairs} == {"comparison"}
    assert all(pair.application_id is None for pair in pairs)
    assert all(not item["is_source_position"] for item in cross_assessments(session, candidate.id)["items"])


def test_later_resolved_response_is_selected_instead_of_first_unresolved(session, setup, tmp_path, monkeypatch):
    candidate, first, _, _ = setup
    vacancy = session.scalar(select(Vacancy).join(Position).where(Position.code == "qa-manual"))
    second = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                     vacancy_id=vacancy.id)
    register(tmp_path, monkeypatch, session, second)
    pairs, _ = select_pairs(session, technical=True, candidate_codes=[candidate.code])
    primary = [pair for pair in pairs if pair.purpose == "primary"]
    assert [(pair.position_code, pair.application_id) for pair in primary] == [("hr-consultant", second.id)]
    assert second.id != first.id


def test_cross_payload_marks_resolved_role_and_only_response_vacancies(session, setup, tmp_path, monkeypatch):
    candidate, application, _, _ = setup
    register(tmp_path, monkeypatch, session, application)
    vacancy = session.scalar(select(Vacancy).join(Position).where(Position.code == "hr-consultant"))
    manual = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.MANUAL,
                                     vacancy_id=vacancy.id)
    payload = cross_assessments(session, candidate.id)
    items = {item["position_code"]: item for item in payload["items"]}
    assert items["hr-consultant"]["is_source_position"] is True
    assert items["python-dev"]["is_source_position"] is False
    assert any(row["application_id"] == str(manual.id) for row in payload["applications"])
    assert all(row["application_id"] is None for row in items["hr-consultant"]["vacancies"])


@pytest.mark.parametrize("skip_existing", [True, False])
def test_revoked_primary_is_skipped_before_cached_assessment_or_model(session, setup, tmp_path, monkeypatch, skip_existing):
    candidate, application, _, hr = setup
    register(tmp_path, monkeypatch, session, application)
    pairs, _ = select_pairs(session, technical=True, candidate_codes=[candidate.code])
    primary = next(pair for pair in pairs if pair.position_code == "hr-consultant")
    assess_candidate(session, candidate_id=candidate.id, profile_id=hr.id,
                     llm=FakeLLMClient(responder()), mode="technical", as_of=AS_OF)
    register(tmp_path, monkeypatch, session, application, state="needs_review", version="v2")
    report = run_cross_batch(factory(session), [primary], run_one=lambda *a, **kw: pytest.fail("revoked primary ran"),
                             llm_factory=lambda: FakeLLMClient(lambda *a: pytest.fail("model called")),
                             technical=True, as_of=AS_OF, skip_existing=skip_existing)
    assert report["counts"] == {"skipped_context": 1}
    assert report["results"][0]["reason"] == "awaiting_hr"
    audit = session.scalar(select(AuditLog).where(AuditLog.entity_type == "cross_pair_skipped"))
    assert audit.details["resolution"]["mapping"]["registry_version"] == "v2"
    assert audit.details["reason"] == "awaiting_hr"


@pytest.mark.parametrize("change, reason", [("archive", "no_approved_profile"), ("wrong_profile", "profile_changed")])
def test_primary_cache_cannot_bypass_approved_profile_selection(session, setup, tmp_path, monkeypatch, change, reason):
    candidate, application, python, hr = setup
    register(tmp_path, monkeypatch, session, application)
    pairs, _ = select_pairs(session, technical=True, candidate_codes=[candidate.code])
    primary = next(pair for pair in pairs if pair.position_code == "hr-consultant")
    if change == "wrong_profile":
        primary = replace(primary, profile_id=python.id)
    assess_candidate(session, candidate_id=candidate.id, profile_id=primary.profile_id,
                     llm=FakeLLMClient(responder()), mode="technical", as_of=AS_OF)
    if change == "archive":
        hr.status = RequirementStatus.ARCHIVED
        session.flush()
    report = run_cross_batch(factory(session), [primary], run_one=lambda *a, **kw: pytest.fail("invalid profile ran"),
                             llm_factory=lambda: FakeLLMClient(lambda *a: pytest.fail("model called")),
                             technical=True, as_of=AS_OF, skip_existing=True)
    assert report["counts"] == {"skipped_context": 1}
    assert report["results"][0]["reason"] == reason


def test_valid_current_primary_reuses_cache_without_calling_model(session, setup, tmp_path, monkeypatch):
    candidate, application, _, hr = setup
    register(tmp_path, monkeypatch, session, application)
    pairs, _ = select_pairs(session, technical=True, candidate_codes=[candidate.code])
    primary = next(pair for pair in pairs if pair.position_code == "hr-consultant")
    assessment_id = assess_candidate(session, candidate_id=candidate.id, profile_id=hr.id,
                                     llm=FakeLLMClient(responder()), mode="technical", as_of=AS_OF)
    report = run_cross_batch(factory(session), [primary], run_one=lambda *a, **kw: pytest.fail("cache not reused"),
                             llm_factory=lambda: FakeLLMClient(lambda *a: pytest.fail("model called")),
                             technical=True, as_of=AS_OF, skip_existing=True)
    assert report["counts"] == {"skipped_current": 1}
    assert report["results"][0]["assessment_id"] == str(assessment_id)


@pytest.mark.parametrize("skip_existing", [True, False])
@pytest.mark.parametrize("change, reason", [
    ("archive", "no_approved_profile"), ("replace", "profile_changed"),
    ("wrong_contour", "contour_mismatch"), ("profile_contour", "contour_mismatch"),
])
def test_comparison_rechecks_current_approved_profile_before_cache_or_model(
    session, setup, tmp_path, monkeypatch, skip_existing, change, reason,
):
    candidate, application, python, _ = setup
    register(tmp_path, monkeypatch, session, application)  # HR is primary; Python is explicit comparison.
    pairs, _ = select_pairs(session, technical=True, candidate_codes=[candidate.code])
    comparison = next(pair for pair in pairs if pair.position_code == "python-dev")
    assert comparison.purpose == "comparison"
    if change == "profile_contour":
        python = approve(session, create_fixture_profile(session, FIXTURE, synthetic=False))
        comparison = replace(comparison, profile_id=python.id)
    assess_candidate(session, candidate_id=candidate.id, profile_id=python.id,
                     llm=FakeLLMClient(responder()), mode="technical", as_of=AS_OF)
    if change == "archive":
        python.status = RequirementStatus.ARCHIVED
    elif change == "replace":
        approve(session, create_fixture_profile(session, FIXTURE))
    session.flush()
    report = run_cross_batch(factory(session), [comparison],
        run_one=lambda *a, **kw: pytest.fail("invalid comparison reached orchestration"),
        llm_factory=lambda: FakeLLMClient(lambda *a: pytest.fail("model called")),
        technical=change != "wrong_contour", as_of=AS_OF, skip_existing=skip_existing)
    assert report["counts"] == {"skipped_context": 1}
    assert report["results"][0]["reason"] == reason
    audit = session.scalar(select(AuditLog).where(AuditLog.entity_type == "cross_pair_skipped"))
    assert audit.details["reason"] == reason and audit.details["purpose"] == "comparison"
    assert audit.details["profile_id"] == str(python.id)
    if change in ("archive", "replace", "profile_contour"):
        displayed = cross_assessments(session, candidate.id)["items"]
        assert all(item["profile_id"] != str(python.id) for item in displayed)
