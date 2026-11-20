"""Разбор «Истории общения с кандидатом» (app/ingest/history.py) без базы.

Тексты повторяют форму выгрузки hh.ru из архива «Кадры»; названия и даты выдуманы.
"""
from datetime import date

from app.ingest.history import HistoryEntry, parse_history, parse_russian_date, title_key

RESUME_HEAD = "ФИО 9001\nЖенщина, 31 год, родилась 5 марта 1995\nОпыт работы\nОрганизация 1\n"
TAIL = "\nФИО 9001  •  Резюме обновлено 16 августа 2026 в 11:58\nРезюме обновлено 16 августа 2026 в 11:58\n"


def footer(title: str, when: str) -> str:
    return f"Отклик на вакансию: «{title}»\n{when} \n"


def test_only_entry_equal_to_footer_is_the_response_itself():
    text = (
        RESUME_HEAD
        + "История общения с кандидатом\n"
        + "Откликнулся\tКонсультант отдела кадровой работы\n6 августа 2026\n\n"
        + TAIL
        + footer("Консультант отдела кадровой работы", "6 августа 2026")
    )
    parsed = parse_history(text)

    assert parsed.has_block
    assert parsed.response_title == "Консультант отдела кадровой работы"
    assert parsed.response_date == date(2026, 8, 6)
    assert parsed.entries == [HistoryEntry("Консультант отдела кадровой работы", date(2026, 8, 6), "Откликнулся")]
    assert parsed.external == []
    assert parsed.warnings == []


def test_entries_not_equal_to_footer_are_external():
    text = (
        RESUME_HEAD
        + "История общения с кандидатом\n"
        + "Откликнулся\tКонсультант отдела кадровой работы\n6 августа 2026\n\n"
        + "Консультант отдела муниципальной службы\n31 июля 2026\n\n"
        + "Главный специаст отдела мониторинга\n2 мая 2026\n"
        + TAIL
        + footer("Консультант отдела кадровой работы", "6 августа 2026")
    )
    parsed = parse_history(text)

    assert parsed.response_date == date(2026, 8, 6)
    assert parsed.external == [
        HistoryEntry("Консультант отдела муниципальной службы", date(2026, 7, 31)),
        # Опечатка организаторов сохраняется как есть.
        HistoryEntry("Главный специаст отдела мониторинга", date(2026, 5, 2)),
    ]
    assert parsed.warnings == []


def test_match_ignores_case_spaces_and_quotes():
    text = (
        "История общения с кандидатом\n"
        + "Откликнулась\t  консультант   отдела КАДРОВОЙ работы \n6 августа 2026\n"
        + TAIL
        + footer("Консультант отдела кадровой работы", "6 августа 2026")
    )
    parsed = parse_history(text)
    assert parsed.external == []
    assert title_key("«Консультант»  отдела") == title_key("консультант отдела")


def test_same_posting_other_date_is_still_the_response():
    text = (
        "История общения с кандидатом\n"
        + "Откликнулся\tКонсультант отдела кадровой работы\n1 августа 2026\n"
        + TAIL
        + footer("Консультант отдела кадровой работы", "6 августа 2026")
    )
    parsed = parse_history(text)
    assert parsed.external == []
    assert parsed.response_date == date(2026, 8, 6)  # дата отклика — из подвала
    assert parsed.warnings == ["history_date_mismatch"]


def test_without_footer_all_entries_are_external():
    text = (
        "История общения с кандидатом\n"
        + "Откликнулся\tКонсультант отдела прогнозирования\n6 августа 2026\n\n"
        + "Консультант отдела антикоррупционного контроля\n31 июля 2026\n"
        + TAIL
    )
    parsed = parse_history(text)
    assert parsed.response_title is None
    assert parsed.response_date is None
    assert [entry.title for entry in parsed.external] == [
        "Консультант отдела прогнозирования", "Консультант отдела антикоррупционного контроля",
    ]
    assert parsed.warnings == ["history_no_footer"]


def test_footer_without_block_dates_the_response():
    parsed = parse_history(RESUME_HEAD + TAIL + footer("Сметчик", "5 сентября 2026"))
    assert not parsed.has_block
    assert parsed.found
    assert (parsed.response_title, parsed.response_date) == ("Сметчик", date(2026, 9, 5))
    assert parsed.external == []


def test_resume_without_history_and_footer():
    parsed = parse_history(RESUME_HEAD + "Навыки\nExcel\n")
    assert not parsed.found
    assert parsed.entries == [] and parsed.external == [] and parsed.warnings == []


def test_repeated_entry_gives_one_external_application():
    text = (
        "История общения с кандидатом\n"
        + "Откликнулся\tКонсультант отдела прогнозирования\n6 августа 2026\n\n"
        + "Консультант отдела прогнозирования\n6 августа 2026\n"
        + TAIL
        + footer("Сметчик", "1 сентября 2026")
    )
    assert parse_history(text).external == [
        HistoryEntry("Консультант отдела прогнозирования", date(2026, 8, 6), "Откликнулся"),
    ]


def test_unknown_status_is_kept_with_warning():
    text = (
        "История общения с кандидатом\n"
        + "Приглашение\tКонсультант отдела прогнозирования\n6 августа 2026\n"
        + TAIL
        + footer("Сметчик", "1 сентября 2026")
    )
    parsed = parse_history(text)
    assert parsed.external == [HistoryEntry("Консультант отдела прогнозирования", date(2026, 8, 6), "Приглашение")]
    assert parsed.warnings == ["history_unknown_status"]


def test_broken_block_is_reported_not_guessed():
    text = "История общения с кандидатом\nКонсультант отдела прогнозирования\nвчера\n" + TAIL
    parsed = parse_history(text)
    assert parsed.has_block
    assert parsed.entries == []
    assert parsed.warnings == ["history_unparsed"]


def test_extra_line_inside_block_is_reported():
    text = (
        "История общения с кандидатом\n"
        + "Комментарий без даты\n"
        + "Откликнулся\tКонсультант отдела прогнозирования\n6 августа 2026\n"
        + TAIL
        + footer("Сметчик", "1 сентября 2026")
    )
    parsed = parse_history(text)
    assert [entry.title for entry in parsed.external] == ["Консультант отдела прогнозирования"]
    assert parsed.warnings == ["history_unrecognized_lines"]


def test_russian_dates():
    assert parse_russian_date("6 августа 2026") == date(2026, 8, 6)
    assert parse_russian_date(" 31 мая 2026 ") == date(2026, 5, 31)
    assert parse_russian_date("31 июня 2026") is None
    assert parse_russian_date("6 August 2026") is None
    assert parse_russian_date("Резюме обновлено 8 сентября 2026 в 16:54") is None
