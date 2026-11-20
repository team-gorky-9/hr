"""Очистка ПДн и правила сопоставления — без базы. Тексты синтетические, формат как в архиве «Кадры»."""
from datetime import date
from pathlib import Path

import pytest

from app.db.enums import DocumentKind, FileFormat
from app.ingest.extract import ExtractError, extract_text
from app.ingest.package import InputFile, MappingConfig, Problem, resolve_route
from app.ingest.redact import MASK_CONTACT, MASK_NAME, MASK_PERSON, RedactionError, redact

BODY = (
    "\nОпыт работы\nОрганизация 1\nPython-разработчик\n"
    "- Разрабатывал REST API на FastAPI и PostgreSQL для сервиса заявок.\n"
    "- Написал API-тесты для сервиса заявок.\n"
)


def test_hh_docx_header_goes_to_pii():
    text = "ФИО 12\nЖенщина, 48 лет, родилась 7 июля 1978\n\nmailto:\nПроживает: Нижний Новгород\n" + BODY
    result = redact(text, FileFormat.HH_DOCX)

    assert result.pii.gender == "женский"
    assert result.pii.age == 48
    assert result.pii.birth_date == date(1978, 7, 7)
    assert MASK_PERSON in result.text and MASK_NAME in result.text
    for leaked in ("ФИО 12", "48 лет", "1978", "родилась", "mailto"):
        assert leaked not in result.text
    # Город не ПДн для очистки (контракт БД, п. 11.8).
    assert "Проживает: Нижний Новгород" in result.text


def test_gender_only_line_is_removed():
    result = redact("ФИО 3\nМужчина\n" + BODY, FileFormat.HH_DOCX)
    assert result.pii.gender == "мужской"
    assert "Мужчина" not in result.text


def test_contacts_signature_and_name_everywhere():
    text = (
        "Кандидат №7\nСопроводительное письмо\nЗдравствуйте! Меня зовут Пётр, это моё резюме.\n"
        "С уважением,\nПетров Пётр\nТелефон: 8 (999) 000-00-03\nПочта: petrov.test@example.com\n"
        "GitHub: https://github.com/petrov-test\n" + BODY + "Рекомендует Петрова, руководитель Петра."
    )
    result = redact(text, FileFormat.HH_TXT)

    for leaked in ("Пётр", "Петров", "Петра", "000-00-03", "petrov.test", "petrov-test", "Кандидат №7"):
        assert leaked not in result.text
    assert result.pii.phone == "8 (999) 000-00-03"
    assert result.pii.email == "petrov.test@example.com"
    assert "https://github.com/petrov-test" in result.pii.links
    assert "Написал API-тесты для сервиса заявок." in result.text


@pytest.mark.parametrize("contact", ["Telegram – @test_nick77.", "в тг @@test_nick77", "Телеграм@test_nick77"])
def test_nick_variants_from_archive(contact):
    result = redact(BODY + contact + "\n", FileFormat.HH_TXT)
    assert "test_nick77" not in result.text
    assert MASK_CONTACT in result.text


def test_decorators_and_annotations_are_not_nicks():
    text = BODY + "Применял параметризацию (@pytest.mark.parametrize), @app.get( и аннотацию @Override.\n"
    result = redact(text, FileFormat.HH_TXT)
    assert "@pytest.mark.parametrize" in result.text
    assert "@app.get(" in result.text
    assert "@Override" in result.text


def test_rare_name_after_strong_hint_without_dictionary():
    """«Зорвек» нет в словаре имён, но после «Меня зовут» это всегда имя."""
    result = redact("Обо мне\nЗдравствуйте! Меня зовут Зорвек. Я фронтенд-разработчик.\n" + BODY, FileFormat.HH_TXT)
    assert "Зорвек" not in result.text
    assert result.pii.full_name == "Зорвек"


def test_weak_hint_needs_dictionary():
    """После «Спасибо» бывает не имя: «Спасибо за внимание. Опыт…» — слово «Опыт» не маскируем."""
    result = redact("Спасибо за внимание.\nОпыт работы: 2 года\n" + BODY, FileFormat.HH_TXT)
    assert "Опыт работы: 2 года" in result.text
    assert result.pii.full_name is None


def test_employer_block_kept_but_recruiter_masked():
    text = BODY + "Комментарии\n🔴 Не сейчас: 2 из 5 обязательных требований\nОтказ: не подходит, 19.03.26 Автор: Сидорова Анна\n"
    result = redact(text, FileFormat.HH_TXT)
    assert "Сидорова" not in result.text and "Анна" not in result.text
    assert "Отказ: не подходит" in result.text  # решение 14: блок остаётся
    assert result.warnings == ["employer_block_present"]
    assert result.pii.full_name is None  # рекрутер — не кандидат


