"""Acceptance of the standalone six-role package, using real source documents."""
import json
from pathlib import Path
import subprocess
import sys
import uuid
from copy import deepcopy

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "fixtures/requirement_profiles/all_six"


def test_standalone_package_verifies_all_six_roles_and_original_bytes():
    # Catches a missing role or a package that only works with an external archive.
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "scripts.verify_all_six_profiles"],
        cwd=ROOT, capture_output=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert {p["position_code"] for p in report["profiles"]} == {
        "hr-consultant", "python-dev", "junior-python-dev", "qa-manual",
        "frontend-dev", "junior-ux-ui",
    }
    assert report["sources_verified"] == 7
    assert all(p["status"] == "draft" and not p["is_synthetic"] for p in report["profiles"])


@pytest.mark.parametrize("defect", ["duplicate_key", "extra_param", "unknown_source", "unknown_requirement", "range", "half_range", "quote"])
def test_corrupted_package_is_rejected_before_loading(defect):
    from scripts.verify_all_six_profiles import verify_package
    package = json.loads((PACKAGE / "profiles.draft.json").read_text(encoding="utf-8"))
    manifest = json.loads((PACKAGE / "sources.json").read_text(encoding="utf-8"))
    hr = package["profiles"][0]
    if defect == "duplicate_key":
        hr["formal_requirements"].append(deepcopy(hr["formal_requirements"][0]))
    elif defect == "extra_param":
        hr["formal_requirements"][0]["params"]["invented"] = True
    elif defect == "unknown_source":
        hr["formal_requirements"][0]["source_refs"][0]["source_id"] = "absent"
    elif defect == "unknown_requirement":
        hr["formal_requirements"][1]["params"]["requires_requirement"] = "absent"
    elif defect == "range":
        hr["competencies"][0].update(target_level_min=101, target_level_max=99)
    elif defect == "half_range":
        hr["competencies"][0]["target_level_min"] = None
    else:
        hr["formal_requirements"][0]["source_refs"][0]["quote"] = "Такого условия в документе нет."
    with pytest.raises(ValueError):
        verify_package(package, manifest, PACKAGE / "originals")


def test_consultant_matrix_preserved_and_python_source_change_is_versioned():
    package = json.loads((PACKAGE / "profiles.draft.json").read_text(encoding="utf-8"))
    original = json.loads((PACKAGE.parent / "profiles.draft.json").read_text(encoding="utf-8"))
    assert package["profiles"][0] == original["profiles"][0]
    assert original["profiles"][1]["version"] == 5
    assert package["profiles"][1]["version"] == 6
    for profile in package["profiles"]:
        assert all(s["role"] != "vacancy_posting" for s in profile["sources"])
        for group in profile["competencies"]:
            assert all("posting" not in r["key"] for r in group["indicators"])


def test_courses_remain_manual_alternative_and_designer_di_is_applicable():
    package = json.loads((PACKAGE / "profiles.draft.json").read_text(encoding="utf-8"))
    profiles = {p["position_code"]: p for p in package["profiles"]}
    for code in ("frontend-dev", "junior-ux-ui"):
        rules = profiles[code]["formal_requirements"]
        education = next(r for r in rules if r["key"].endswith(".education"))
        assert (education["kind"], education["verification"], education["check_stage"]) == ("other", "documents", "interview")
        assert "ФРДО" in education["acceptance"]["met"]
        experience = next(r for r in rules if r["kind"] == "experience")
        assert experience["params"]["minimum_defined"] is False
    ux_leaves = [r for c in profiles["junior-ux-ui"]["competencies"] for r in c["indicators"]]
    assert any(r["key"] == "ux.di.P128" and r["check_stage"] == "interview" for r in ux_leaves)


def test_junior_and_qa_education_have_different_requirements_without_invented_tenure():
    package = json.loads((PACKAGE / "profiles.draft.json").read_text(encoding="utf-8"))
    profiles = {p["position_code"]: p for p in package["profiles"]}
    junior = profiles["junior-python-dev"]["formal_requirements"]
    qa = profiles["qa-manual"]["formal_requirements"]
    assert junior[0]["params"]["alternatives"][0]["field_group"] == "technical"
    assert "field_group" not in qa[0]["params"]["alternatives"][0]
    for rows in (junior, qa):
        assert rows[1]["params"]["minimum_defined"] is False
        assert "min_months" not in rows[1]["params"]
    leaves = [r for c in profiles["junior-python-dev"]["competencies"] for r in c["indicators"]]
    privacy = next(r for r in leaves if r["key"] == "jpy.di.P201")
    assert privacy["check_stage"] == "interview"
    assert privacy["source_refs"][0]["paragraph_ids"] == ["P201"]


