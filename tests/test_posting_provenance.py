"""Package identity and per-application import evidence, independent of candidate deduplication."""
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError

from app.ingest import ItemStatus, load_mapping, read_package, run_import
from app.ingest.package import InputFile, Mapping, MappingConfig, Problem


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "stage_0a"


def test_fingerprint_ignores_input_order_and_path_encoding():
    from app.postings.provenance import dataset_fingerprint

    original = [InputFile("café/a.txt", b"one", "one"), InputFile("b.txt", b"two", "two")]
    equivalent = [original[1], InputFile("cafe\u0301\\a.txt", b"one", "different extracted text")]
    assert dataset_fingerprint(original) == dataset_fingerprint(equivalent)
    assert len(dataset_fingerprint(original)) == 64


def test_fingerprint_changes_for_content_path_and_missing_or_unsupported_records():
    from app.postings.provenance import dataset_fingerprint

    original = [InputFile("a.txt", b"one", "one")]
    baseline = dataset_fingerprint(original)
    variants = [
        [InputFile("a.txt", b"two", "one")],
        [InputFile("other/a.txt", b"one", "one")],
        original + [InputFile("missing.docx", None, None, Problem("MISSING", "missing"))],
        original + [InputFile("unsupported.bin", b"bytes", None, Problem("UNSUPPORTED", "unsupported"))],
    ]
    assert all(dataset_fingerprint(files) != baseline for files in variants)


def test_mapping_accepts_dataset_identity_but_never_a_declared_fingerprint(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text('{"dataset_id":"package-v1"}', encoding="utf-8")
    assert load_mapping(path).dataset_id == "package-v1"
    for bad in ("", "   "):
        with pytest.raises(ValidationError):
            Mapping(dataset_id=bad)
        with pytest.raises(ValueError):
            MappingConfig(dataset_id=bad)
    with pytest.raises(ValidationError):
        Mapping(dataset_id="package-v1", dataset_sha256="a" * 64)


def _package(dataset_id="package-v1"):
    mapping = load_mapping(FIXTURES / "mapping.json")
    mapping.dataset_id = dataset_id
    return read_package(FIXTURES), mapping


def _sources(session):
    from app.db.models import ApplicationPostingSource

    return list(session.scalars(select(ApplicationPostingSource)))


def test_duplicate_import_is_idempotent_and_preserves_second_dataset_context(session):
    files, mapping = _package()
    first = run_import(session, files, mapping, import_batch="first")
    assert first.counts["imported"] == 2
    rows = _sources(session)
    assert len(rows) == 2  # no source evidence for extracted history or excluded documents
    original_ids = {row.id for row in rows}
    assert {row.dataset_id for row in rows} == {"package-v1"}
    assert {row.channel for row in rows} == {"hh_ru"}
    assert {row.source_folder for row in rows} == {"Python-разработчик", "консультанта сектора подбора кадров"}

    repeated = run_import(session, files, mapping, import_batch="repeat")
    assert repeated.counts["duplicate_skipped"] == 2
    assert {row.id for row in _sources(session)} == original_ids

    mapping.dataset_id = "another-delivery"
    run_import(session, files, mapping, import_batch="second-context")
    rows = _sources(session)
    assert len(rows) == 4
    assert original_ids <= {row.id for row in rows}
    assert {row.dataset_id for row in rows} == {"package-v1", "another-delivery"}
    assert len({row.dataset_sha256 for row in rows}) == 1


def test_same_bytes_in_other_folder_keep_each_applications_actual_source(session):
    files, mapping = _package()
    original = next(item for item in files if item.source_path.endswith("py-9001.txt"))
    copied = replace(original, source_path="QA Engineer Manual/отклик 5.txt")
    report = run_import(session, [original, copied], mapping, import_batch="two-folders")
    assert [item.status for item in report.items] == [ItemStatus.IMPORTED, ItemStatus.APPLICATION_ADDED]
    assert len({item.candidate_id for item in report.items}) == 1
    assert len({item.application_id for item in report.items}) == 2
    rows = _sources(session)
    assert {row.application_id: row.source_path for row in rows} == {
        report.items[0].application_id: "Python-разработчик/py-9001.txt",
        report.items[1].application_id: "QA Engineer Manual/отклик 5.txt",
    }
    assert len({row.source_sha256 for row in rows}) == 1


def test_old_import_has_no_inferred_context_until_reimport_with_dataset(session):
    files, mapping = _package(dataset_id=None)
    run_import(session, files, mapping, import_batch="legacy")
    assert _sources(session) == []
    mapping.dataset_id = "verified-delivery"
    run_import(session, files, mapping, import_batch="verified")
    assert len(_sources(session)) == 2


def test_changed_package_snapshot_retains_previous_context_even_for_unchanged_resume(session):
    files, mapping = _package()
    run_import(session, files, mapping, import_batch="before")
    old_ids = {row.id for row in _sources(session)}
    files.append(InputFile("missing.docx", None, None, Problem("MISSING", "missing")))
    run_import(session, files, mapping, import_batch="after")
    rows = _sources(session)
    assert len(rows) == 4
    assert old_ids <= {row.id for row in rows}
    assert len({row.dataset_sha256 for row in rows}) == 2


def test_application_deletion_cascades_source_evidence(session):
    from app.db.models import Application

    files, mapping = _package()
    run_import(session, files, mapping, import_batch="delete")
    removed_id = _sources(session)[0].application_id
    session.execute(delete(Application).where(Application.id == removed_id))
    assert len(_sources(session)) == 1
    assert all(row.application_id != removed_id for row in _sources(session))


def test_source_helper_rejects_history_application_and_missing_original(session):
    from app.db.enums import ApplicationSource
    from app.db.models import Application
    from app.postings.provenance import record_source

    files, mapping = _package()
    run_import(session, files, mapping, import_batch="guard")
    history_id = session.scalar(select(Application.id).where(Application.source == ApplicationSource.HISTORY))
    response_id = _sources(session)[0].application_id
    with pytest.raises(ValueError, match="response application"):
        record_source(session, history_id, "package-v1", "a" * 64, files[0], "hh_ru")
    with pytest.raises(ValueError, match="original file bytes"):
        record_source(session, response_id, "package-v1", "a" * 64, InputFile("lost.txt", None, None), "hh_ru")
    assert len(_sources(session)) == 2


def test_source_evidence_cannot_be_overwritten(session):
    from app.db.models import ApplicationPostingSource

    files, mapping = _package()
    run_import(session, files, mapping, import_batch="immutable")
    row = _sources(session)[0]
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(update(ApplicationPostingSource).where(ApplicationPostingSource.id == row.id).values(dataset_id="changed"))
    session.expire_all()
    assert session.get(ApplicationPostingSource, row.id).dataset_id == "package-v1"


def test_provenance_migration_can_downgrade_and_reapply(engine, database_url):
    from alembic import command
    from tests.conftest import alembic_config

    config = alembic_config(database_url)
    try:
        command.downgrade(config, "0006")
        assert "application_posting_sources" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(config, "head")
    assert "application_posting_sources" in inspect(engine).get_table_names()