@pytest.mark.parametrize(
    "phone", ["📱 +7 (999) 000‑00‑06", "+7 999 000 00 06", "+ 7 999 000 00 06", "8-999-000-00-06"]
)
def test_phone_with_unicode_separators(phone):
    """В архиве встречаются неразрывный дефис U+2011 и неразрывные пробелы."""
    result = redact(BODY + phone + "\n", FileFormat.HH_TXT)
    assert "000" not in result.text.replace("Организация", "")
    assert result.pii.phone is not None


def test_fields_with_dash_and_phone_without_colon():
    """Случаи из аудита архива: «Дата рождения – …», «Пол – …», «Тел. + (…)», ник в github.io."""
    text = BODY + (
        "Дата рождения – 01.02.2003 (23 года) | Пол – Мужской\n"
        "Тел. + (999) 00 00 00 07 | Портфолио: https://test-nick88.github.io/portfolio/\n"
    )
    result = redact(text, FileFormat.HH_TXT)
    for leaked in ("01.02.2003", "23 года", "Мужской", "00 00 00 07", "test-nick88"):
        assert leaked not in result.text, leaked
    assert result.pii.extra["birth_date_raw"].startswith("01.02.2003")


def test_unlabeled_phone_goes_to_quarantine():
    """Телефон без +7 и подписи правила не опознают как телефон — проверка не пускает текст к модели."""
    with pytest.raises(RedactionError) as error:
        redact(BODY + "Звоните: 999 000 00 01\n", FileFormat.HH_TXT)
    assert error.value.code == "PII_RESIDUE"


def test_dates_and_links_with_digits_are_not_phones():
    text = BODY + "01.2019-05.2021 ЗАО «Организация»\nhttps://www.notion.so/test/1234567890abcdef\n"
    assert "01.2019-05.2021" in redact(text, FileFormat.HH_TXT).text


def test_nearly_empty_resume_goes_to_quarantine():
    with pytest.raises(RedactionError) as error:
        redact("Телефон: +7 999 000-00-04\n", FileFormat.HH_TXT)
    assert error.value.code == "EMPTY_AFTER_REDACTION"


# --- Извлечение текста ----------------------------------------------------------

def test_txt_cp1251_and_line_endings():
    assert extract_text("Опыт работы\r\nPython".encode("cp1251"), ".txt") == "Опыт работы\nPython"


def test_unknown_extension_and_empty_text():
    with pytest.raises(ExtractError) as unsupported:
        extract_text(b"x", ".rtf")
    assert unsupported.value.code == "UNSUPPORTED_FORMAT"
    with pytest.raises(ExtractError) as empty:
        extract_text(b"  \n", ".txt")
    assert empty.value.code == "EMPTY_TEXT"


def test_blank_pdf_needs_review():
    from scripts.make_stage0a_fixtures import build_blank_pdf

    with pytest.raises(ExtractError) as error:
        extract_text(build_blank_pdf(), ".pdf")
    assert error.value.code == "PDF_NEEDS_REVIEW"


def test_docx_table_cells():
    from scripts.make_stage0a_fixtures import build_docx

    text = extract_text(build_docx(["Опыт"], [["Образование", "Высшее, Юриспруденция, 2018"]]), ".docx")
    assert text == "Опыт\nОбразование\tВысшее, Юриспруденция, 2018"


# --- Сопоставление по правилам ----------------------------------------------------

def _route(path: str):
    return resolve_route(InputFile(path, b"", "text"), MappingConfig())


@pytest.mark.parametrize(
    ("path", "kind", "position", "code"),
    [
        ("Кадры/Python-разработчик/отклик 5.txt", DocumentKind.RESUME, "python-dev", "py-0005"),
        ("Кадры/Junior Python-разработчик/отклик 5.txt", DocumentKind.RESUME, "junior-python-dev", "jpy-0005"),
        ("Кадры/консультанта сектора подбора кадров/Резюме 12.docx", DocumentKind.RESUME, "hr-consultant", "hr-0012"),
        ("Кадры/Python-разработчик/Вакансия.txt", DocumentKind.VACANCY_POSTING, None, None),
        ("Кадры/Python-разработчик/Инженер ДИ.docx", DocumentKind.JOB_DESCRIPTION, None, None),
        ("Кадры/Положения/Кодекс этики.docx", DocumentKind.REGULATION, None, None),
        ("Кадры/матрица компетенций.docx", DocumentKind.COMPETENCY_MATRIX, None, None),
    ],
)
def test_rules(path, kind, position, code):
    route = _route(path)
    assert (route.document_kind, route.position_code, route.candidate_code) == (kind, position, code)


