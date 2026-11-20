"""Аудит очистки ПДн (app/ingest/audit.py): находит остатки и не шумит на обычном тексте резюме."""
from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import CandidatePii, CandidateText
from app.ingest import load_mapping, read_package, run_import
from app.ingest.audit import audit_text, main, run_audit
from tests.test_ingest import FIXTURES

CLEAN = (
    "Опыт работы\nОрганизация 1\nМосква\nwww.sibur.ru\nPython-разработчик\n"
    "- Разрабатывал REST API на FastAPI (ASP.NET/Core в прошлом), настроил CI/CD.\n"
    "- Лицензия № Л035-01234-52/00176874 от 20.08.2021.\n"
    "01.09.2015 – 30.06.2019\nПроживает: Нижний Новгород\n[контакт скрыт] [ссылка скрыта]\n"
)


def test_clean_resume_has_no_findings():
    assert audit_text(CLEAN, None) == ([], [])


@pytest.mark.parametrize(("residue", "category"), [
    ("Почта: test.user@example.com", "email"),
    ("Тел.: +7 (999) 000‑00‑01", "phone"),         # неразрывный дефис U+2011
    ("звоните 8 999 000 00 01.", "phone"),
    ("https://github.com/test-user", "profile_link"),
    ("test-user.github.io", "profile_link"),
    ("https://drive.google.com/file/d/1AbC/view", "personal_url"),
    ("Москваdisk.yandex.ru/d/AbCd", "personal_url"),
    ("test-user.notion.site", "personal_url"),
    ("Женщина, 31 год", "person_header"),
    ("родилась 5 марта 1995", "birth_date"),
    ("Дата рождения: 05.03.1995", "birth_date"),
    ("ФИО 9001", "archive_id"),
    ("Кандидат №9001", "archive_id"),
])
def test_residue_is_found(residue, category):
    findings, _ = audit_text(CLEAN + residue + "\n", None)
    assert category in findings


def test_values_of_this_candidate_are_found_in_any_form():
    pii = CandidatePii(
        full_name="Иванов Тест", phone="+7 999 000-00-01", email="test.user@example.com",
        links=["https://github.com/test-user", "@testnick", "CI/CD"], birth_date=date(1995, 3, 5),
        extra={"archive_label": "ФИО 9001"},
    )
    text = CLEAN + "Связь: 8(999)0000001\nИванов\ntest-user\ntestnick\n"
    findings, _ = audit_text(text, pii)
    assert {"pii_phone", "pii_name", "pii_nick"} <= set(findings)
    assert "pii_link" not in findings  # «CI/CD» в ссылках — ошибка v1, а не адрес
    # Из «figma.com/design/…» ник не берётся: «Material Design» — не утечка.
    figma = CandidatePii(links=["https://www.figma.com/design/AbC/Projects"])
    assert audit_text(CLEAN + "Material Design\n", figma)[0] == []
    # «роман» с маленькой буквы — не имя «Роман».
    assert "pii_name" not in audit_text(CLEAN + "люблю роман\n", CandidatePii(full_name="Роман"))[0]


def test_code_decorator_goes_to_review_not_findings():
    findings, review = audit_text(CLEAN + "@pytest.fixture\n@Override\n", None)
    assert findings == [] and review == ["at_word"]


def test_imported_package_passes_audit(session):
    run_import(session, read_package(FIXTURES), load_mapping(FIXTURES / "mapping.json"), import_batch="test")
    report = run_audit(session)
    assert report.texts == 2
    assert report.findings == {}


def test_cli_exit_code_and_report_without_text(session, tmp_path, capsys):
    run_import(session, read_package(FIXTURES), load_mapping(FIXTURES / "mapping.json"), import_batch="test")
    text = session.scalars(select(CandidateText)).first()
    text.text += "\nПочта: leak.user@example.com\n"
    session.flush()

    class _Factory:
        def __call__(self):
            return _NoClose(session)

    exit_code = main(["--report", str(tmp_path / "audit.json")], session_factory=_Factory())
    out = capsys.readouterr()
    assert exit_code == 1
    assert "leak.user" not in out.out + out.err
    assert "email" in out.out


class _NoClose:
    """Сессия теста живёт в откатываемой транзакции: CLI не должен её закрывать."""

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False
