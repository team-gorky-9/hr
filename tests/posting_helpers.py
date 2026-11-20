"""Explicit test data only: never a runtime fallback for missing provenance.

Callers choose the original role and a temporary registry directory. Every fixture
gets real DB provenance and an independently versioned decision in that directory.
"""
import os
from pathlib import Path

import pytest

from app.db.models import Candidate
from app.ingest.package import InputFile
from app.postings.provenance import dataset_fingerprint, record_source
from app.postings.registry import PostingRule, Registry, RegistryContext, RegistryStore


@pytest.fixture
def posting_registry(tmp_path, monkeypatch):
    """An empty private store; applications require explicit confirm_response calls."""
    root = tmp_path / "test-posting-registry"
    (root / "versions").mkdir(parents=True)
    empty = Registry(schema_version="posting-register/1.0", version="test-v0", rules=())
    (root / "versions" / "test-v0.json").write_text(empty.model_dump_json(), encoding="utf-8")
    (root / "current.json").write_text('{"version":"test-v0"}', encoding="utf-8")
    monkeypatch.setenv("POSTING_REGISTRY_DIR", str(root))
    return root


def confirm_response(session, application, position_code, *, registry_dir=None):
    root_value = registry_dir or os.environ.get("POSTING_REGISTRY_DIR")
    if not root_value:
        raise ValueError("test must explicitly select a temporary posting registry")
    root = Path(root_value)
    candidate = session.get(Candidate, application.candidate_id)
    item = InputFile(f"test-postings/{application.id}.txt", f"test-response:{application.id}".encode(), None)
    fingerprint = dataset_fingerprint([item])
    record_source(session, application.id, "explicit-test-fixture", fingerprint, item, "hh_ru")
    rule = PostingRule(
        id=f"response-{application.id}",
        context=RegistryContext(dataset_id="explicit-test-fixture", dataset_sha256=fingerprint,
            channel="hh_ru", source_folder="test-postings", is_synthetic=candidate.is_synthetic),
        match_kind="posting_title" if (application.posting_title or "").strip() else "folder",
        posting_title=application.posting_title,
        decision_state="confirmed", position_code=position_code,
        decision_author="Explicit test fixture", decision_date="2026-11-20",
        decision_basis="Role declared by this test; not a working HR confirmation",
        evidence_refs=(f"fixture://response/{application.id}",),
    )
    previous = RegistryStore(root).load() if (root / "current.json").exists() else None
    rules = [existing for existing in previous.rules if existing.id != rule.id] if previous else []
    version = f"test-v{len(list((root / 'versions').glob('*.json'))) + 1}"
    registry = Registry(schema_version="posting-register/1.0", version=version, rules=(*rules, rule))
    (root / "versions").mkdir(parents=True, exist_ok=True)
    (root / "versions" / f"{version}.json").write_text(registry.model_dump_json(), encoding="utf-8")
    (root / "current.json").write_text('{"version":"' + version + '"}', encoding="utf-8")
    session.flush()
    return registry
