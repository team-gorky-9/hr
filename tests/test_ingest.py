"""Импорт контрольного пакета в PostgreSQL: приёмка задачи 0а на синтетике fixtures/stage_0a/.

Каждый тест работает в своей откатываемой транзакции (conftest.py), поэтому база в начале
теста содержит только справочники и должности.
"""
import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import ApplicationSource
from app.db.models import Application, Candidate, CandidatePii, CandidateText, SourceDocument, StageEvent
from app.ingest import ItemStatus, load_mapping, read_package, run_import
from app.ingest import pipeline
from app.ingest.__main__ import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "stage_0a"
PYTHON = "Python-разработчик"
CONSULTANT = "консультанта сектора подбора кадров"
CONTROL_PHRASE = "Написал API-тесты для сервиса заявок."
# Всё, что в синтетическом пакете выдумано как персональные данные.
SYNTHETIC_PII = [
    "Иванов", "Тестович", "Тест Иванов", "+7 999 000-00-01", "000-00-01", "test.ivanov@example.com",
    "github.com/test-ivanov", "test-ivanov", "Кандидат №9001", "ФИО 9001", "родилась", "5 марта 1995",
    "31 год", "+7 999 000-00-02", "petrova.test@example.com",
]


def counts(session: Session) -> dict[str, int]:
    tables = {
        "source_documents": SourceDocument, "candidates": Candidate, "candidate_pii": CandidatePii,
        "candidate_texts": CandidateText, "applications": Application, "stage_events": StageEvent,
    }
    return {name: session.scalar(select(func.count()).select_from(model)) for name, model in tables.items()}


def load(session: Session, root: Path = FIXTURES, mapping_path: Path | None = FIXTURES / "mapping.json"):
    return run_import(session, read_package(root), load_mapping(mapping_path), import_batch="test")


def by_path(report, path: str):
    return next(item for item in report.items if item.source_path == path)


@pytest.fixture
def package_copy(tmp_path: Path) -> Path:
    """Копия пакета, которую тест может дополнять файлами."""
    root = tmp_path / "package"
    shutil.copytree(FIXTURES, root)
    return root


def test_package_loads_and_report_matches_database(session):
    report = load(session)

    assert report.counts == {
        "total": 4, "imported": 2, "application_added": 0, "duplicate_skipped": 0,
        "excluded_non_resume": 1, "conflict": 0, "quarantined": 1, "error": 0,
    }
    # 2 отклика из папок + 2 внешних отклика из «Истории общения» hr-9001 (ingest-02).
    assert counts(session) == {
        "source_documents": 3, "candidates": 2, "candidate_pii": 2,
        "candidate_texts": 2, "applications": 4, "stage_events": 4,
    }
    py = by_path(report, f"{PYTHON}/py-9001.txt")
    assert py.candidate_code == "py-9001"
    application = session.get(Application, py.application_id)
    assert application.current_stage_code == "new"
    assert application.vacancy.position.code == "python-dev"
    assert by_path(report, f"{PYTHON}/py-9002.pdf").reason.startswith("PDF_NEEDS_REVIEW")
    assert by_path(report, f"{PYTHON}/Вакансия.txt").document_kind == "vacancy_posting"


def test_clean_text_has_no_pii_and_keeps_exact_quote(session):
    report = load(session)
    py = by_path(report, f"{PYTHON}/py-9001.txt")
    hr = by_path(report, f"{CONSULTANT}/hr-9001.docx")
    py_text = session.get(CandidateText, py.candidate_text_id).text
    hr_text = session.get(CandidateText, hr.candidate_text_id).text

    for value in SYNTHETIC_PII:
        assert value not in py_text and value not in hr_text, value
    # Цитата проверяется так же, как в save_assessment: text[start:end] == quote.
    start = py_text.index(CONTROL_PHRASE)
    assert py_text[start:start + len(CONTROL_PHRASE)] == CONTROL_PHRASE
    assert "Высшее, Юриспруденция, 2018" in hr_text

    pii = session.get(CandidatePii, py.candidate_id)
    assert (pii.full_name, pii.phone, pii.email) == ("Иванов Тест Тестович", "+7 999 000-00-01", "test.ivanov@example.com")
    assert pii.links == ["https://github.com/test-ivanov"]
    hr_pii = session.get(CandidatePii, hr.candidate_id)
    assert (hr_pii.gender, hr_pii.age, str(hr_pii.birth_date)) == ("женский", 31, "1995-03-05")


