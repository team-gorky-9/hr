"""Проверка паритета валидатора requirement-draft/1.0 и формата событий."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from requirements_service.errors import ServiceError
from requirements_service.validation import quote_in_document, validate_draft_content

HR_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _sample_draft() -> dict:
    return {
        "schema_version": "requirement-draft/1.0",
        "position_code": "python-dev",
        "is_synthetic": True,
        "sources": [],
        "formal_requirements": [
            {
                "key": "demo.experience",
                "kind": "experience",
                "description": "24 months",
                "params": {
                    "schema_version": "0.1",
                    "scope": "total_commercial",
                    "minimum_defined": True,
                    "min_months": 24,
                },
                "is_mandatory": True,
                "verification": "resume",
                "origin": "team",
                "note": "synthetic rule",
            }
        ],
        "competencies": [
            {
                "key": "demo.testing",
                "code": "TEST",
                "name": "API tests",
                "origin": "team",
                "note": "synthetic indicator",
                "indicators": [
                    {
                        "key": "demo.api",
                        "text": "Писал API-тесты",
                        "verification": "resume",
                        "origin": "team",
                        "note": "synthetic indicator",
                    }
                ],
            }
        ],
    }


def test_py9001_fixture_passes_and_matches_legacy_validator():
    py9001_path = HR_ROOT / "fixtures" / "requirement_profiles" / "py-9001.draft.json"
    data = json.loads(py9001_path.read_text(encoding="utf-8"))

    validated = validate_draft_content(data)
    assert validated.position_code == "python-dev"
    assert validated.is_synthetic is True
    dumped = validated.model_dump(mode="json")
    assert dumped["formal_requirements"][0]["check_stage"] == "screening"
    assert dumped["competencies"][0]["indicators"][0]["check_stage"] == "screening"

    # Если рядом доступен корневой пакет hr/app с установленным окружением, сверяем точный JSON-паритет.
    legacy_script = Path(__file__).resolve().parent / "support" / "legacy_parity_check.py"
    root_python_win = HR_ROOT / ".venv" / "Scripts" / "python.exe"
    root_python_posix = HR_ROOT / ".venv" / "bin" / "python"
    legacy_python = root_python_win if root_python_win.is_file() else root_python_posix

    if legacy_python.is_file() and (HR_ROOT / "app" / "requirements" / "schemas.py").is_file():
        proc = subprocess.run(
            [str(legacy_python), "-X", "utf8", str(legacy_script), str(HR_ROOT), str(py9001_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        assert dumped == json.loads(proc.stdout)
    elif importlib.util.find_spec("pymorphy3") is not None and (HR_ROOT / "app" / "requirements" / "schemas.py").is_file():
        sys.path.insert(0, str(HR_ROOT))
        try:
            from app.requirements.schemas import validate_draft as legacy_validate_draft

            assert dumped == legacy_validate_draft(data).model_dump(mode="json")
        finally:
            if sys.path and sys.path[0] == str(HR_ROOT):
                sys.path.pop(0)


def test_rejects_extra_fields_and_does_not_leak_values():
    data = _sample_draft()
    data["version"] = 5
    with pytest.raises(ServiceError) as caught:
        validate_draft_content(data)
    assert caught.value.code == "VALIDATION_ERROR"

    data = _sample_draft()
    data["formal_requirements"][0]["params"]["SECRET_KEY"] = "PRIVATE_TEXT_123"
    with pytest.raises(ServiceError) as caught:
        validate_draft_content(data)
    assert "PRIVATE_TEXT_123" not in caught.value.message
    assert "SECRET_KEY" not in (caught.value.field or "")


@pytest.mark.parametrize(
    "mutator",
    [
        lambda d: d.update(is_synthetic="false"),
        lambda d: d["formal_requirements"][0].update(is_mandatory="false"),
        lambda d: d["formal_requirements"][0]["params"].update(min_months="24"),
        lambda d: d["formal_requirements"][0]["params"].update(min_months=True),
        lambda d: d["competencies"][0].update(target_level_min=90, target_level_max=80),
        lambda d: d["competencies"][0]["indicators"][0].update(typo=True),
        lambda d: d["competencies"].append(deepcopy(d["competencies"][0])),
    ],
)
def test_strict_scalar_and_structural_validation(mutator):
    data = _sample_draft()
    mutator(data)
    with pytest.raises(ServiceError) as caught:
        validate_draft_content(data)
    assert caught.value.status_code == 422


def test_same_as_and_requires_requirement_constraints():
    data = _sample_draft()
    data["formal_requirements"].append(
        {
            "key": "edu.field",
            "kind": "education_field",
            "description": "Профильное направление",
            "params": {
                "schema_version": "0.1",
                "requires_requirement": "missing.edu.level",
                "alternatives": [{"key": "deg", "degree_fields": ["Экономика"]}],
            },
            "is_mandatory": True,
            "verification": "documents",
            "origin": "team",
            "note": "rule check",
        }
    )
    with pytest.raises(ServiceError):
        validate_draft_content(data)

    data = _sample_draft()
    data["competencies"][0]["indicators"][0]["excluded_from_scoring"] = True
    data["competencies"][0]["indicators"][0]["same_as"] = "grp.1"
    with pytest.raises(ServiceError):
        validate_draft_content(data)


def test_quote_in_document_supports_nonadjacent_paragraphs():
    text = "Первый абзац.\nПромежуточный текст.\nВторой нужный абзац."
    assert quote_in_document("Первый абзац.\nВторой нужный абзац.", text) is True
    assert quote_in_document("Второй нужный абзац.\nПервый абзац.", text) is False
    assert quote_in_document("   \n  ", text) is False


def test_events_fixture_matches_requirements_approved_schema():
    events_path = SERVICE_ROOT / "fixtures" / "wave-1" / "events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))["events"]
    approved_evt = [e for e in events if e["event_type"] == "requirements.approved"][0]
    assert set(approved_evt.keys()) == {
        "event_id",
        "event_type",
        "schema_version",
        "producer",
        "organization_id",
        "aggregate_id",
        "aggregate_revision",
        "occurred_at",
        "correlation_id",
        "payload",
    }
    assert set(approved_evt["payload"].keys()) == {
        "profile_id",
        "position_code",
        "profile_version",
        "contour",
        "approved_by_actor_id",
        "approval_basis",
        "source_document_ids",
    }