def test_resume_formats_follow_channel():
    assert _route("Кадры/Python-разработчик/отклик 5.txt").file_format == FileFormat.HH_TXT
    assert _route("Кадры/консультанта сектора подбора кадров/Резюме 1.docx").file_format == FileFormat.HH_DOCX


@pytest.mark.parametrize(
    ("path", "problem"),
    [("Кадры/Кейс.pdf", "UNKNOWN_DOCUMENT_KIND"), ("Кадры/Неизвестная папка/отклик 1.txt", "UNKNOWN_POSITION")],
)
def test_rules_do_not_guess(path, problem):
    with pytest.raises(Problem) as error:
        _route(path)
    assert error.value.code == problem


def test_kadry_mapping_covers_unrecognized_service_files():
    from app.ingest.package import load_mapping

    mapping = load_mapping(Path(__file__).resolve().parents[1] / "fixtures" / "kadry_mapping.json")
    route = resolve_route(InputFile("Кадры/Кейс.pdf", b"", "text"), mapping)
    assert route.document_kind == DocumentKind.OTHER


# --- Словарь папок: переименование папки без правки кода ----------------------------

def _mapping(tmp_path: Path, folders: dict[str, str]):
    from app.ingest.package import load_mapping

    path = tmp_path / "mapping.json"
    path.write_text(__import__("json").dumps({"folders": folders}, ensure_ascii=False), encoding="utf-8")
    return load_mapping(path)


def test_renamed_folder_works_through_dictionary(tmp_path):
    item = InputFile("Отклики 2026/Python Backend/отклик 5.txt", b"", "text")
    with pytest.raises(Problem) as error:
        resolve_route(item, MappingConfig())
    assert error.value.code == "UNKNOWN_POSITION"

    route = resolve_route(item, _mapping(tmp_path, {"Python Backend": "python-dev"}))
    assert (route.position_code, route.candidate_code) == ("python-dev", "py-0005")


def test_folder_names_compare_without_case_and_extra_spaces(tmp_path):
    mapping = _mapping(tmp_path, {"python  backend ": "python-dev"})
    assert resolve_route(InputFile("Python Backend/отклик 5.txt", b"", "text"), mapping).position_code == "python-dev"


def test_dictionary_overrides_seed_default(tmp_path):
    mapping = _mapping(tmp_path, {"Python-разработчик": "junior-python-dev"})
    route = resolve_route(InputFile("Python-разработчик/отклик 5.txt", b"", "text"), mapping)
    assert (route.position_code, route.candidate_code) == ("junior-python-dev", "jpy-0005")


# --- v2 (ingest-02): личные ссылки, которые пропускала v1 (найдены аудитом на архиве) ---

@pytest.mark.parametrize("link", [
    "https://drive.google.com/file/d/1AbCdEfGh/view?usp=sharing",
    "https://docs.google.com/document/d/1xYz/edit",
    "https://www.figma.com/file/AbC123/portfolio",
    "https://www.notion.so/testuser/Portfolio-8201f34ba78e",
    "https://test-user.notion.site/b9cc238c0e2a446f9f",
    "test-user.notion.site",
    "https://sites.google.com/view/portfoliotest",
    "disk.yandex.ru/d/AbCdEf",
    "https://test-user.netlify.app",
    "https://test-user-portfolio-123456.framer.app",
    "https://test-host.zapto.org:8443/auth",   # домашний сервер с портом
    "https://music.test-user.na4u.ru/#/",      # путь SPA «/#/»
])
def test_personal_links_are_masked(link):
    result = redact(f"Портфолио проектов\n{link}\n" + BODY, FileFormat.HH_TXT)
    assert link not in result.text
    assert "[ссылка скрыта]" in result.text
    assert link in result.pii.links


def test_link_glued_to_city_is_masked():
    """В выгрузке hh сайт идёт сразу после города: «Москваtest-site.example.com/…»."""
    result = redact("Организация 1\nМоскваpersonal.chickenkiller.com/\n" + BODY, FileFormat.HH_TXT)
    assert "chickenkiller" not in result.text
    assert "Москва" in result.text


@pytest.mark.parametrize("kept", [
    "Москваwww.sibur.ru",      # сайт работодателя без пути — не ПДн кандидата
    "rabota.sber.ru",
    "ASP.NET/Core",            # технологии, а не ссылки
    "Node.js/Express",
    "CI/CD",
])
def test_company_sites_and_technologies_are_kept(kept):
    assert kept in redact(f"Навыки\n{kept}\n" + BODY, FileFormat.HH_TXT).text


def test_git_label_with_skill_is_not_an_address():
    result = redact("Git: CI/CD, GitLab\n" + BODY, FileFormat.HH_TXT)
    assert "Git: CI/CD, GitLab" in result.text
    assert result.pii.links == []