def test_loading_command_defaults_to_rollback_and_reports_persisted_versions(session, monkeypatch, capsys):
    from contextlib import nullcontext
    from sqlalchemy import select, func
    from app.db import session as db_session
    from app.db.models import RequirementProfile, SourceDocument
    from scripts.load_all_six_profiles import main

    monkeypatch.setattr(db_session, "SessionLocal", lambda: nullcontext(session))
    assert main([]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["status"] == "dry_run" and preview["persisted"] is False
    assert session.scalar(select(func.count()).select_from(RequirementProfile)) == 0
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 0
    assert main(["--commit"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["persisted"] is True and result["sources_verified"] == 7
    assert len(result["profiles"]) == 6
    for row in result["profiles"]:
        saved = session.get(RequirementProfile, uuid.UUID(row["profile_id"]))
        assert saved.version == row["version"]
        assert row["position_code"] and row["sources"] and row["status"] == "draft"
    assert main(["--commit"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "version_conflict"
    assert session.scalar(select(func.count()).select_from(RequirementProfile)) == 6
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 7


def test_junior_response_uses_distinct_profiles_without_rejecting_application(session):
    from app import requirements as api
    from app.ai.fake import FakeLLMClient
    from app.assessment.service import assess_candidate
    from app.assessment.applicability import resolve_applicability
    from app.db import repository as repo
    from app.db.enums import ApplicationSource
    from app.db.models import Assessment
    from tests import factories as f

    package = json.loads((PACKAGE / "profiles.draft.json").read_text(encoding="utf-8"))
    manifest = json.loads((PACKAGE / "sources.json").read_text(encoding="utf-8"))
    loaded = api.load_package(session, package, manifest, PACKAGE / "originals", created_by="requirements02-test")
    profiles = dict(zip((p["position_code"] for p in package["profiles"]), loaded.profiles, strict=True))
    example = json.loads((PACKAGE / "example-junior-response.json").read_text(encoding="utf-8"))
    candidate = f.make_candidate(session, "jpy-9902", text=example["resume_text"], is_synthetic=True)
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                         vacancy_id=f.vacancy(session, "junior-python-dev").id)
    for code, expected in example["expected"].items():
        profile = profiles[code]
        prefix = "jpy" if code == "junior-python-dev" else "qa"
        def answer(role, schema, system, user):
            if schema == "FormalExtraction":
                result = {"alternatives": [{"alternative_key": f"{prefix}.education.alt1", "status": "confirmed",
                                             "quote": example["education_quote"]}]}
                if prefix == "jpy":
                    result["periods"] = [{"kind": "internship", "relevant": True, "quote": example["work_quote"]}]
                else:
                    result["no_experience_quote"] = example["qa_no_experience_quote"]
                return result
            return {}
        assessment_id = assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id,
                                         llm=FakeLLMClient(answer), mode="technical", as_of="2026-11")
        assessment = session.get(Assessment, assessment_id)
        checks = {r.requirement_id: r for r in assessment.formal_checks}
        for rule in profile.formal_requirements:
            assert checks[rule.id].result.value == expected[rule.key.split(".")[-1]]
            assert checks[rule.id].evidence
        assert assessment.profile_id == profile.id and profile.version == expected["version"]
    session.refresh(application)
    assert application.current_stage_code == "new"
    # Loading a consultant profile does not resolve the original mixed-folder mapping.
    assert profiles["hr-consultant"]
    assert resolve_applicability("hr-consultant", "Сметчик").status == "mismatch"


def test_six_profiles_roundtrip_and_version_history_in_isolated_database(session):
    from collections import Counter
    from sqlalchemy import select, func
    from app import requirements as api
    from app.requirements.package import convert_profile, validate_sources
    from app.db.enums import RequirementStatus, UserRole
    from app.db.models import RequirementProfile, User, SourceDocument

    package = json.loads((PACKAGE / "profiles.draft.json").read_text(encoding="utf-8"))
    manifest = json.loads((PACKAGE / "sources.json").read_text(encoding="utf-8"))
    sources = validate_sources(manifest, PACKAGE / "originals")
    loaded = api.load_package(session, package, manifest, PACKAGE / "originals", created_by="requirements02-test")
    documents = {key: session.scalar(select(SourceDocument.id).where(SourceDocument.sha256 == item[0]["sha256"]))
                 for key, item in sources.items()}
    with pytest.raises(api.RequirementError) as caught:
        api.load_package(session, package, manifest, PACKAGE / "originals", created_by="requirements02-test")
    assert caught.value.code == "version_conflict"
    assert session.scalar(select(func.count()).select_from(RequirementProfile)) == 6
    # Test actor and approvals exist only in the transaction rolled back by conftest.
    actor = User(login="requirements02-test", full_name="Тест жизненного цикла", role=UserRole.HR, is_active=True)
    session.add(actor)
    session.flush()
    for item, first in zip(package["profiles"], loaded.profiles, strict=True):
        position_id = first.position_id
        payload = convert_profile(item, sources, documents, Counter())
        assert first.status == RequirementStatus.DRAFT
        assert api.get_approved_profile(session, position_id) is None
        session.expire_all()
        restored = session.get(RequirementProfile, first.id)
        assert {r.key for r in restored.formal_requirements} == {r["key"] for r in item["formal_requirements"]}
        actual = {r.key: r for c in restored.competencies for r in c.indicators}
        for group in item["competencies"]:
            for leaf in group["indicators"]:
                assert actual[leaf["key"]].source_refs[0]["quote"] == leaf["source_refs"][0]["quote"].strip()
                assert actual[leaf["key"]].check_stage.value == leaf["check_stage"]
        api.approve_profile(session, first.id, approved_by_user_id=actor.id,
                                         approval_basis="Изолированный тест механизма; не утверждение содержания")
        second = api.load_profile_draft(session, payload, created_by="requirements02-test")
        assert second.version == first.version + 1
        assert api.get_approved_profile(session, position_id).id == first.id
        training_payload = payload.model_copy(update={"is_synthetic": True})
        training = api.load_profile_draft(session, training_payload, created_by="requirements02-test")
        api.approve_profile(session, training.id, approved_by_user_id=actor.id, approval_basis="Тест учебного контура")
        api.approve_profile(session, second.id, approved_by_user_id=actor.id, approval_basis="Тест смены версии")
        session.refresh(first)
        assert first.status == RequirementStatus.ARCHIVED
        assert first.competencies  # Historical content remains readable.
        assert api.get_approved_profile(session, position_id).id == second.id
        assert api.get_approved_profile(session, position_id, synthetic=True).id == training.id
