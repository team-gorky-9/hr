"""Разбор блока «История общения с кандидатом» из резюме hh.ru (DOCX консультанта).

Как выглядит выгрузка hh (архив «Кадры», 229 из 287 резюме DOCX):

    История общения с кандидатом
    Откликнулся<TAB>Консультант отдела кадровой работы
    6 августа 2026

    Консультант отдела муниципальной службы
    31 июля 2026

    ФИО N  •  Резюме обновлено 16 августа 2026 в 11:58
    Резюме обновлено 16 августа 2026 в 11:58
    Отклик на вакансию: «Консультант отдела кадровой работы»
    6 августа 2026

Запись истории — строка «[статус<TAB>]название публикации» и строка с датой. Подвал
«Отклик на вакансию: «…»» называет публикацию, на которую пришёл сам этот отклик.

Главное правило (план ingest-02): запись, совпадающая с подвалом по названию, — это не
другая должность, а тот же отклик, из-за которого резюме попало в архив (226 из 229 файлов).
Из неё берём только дату. Внешними откликами (`applications.source = history`) становятся
лишь записи, которые с подвалом не совпадают.

Функции здесь чистые: на входе извлечённый текст (`source_documents.raw_text`, до очистки ПДн —
названия должностей не ПДн, а очистка могла бы их задеть), на выходе — разобранные записи.
"""
import re
from dataclasses import dataclass, field
from datetime import date

HISTORY_HEADER = "История общения с кандидатом"
# Статус, который hh пишет у отклика. Другие («Приглашение», «Отказ») в архиве не встречаются,
# их запись всё равно сохраняется, но с предупреждением.
KNOWN_STATUSES = {"откликнулся", "откликнулась"}

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_DATE_LINE = re.compile(r"^(\d{1,2})\s+([а-яё]+)\s+(\d{4})$", re.IGNORECASE)
_FOOTER = re.compile(r"^Отклик на вакансию:\s*«(?P<title>.+)»\s*$")
# Строки, которыми кончается блок истории: шапка «ФИО N • Резюме обновлено …» и подвал.
_BLOCK_END = re.compile(r"^(ФИО\b.*•|Резюме обновлено\b|Отклик на вакансию:)")


@dataclass(frozen=True)
class HistoryEntry:
    title: str
    applied_at: date | None
    status: str | None = None


@dataclass
class HistoryParse:
    """Что нашлось в тексте резюме.

    response_title / response_date — публикация и дата из подвала (сам отклик);
    external — записи истории, которые не совпали с подвалом (отклики на другие должности);
    warnings — коды для отчёта импорта, без текста.
    """
    has_block: bool = False
    response_title: str | None = None
    response_date: date | None = None
    entries: list[HistoryEntry] = field(default_factory=list)
    external: list[HistoryEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.has_block or self.response_title is not None


def parse_russian_date(line: str) -> date | None:
    """«6 августа 2026» → date(2026, 8, 6); всё остальное → None."""
    match = _DATE_LINE.match(line.strip())
    if match is None:
        return None
    month = MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:  # «31 июня» — не дата
        return None


def clean_title(title: str) -> str:
    """Название как в выгрузке, но без лишних пробелов. Опечатки организаторов не правим."""
    return " ".join(title.split())


def title_key(title: str) -> str:
    """Ключ сравнения названий: без регистра, кавычек и разницы в пробелах."""
    return " ".join(title.replace("«", " ").replace("»", " ").replace('"', " ").split()).casefold()


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n")]


def _parse_footer(lines: list[str]) -> tuple[str | None, date | None]:
    for index, line in enumerate(lines):
        match = _FOOTER.match(line)
        if match is None:
            continue
        following = next((other for other in lines[index + 1:] if other), "")
        return clean_title(match.group("title")), parse_russian_date(following)
    return None, None


def _parse_block(lines: list[str], start: int) -> tuple[list[HistoryEntry], list[str]]:
    """Записи блока, начиная со строки после заголовка, до шапки/подвала."""
    block: list[str] = []
    for line in lines[start:]:
        if _BLOCK_END.match(line):
            break
        if line:
            block.append(line)

    entries: list[HistoryEntry] = []
    warnings: list[str] = []
    used = [False] * len(block)
    for index, line in enumerate(block):
        applied_at = parse_russian_date(line)
        if applied_at is None or index == 0 or used[index - 1]:
            continue
        status, _, title = block[index - 1].rpartition("\t")
        status = status.strip() or None
        title = clean_title(title)
        if not title:
            continue
        used[index - 1] = used[index] = True
        entries.append(HistoryEntry(title=title, applied_at=applied_at, status=status))
        if status is not None and status.casefold() not in KNOWN_STATUSES:
            warnings.append("history_unknown_status")

    if not entries:
        warnings.append("history_unparsed")
    elif not all(used):
        warnings.append("history_unrecognized_lines")
    return entries, warnings


def parse_history(text: str) -> HistoryParse:
    lines = _lines(text)
    result = HistoryParse()
    result.response_title, result.response_date = _parse_footer(lines)

    header = next((index for index, line in enumerate(lines) if line == HISTORY_HEADER), None)
    if header is None:
        return result
    result.has_block = True
    result.entries, result.warnings = _parse_block(lines, header + 1)

    # Отделяем сам отклик от откликов на другие должности.
    response_key = title_key(result.response_title) if result.response_title else None
    if response_key is None and result.entries:
        # Без подвала не угадываем, какая из записей «своя»: все — внешние.
        result.warnings.append("history_no_footer")
    matched_dates = []
    seen: set[tuple[str, date | None]] = set()
    for entry in result.entries:
        if response_key is not None and title_key(entry.title) == response_key:
            matched_dates.append(entry.applied_at)
            continue
        key = (title_key(entry.title), entry.applied_at)
        if key in seen:  # одна и та же запись дважды — один отклик
            continue
        seen.add(key)
        result.external.append(entry)
    if matched_dates and result.response_date is not None and result.response_date not in matched_dates:
        # Публикация та же, дата другая (11 файлов архива): дата отклика — из подвала.
        result.warnings.append("history_date_mismatch")
    if result.response_date is None and matched_dates:
        result.response_date = matched_dates[0]
    return result