def test_report_and_stdout_have_no_pii(engine, capsys):
    # Отдельная сессия без тестовой транзакции: пробный прогон всё откатывает сам.
    # (Если бы рядом была открыта тестовая транзакция с теми же файлами, вставки ждали бы друг друга.)
    exit_code = main(
        ["--input", str(FIXTURES), "--mapping", str(FIXTURES / "mapping.json"), "--dry-run"],
        session_factory=lambda: Session(engine),
    )
    out, err = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(out)["counts"]["imported"] == 2
    for value in SYNTHETIC_PII + [CONTROL_PHRASE]:
        assert value not in out and value not in err, value


def test_repeat_and_renamed_copy_create_no_duplicates(session, package_copy):
    load(session)
    before = counts(session)

    shutil.copy(package_copy / PYTHON / "py-9001.txt", package_copy / PYTHON / "отклик 77.txt")
    report = load(session, package_copy, package_copy / "mapping.json")

    assert counts(session) == before
    assert report.counts["duplicate_skipped"] == 3  # py-9001, hr-9001 и переименованная копия
    renamed = by_path(report, f"{PYTHON}/отклик 77.txt")
    assert (renamed.status, renamed.candidate_code) == (ItemStatus.DUPLICATE_SKIPPED, "py-9001")
    assert by_path(report, f"{PYTHON}/Вакансия.txt").status == ItemStatus.EXCLUDED_NON_RESUME


def test_same_file_for_another_vacancy_adds_application(session, package_copy):
    load(session)
    (package_copy / "QA Engineer Manual").mkdir()
    shutil.copy(package_copy / PYTHON / "py-9001.txt", package_copy / "QA Engineer Manual" / "отклик 5.txt")

    report = load(session, package_copy, package_copy / "mapping.json")

    added = by_path(report, "QA Engineer Manual/отклик 5.txt")
    assert (added.status, added.candidate_code) == (ItemStatus.APPLICATION_ADDED, "py-9001")
    assert counts(session)["candidates"] == 2
    assert counts(session)["applications"] == 5  # 2 + 2 внешних из истории hr-9001 + новый


def test_other_file_with_taken_code_is_conflict(session, package_copy):
    load(session)
    before = counts(session)
    (package_copy / PYTHON / "py-9001.txt").write_text("Другое резюме.\n" * 10 + CONTROL_PHRASE, encoding="utf-8")

    report = load(session, package_copy, package_copy / "mapping.json")

    conflict = by_path(report, f"{PYTHON}/py-9001.txt")
    assert (conflict.status, conflict.candidate_code) == (ItemStatus.CONFLICT, "py-9001")
    assert conflict.reason.startswith("CODE_CONFLICT")
    assert counts(session) == before


def test_synthetic_files_are_imported_into_training_contour(session):
    """py-9001 и hr-9001 помечены в mapping как учебные: в рабочие списки они не попадут."""
    report = load(session)
    for path in (f"{PYTHON}/py-9001.txt", f"{CONSULTANT}/hr-9001.docx"):
        item = by_path(report, path)
        assert item.is_synthetic is True
        assert session.get(Candidate, item.candidate_id).is_synthetic


def test_unmarked_file_is_real(session, tmp_path):
    root = tmp_path / "package"
    (root / PYTHON).mkdir(parents=True)
    shutil.copy(FIXTURES / PYTHON / "py-9001.txt", root / PYTHON / "отклик 5.txt")
    report = load(session, root, mapping_path=None)
    item = by_path(report, f"{PYTHON}/отклик 5.txt")
    assert (item.status, item.is_synthetic) == (ItemStatus.IMPORTED, False)


