"""Собрать синтетический контрольный пакет этапа 0а: fixtures/stage_0a/.

Все люди, контакты и организации вымышлены. Формат повторяет настоящие выгрузки hh.ru
из архива «Кадры»: TXT IT-вакансии и DOCX консультанта со строкой «Женщина, N лет, родилась …».
Готовые файлы лежат в Git; скрипт нужен, чтобы их пересобрать и увидеть, что внутри DOCX и PDF.

Запуск (из корня hr):
    uv run python -m scripts.make_stage0a_fixtures
"""
import io
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "stage_0a"
PYTHON_FOLDER = "Python-разработчик"
CONSULTANT_FOLDER = "консультанта сектора подбора кадров"

CONTROL_PHRASE = "Написал API-тесты для сервиса заявок."

PY_9001 = f"""Кандидат №9001
Резюме: Python-разработчик (FastAPI, PostgreSQL)

Сопроводительное письмо
Здравствуйте! Меня зовут Тест Иванов, откликаюсь на вакансию Python-разработчика.
Буду рад обсудить задачи команды.
С уважением,
Иванов Тест Тестович
Телефон: +7 999 000-00-01
Email: test.ivanov@example.com
GitHub: https://github.com/test-ivanov

Опыт работы
Опыт работы: 2 года 10 месяцев
Январь 2023 -
настоящее время
2 года 10 мес
Организация 1
Python-разработчик
- Разрабатывал REST API на FastAPI и PostgreSQL.
- {CONTROL_PHRASE}
- Настраивал сборку в GitLab CI.

Образование
Высшее образование (Бакалавр)
2022
Нижегородский государственный технический университет
Информатика и вычислительная техника

Навыки
Python
FastAPI
PostgreSQL
Pytest
Git

Гражданство:
Россия
"""

VACANCY = """Python-разработчик
Требования: Python 3, FastAPI, PostgreSQL, автотесты.
Условия: полная занятость, офис в Нижнем Новгороде.
"""

# Абзацы DOCX консультанта. Строка «Образование» — таблица, как в выгрузке hh.ru.
HR_9001_PARAGRAPHS = [
    "ФИО 9001",
    "Женщина, 31 год, родилась 5 марта 1995",
    "mailto:",
    "Проживает: Нижний Новгород",
    "Гражданство: Россия, есть разрешение на работу: Россия",
    "Не готова к переезду, готова к командировкам",
    "Желаемая должность и зарплата",
    "Специалист по кадрам",
    "Тип занятости: полная занятость",
    "Опыт работы —5 лет 2 месяца",
    "Январь 2021 — настоящее время",
    "Организация 1",
    "Специалист по кадрам",
    "- Подбор персонала, проведение собеседований",
    "- Ведение кадрового делопроизводства",
    "Телефон: +7 999 000-00-02",
    "Эл. почта: petrova.test@example.com",
    # «История общения» и подвал — как в выгрузке hh (задача ingest-02). Первая запись совпадает
    # с подвалом: это сам отклик, из неё берётся только дата. Две другие — отклики на другие должности.
    "История общения с кандидатом",
    "Откликнулась	Консультант отдела кадровой работы",
    "6 августа 2026",
    "",
    "Консультант отдела муниципальной службы",
    "31 июля 2026",
    "",
    "Главный специалист отдела прогнозирования",
    "2 мая 2026",
    "",
    "ФИО 9001  •  Резюме обновлено 16 августа 2026 в 11:58",
    "Резюме обновлено 16 августа 2026 в 11:58",
    "Отклик на вакансию: «Консультант отдела кадровой работы»",
    "6 августа 2026",
]
HR_9001_TABLE = [["Образование", "Высшее, Юриспруденция, 2018"]]

FIXED_DATE = (2026, 11, 19, 0, 0, 0)  # одинаковые байты при пересборке


def _zip_member(archive: zipfile.ZipFile, name: str, data: str) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data)


def build_docx(paragraphs: list[str], table: list[list[str]]) -> bytes:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    def para(text: str) -> str:
        # Табуляция — отдельным элементом <w:tab/>, как пишет Word («Откликнулся<TAB>должность»).
        runs = "<w:tab/>".join(f"<w:t xml:space=\"preserve\">{escape(part)}</w:t>" for part in text.split("	"))
        return f"<w:p><w:r>{runs}</w:r></w:p>"
    rows = "".join(
        "<w:tr>" + "".join(f"<w:tc>{para(cell)}</w:tc>" for cell in row) + "</w:tr>" for row in table
    )
    body = "".join(para(p) for p in paragraphs) + f"<w:tbl>{rows}</w:tbl>"
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {w}><w:body>{body}</w:body></w:document>'
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        _zip_member(archive, "[Content_Types].xml", content_types)
        _zip_member(archive, "_rels/.rels", rels)
        _zip_member(archive, "word/document.xml", document)
    return buffer.getvalue()


def build_blank_pdf() -> bytes:
    """PDF из одной пустой страницы — так выглядит скан без текстового слоя."""
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


MAPPING = {
    # Словарь «папка → должность». Переименовали папку — поправьте ключ здесь, код менять не нужно.
    "folders": {PYTHON_FOLDER: "python-dev", CONSULTANT_FOLDER: "hr-consultant"},
    "entries": [
        {
            "source_path": f"{PYTHON_FOLDER}/py-9001.txt",
            "candidate_code": "py-9001",
            "position_code": "python-dev",
            "channel": "hh_ru",
            "document_kind": "resume",
            "file_format": "hh_txt",
            "synthetic": True,  # учебный контур: в рабочих списках не показывается
        },
        {
            "source_path": f"{CONSULTANT_FOLDER}/hr-9001.docx",
            "candidate_code": "hr-9001",
            "position_code": "hr-consultant",
            "channel": "hh_ru",
            "document_kind": "resume",
            "file_format": "hh_docx",
            "synthetic": True,
        },
    ]
}


def write_fixtures(root: Path = ROOT) -> None:
    (root / PYTHON_FOLDER).mkdir(parents=True, exist_ok=True)
    (root / CONSULTANT_FOLDER).mkdir(parents=True, exist_ok=True)
    (root / PYTHON_FOLDER / "py-9001.txt").write_bytes(PY_9001.encode("utf-8"))
    (root / PYTHON_FOLDER / "Вакансия.txt").write_bytes(VACANCY.encode("utf-8"))
    (root / PYTHON_FOLDER / "py-9002.pdf").write_bytes(build_blank_pdf())
    (root / CONSULTANT_FOLDER / "hr-9001.docx").write_bytes(build_docx(HR_9001_PARAGRAPHS, HR_9001_TABLE))
    (root / "mapping.json").write_text(json.dumps(MAPPING, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_fixtures()
    print(f"пакет записан: {ROOT}")