def test_explicit_contour_change_is_conflict(session, package_copy):
    """Учебный файл, повторно размеченный как реальный, не переводится в рабочий контур."""
    load(session)
    mapping = json.loads((package_copy / "mapping.json").read_text(encoding="utf-8"))
    mapping["entries"][0]["synthetic"] = False
    (package_copy / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    before = counts(session)

    report = load(session, package_copy, package_copy / "mapping.json")

    item = by_path(report, f"{PYTHON}/py-9001.txt")
    assert (item.status, item.candidate_code) == (ItemStatus.CONFLICT, "py-9001")
    assert item.reason.startswith("CONTOUR_CONFLICT")
    assert counts(session) == before


def test_different_files_with_same_text_are_both_imported_with_warning(session, tmp_path):
    text = (FIXTURES / PYTHON / "py-9001.txt").read_text(encoding="utf-8")
    (tmp_path / PYTHON).mkdir()
    (tmp_path / PYTHON / "отклик 9101.txt").write_bytes(text.encode("utf-8"))
    (tmp_path / PYTHON / "отклик 9102.txt").write_bytes(text.encode("cp1251"))  # другие байты, тот же текст

    report = load(session, tmp_path, None)

    first, second = by_path(report, f"{PYTHON}/отклик 9101.txt"), by_path(report, f"{PYTHON}/отклик 9102.txt")
    assert (first.status, first.candidate_code, first.warnings) == (ItemStatus.IMPORTED, "py-9101", [])
    assert (second.status, second.candidate_code) == (ItemStatus.IMPORTED, "py-9102")
    assert second.warnings == ["duplicate_text_warning"]
    assert counts(session)["candidates"] == 2


def test_failure_in_the_middle_leaves_no_partial_candidate(session, monkeypatch):
    def broken_create_application(*args, **kwargs):
        raise RuntimeError("сбой после записи кандидата")

    monkeypatch.setattr(pipeline.repo, "create_application", broken_create_application)
    report = load(session)

    assert report.counts["error"] == 2
    assert by_path(report, f"{PYTHON}/py-9001.txt").reason == "INTERNAL_ERROR: RuntimeError"
    # Документ и кандидат были записаны до сбоя, но точка сохранения откатила их.
    assert counts(session) == {
        "source_documents": 1, "candidates": 0, "candidate_pii": 0,
        "candidate_texts": 0, "applications": 0, "stage_events": 0,
    }


def test_unknown_folder_and_pii_residue_are_quarantined(session, tmp_path):
    (tmp_path / "Неизвестная папка").mkdir()
    (tmp_path / "Неизвестная папка" / "отклик 1.txt").write_text("Опыт работы\n" * 10, encoding="utf-8")
    (tmp_path / PYTHON).mkdir()
    residue = (FIXTURES / PYTHON / "py-9001.txt").read_text(encoding="utf-8") + "Звоните: 999 000 00 05\n"
    (tmp_path / PYTHON / "отклик 9201.txt").write_text(residue, encoding="utf-8")

    report = load(session, tmp_path, None)

    assert by_path(report, "Неизвестная папка/отклик 1.txt").reason.startswith("UNKNOWN_POSITION")
    assert by_path(report, f"{PYTHON}/отклик 9201.txt").reason.startswith("PII_RESIDUE")
    assert counts(session)["source_documents"] == 0


def test_parser_export_gives_same_result(session, tmp_path):
    """Режим выгрузки парсера: corpus.jsonl + originals/ (формат tools/hr_archive_parser)."""
    import hashlib

    from app.ingest.extract import extract_text

    lines = []
    for path in sorted(FIXTURES.rglob("*")):
        if not path.is_file() or path.name == "mapping.json":
            continue
        relative = path.relative_to(FIXTURES).as_posix()
        target = tmp_path / "originals" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        if path.suffix == ".pdf":
            continue  # парсер не выдаёт текст скана, он попадает в summary.json/errors
        lines.append(json.dumps({
            "source_path": relative, "original_file": f"originals/{relative}", "format": path.suffix,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "text": extract_text(path.read_bytes(), path.suffix),
        }, ensure_ascii=False))
    (tmp_path / "corpus.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps(
        {"errors": [{"path": f"{PYTHON}/py-9002.pdf", "error": "PDF_NEEDS_REVIEW: скан"}]}, ensure_ascii=False
    ), encoding="utf-8")

    report = load(session, tmp_path)

    assert report.counts["imported"] == 2 and report.counts["excluded_non_resume"] == 1
    assert by_path(report, f"{PYTHON}/py-9002.pdf").reason.startswith("PDF_NEEDS_REVIEW")


# --- «История общения с кандидатом» (ingest-02) ---

def history_rows(session: Session, code: str) -> list[tuple[str, object]]:
    rows = session.execute(
        select(Application.external_position_title, Application.applied_at)
        .join(Candidate)
        .where(Candidate.code == code, Application.source == ApplicationSource.HISTORY)
        .order_by(Application.applied_at)
    )
    return [tuple(row) for row in rows]


def test_history_gives_response_date_posting_and_external_applications(session):
    report = load(session)
    hr = by_path(report, f"{CONSULTANT}/hr-9001.docx")

    response = session.get(Application, hr.application_id)
    assert response.source == ApplicationSource.RESPONSE
    assert response.posting_title == "Консультант отдела кадровой работы"
    assert response.applied_at == date(2026, 8, 6)
    # Запись, совпавшая с подвалом, — сам отклик: внешним откликом она не становится.
    assert history_rows(session, "hr-9001") == [
        ("Главный специалист отдела прогнозирования", date(2026, 5, 2)),
        ("Консультант отдела муниципальной службы", date(2026, 7, 31)),
    ]
    external = session.scalars(
        select(Application).where(Application.source == ApplicationSource.HISTORY)
    ).all()
    assert all(app.vacancy_id is None and app.posting_title is None for app in external)
    assert (hr.posting_found, hr.history_added, hr.history_existing) == (True, 2, 0)
    assert report.history == {"responses_with_posting": 1, "applications_added": 2, "applications_existing": 0}
    # У TXT нет ни истории, ни подвала.
    py = by_path(report, f"{PYTHON}/py-9001.txt")
    assert (py.posting_found, py.history_added) == (None, 0)
    assert session.get(Application, py.application_id).applied_at is None


def test_repeat_run_does_not_duplicate_history(session):
    load(session)
    report = load(session)

    hr = by_path(report, f"{CONSULTANT}/hr-9001.docx")
    assert hr.status == ItemStatus.DUPLICATE_SKIPPED
    assert (hr.history_added, hr.history_existing) == (0, 2)
    assert len(history_rows(session, "hr-9001")) == 2


def test_history_is_backfilled_for_files_loaded_before_ingest_02(session):
    """База, загруженная импортом 0а: файл уже есть, истории и даты нет. Повтор их дописывает."""
    report = load(session)
    hr = by_path(report, f"{CONSULTANT}/hr-9001.docx")
    session.execute(delete(Application).where(Application.source == ApplicationSource.HISTORY))
    response = session.get(Application, hr.application_id)
    response.posting_title = None
    response.applied_at = None
    session.commit()

    again = by_path(load(session), f"{CONSULTANT}/hr-9001.docx")

    assert again.status == ItemStatus.DUPLICATE_SKIPPED
    assert again.history_added == 2
    session.refresh(response)
    assert (response.posting_title, response.applied_at) == ("Консультант отдела кадровой работы", date(2026, 8, 6))
    assert len(history_rows(session, "hr-9001")) == 2


def test_manual_response_date_is_not_overwritten(session):
    report = load(session)
    response = session.get(Application, by_path(report, f"{CONSULTANT}/hr-9001.docx").application_id)
    response.applied_at = date(2026, 8, 7)
    session.commit()

    load(session)
    session.refresh(response)
    assert response.applied_at == date(2026, 8, 7)


def test_database_rejects_duplicate_history_application(session):
    report = load(session)
    candidate_id = by_path(report, f"{CONSULTANT}/hr-9001.docx").candidate_id
    for applied_at in (date(2026, 7, 31), None):
        if applied_at is None:  # без даты: первая запись проходит, повтор — нет (NULLS NOT DISTINCT)
            repo.create_application(session, candidate_id=candidate_id, source=ApplicationSource.HISTORY,
                                    external_position_title="Консультант отдела муниципальной службы")
            session.flush()
        savepoint = session.begin_nested()
        with pytest.raises(IntegrityError):
            repo.create_application(session, candidate_id=candidate_id, source=ApplicationSource.HISTORY,
                                    external_position_title="Консультант отдела муниципальной службы",
                                    applied_at=applied_at)
            session.flush()
        savepoint.rollback()


def test_conflicting_file_gets_no_history(session, package_copy):
    load(session)
    before = history_rows(session, "hr-9001")
    docx = package_copy / CONSULTANT / "hr-9001.docx"
    docx.write_bytes(docx.read_bytes() + b"x")  # другие байты, тот же код кандидата

    report = load(session, package_copy, package_copy / "mapping.json")

    assert by_path(report, f"{CONSULTANT}/hr-9001.docx").status in (ItemStatus.CONFLICT, ItemStatus.QUARANTINED)
    assert history_rows(session, "hr-9001") == before


# --- Перечистка уже загруженных текстов (--reredact, план ingest-02 Р5) ---

def test_reredact_replaces_outdated_text_once(session):
    report = load(session)
    py = by_path(report, f"{PYTHON}/py-9001.txt")
    candidate_id = py.candidate_id
    # Текст, очищенный старыми правилами: личная ссылка осталась.
    repo.add_candidate_text(session, candidate_id, text="Портфолио https://drive.google.com/file/d/1AbC/view",
                            redaction_method="ingest-rules v1")
    session.commit()

    again = run_import(session, read_package(FIXTURES), load_mapping(FIXTURES / "mapping.json"),
                       import_batch="test", reredact=True)

    item = by_path(again, f"{PYTHON}/py-9001.txt")
    assert (item.status, item.reredact) == (ItemStatus.DUPLICATE_SKIPPED, "updated")
    current = repo.get_current_text(session, candidate_id)
    assert current.id == item.candidate_text_id and current.version == 3
    assert "drive.google" not in current.text and CONTROL_PHRASE in current.text
    assert again.reredact["updated"] == 1

    third = run_import(session, read_package(FIXTURES), load_mapping(FIXTURES / "mapping.json"),
                       import_batch="test", reredact=True)
    assert by_path(third, f"{PYTHON}/py-9001.txt").reredact == "unchanged"
    assert repo.get_current_text(session, candidate_id).version == 3


def test_without_reredact_text_is_not_touched(session):
    report = load(session)
    before = counts(session)
    assert by_path(load(session), f"{PYTHON}/py-9001.txt").reredact is None
    assert counts(session)["candidate_texts"] == before["candidate_texts"]
