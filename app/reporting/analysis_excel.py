"""Excel views of the same analytical results returned by the reporting API."""
from io import BytesIO
import json

import xlsxwriter

from .analytics import catalog
from .briefing import display, executive_brief
from .excel import OUTCOMES, STATUS

OPS_LABELS = {
    "authorized_fte": "Штатных ставок", "occupied_fte": "Занятых ставок", "headcount": "Сотрудников",
    "hires": "Принято", "exits": "Выбыло", "sent": "Передано", "answered": "Получено ответов",
    "open": "Ожидают ответа", "open_over_15": "Ожидают более 15 дней",
    "median_response_days": "Медиана срока ответа, дн.",
}
OPTIONS = {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}


def formats(book):
    return {
        "title": book.add_format({"font_size": 19, "bold": True, "font_color": "#ffffff",
                                  "bg_color": "#163C43", "valign": "vcenter"}),
        "sub": book.add_format({"font_size": 11, "font_color": "#174A49", "text_wrap": True,
                                "valign": "vcenter", "bg_color": "#E5F1EE"}),
        "head": book.add_format({"bold": True, "font_color": "#ffffff", "bg_color": "#206360",
                                 "text_wrap": True, "valign": "vcenter"}),
        "body": book.add_format({"text_wrap": True, "valign": "vcenter", "font_color": "#243E43"}),
        "label": book.add_format({"bold": True, "valign": "vcenter", "text_wrap": True,
                                  "font_color": "#126760"}),
    }


def heading(sheet, fmt, title, subtitle, last=5):
    sheet.hide_gridlines(2)
    sheet.merge_range(0, 0, 0, last, title, fmt["title"])
    sheet.merge_range(1, 0, 1, last, subtitle, fmt["sub"])
    sheet.set_row(0, 38)
    sheet.set_row(1, 34)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)


def source_label(report):
    mode = "Учебный пример" if report["mode"] == "demo" else "Рабочая выгрузка"
    return f"{report['scope_label']}  ·  {report['year']}  ·  {mode}"


def add_brief(book, report):
    sheet = book.add_worksheet("К докладу")
    fmt = formats(book)
    heading(sheet, fmt, "Кадровый доклад", source_label(report))
    sheet.merge_range(2, 0, 2, 5, f"Период с {report['period_start']} до {report['period_end_exclusive']} "
                      f"(исключительно) · версия {report['snapshot_id'][:12]}", fmt["body"])
    sheet.set_row(2, 25)
    sheet.set_column("A:A", 23)
    sheet.set_column("B:F", 15)
    for row, finding in enumerate(executive_brief(report)["findings"], 3):
        sheet.write(row, 0, finding["section"], fmt["label"])
        sheet.merge_range(row, 1, row, 5, finding["statement"], fmt["body"])
        sheet.set_row(row, 52)
        evidence = finding["evidence"]
        sheet.write_comment(row, 1, evidence if isinstance(evidence, str) else json.dumps(evidence, ensure_ascii=False))
    sheet.set_footer("&LВерсия " + report["snapshot_id"][:16] + "&RСтраница &P")
    return sheet


def add_heatmap(book, report):
    sheet = book.add_worksheet("Нагрузка по вакансиям")
    fmt = formats(book)
    heading(sheet, fmt, "Отклики по вакансиям и месяцам", source_label(report), 12)
    sheet.set_column(0, 0, 38)
    sheet.set_column(1, 12, 12)
    sheet.write_row(3, 0, ["Вакансия", *[m["month"] for m in report["months"]]], fmt["head"])
    by_month = [{v["vacancy_key"]: v for v in month["vacancies"]} for month in report["months"]]
    for row, vacancy in enumerate(report["vacancies"], 4):
        sheet.write_string(row, 0, vacancy["label"])
        for col, lookup in enumerate(by_month, 1):
            cell = lookup[vacancy["vacancy_key"]]["applications_received"]
            sheet.write(row, col, cell["value"] if cell["status"] == "complete" else display(cell))
    if report["vacancies"]:
        last = 3 + len(report["vacancies"])
        sheet.conditional_format(4, 1, last, 12, {"type": "2_color_scale", "min_color": "#F1F7F6",
                                                  "max_color": "#45A193"})
        sheet.autofilter(3, 0, last, 12)
    sheet.freeze_panes(4, 1)


def operations_sheet(book, report, result):
    sheet = book.add_worksheet("Штат и передачи")
    fmt = formats(book)
    heading(sheet, fmt, "Штат и работа подразделений", source_label(report))
    sheet.set_column("A:A", 24)
    sheet.set_column("B:B", 32)
    sheet.set_column("C:C", 32)
    sheet.set_column("D:D", 16)
    sheet.set_column("E:E", 25)
    sheet.set_column("F:F", 25)
    if not result["available"]:
        sheet.merge_range("A4:F4", "В этом пакете нет кадрового реестра и журнала передач.", fmt["body"])
        return
    sheet.write_row(3, 0, ["Разрез", "Группа", "Показатель", "Значение", "Покрытие", "Тип учёта"], fmt["head"])
    records = [("За период", "Выбранные подразделения", result)]
    records.extend(("Месяц", m["month"], m) for m in result["months"])
    records.extend(("Подразделение", d["label"], d) for d in result["by_department"])
    row = 4
    for group, label, record in records:
        for block in ("workforce", "handoffs"):
            for key, cell in record[block].items():
                unit = "На дату среза" if key in {"authorized_fte", "occupied_fte", "headcount", "open", "open_over_15"} else "За период"
                status = "Не менее" if cell["status"] == "partial" and cell["value"] is not None else STATUS.get(cell["status"], cell["status"])
                sheet.write_row(row, 0, [group, label, OPS_LABELS.get(key, key), cell["value"], status, unit])
                row += 1
    sheet.freeze_panes(4, 2)
    sheet.autofilter(3, 0, row - 1, 5)
    charts = book.add_worksheet("Динамика подразделений")
    heading(charts, fmt, "Штат, движение и ожидания", source_label(report), 6)
    charts.set_column(0, 6, 18)
    charts.write_row(3, 0, ["Месяц", "Штатные ставки", "Занятые ставки", "Принято", "Выбыло",
                             "Ожидают ответа", "Более 15 дней"], fmt["head"])
    for r, month in enumerate(result["months"], 4):
        cells = [month["workforce"][key] for key in ("authorized_fte", "occupied_fte", "hires", "exits")]
        cells.extend(month["handoffs"][key] for key in ("open", "open_over_15"))
        charts.write_row(r, 0, [month["month"], *[c["value"] if c["status"] == "complete" else None for c in cells]])
    charts.write(2, 0, "Диаграммы используют полностью покрытые значения. Нижние границы доступны на листе «Штат и передачи».")
    last = len(result["months"]) + 3
    for offset, (title, columns, kind) in enumerate([
        ("Штатные и занятые ставки", (1, 2), "line"), ("Приём и выбытие", (3, 4), "column"),
        ("Ожидаемые ответы на конец периода", (5, 6), "column")]):
        chart = book.add_chart({"type": kind})
        for col in columns:
            chart.add_series({"name": [charts.name, 3, col], "categories": [charts.name, 4, 0, last, 0],
                              "values": [charts.name, 4, col, last, col]})
        chart.set_title({"name": title})
        chart.show_blanks_as("gap")
        chart.set_legend({"position": "bottom"})
        charts.insert_chart(4 + offset * 17, 8, chart)


def operations_book(report, result, query):
    buffer = BytesIO()
    with xlsxwriter.Workbook(buffer, OPTIONS) as book:
        operations_sheet(book, report, result)
        passport(book, report, query)
    return buffer.getvalue()


def passport(book, report, query):
    sheet = book.add_worksheet("Параметры")
    sheet.set_column(0, 0, 29)
    sheet.set_column(1, 1, 80)
    fmt = formats(book)
    heading(sheet, fmt, "Параметры и происхождение", source_label(report), 1)
    rows = [("Версия отчёта", report["snapshot_id"]), ("Данные извлечены", report["extracted_at"]),
            ("Граница наблюдения", report["observed_until"]), ("Часовой пояс", report["timezone"])]
    rows.extend(query.items())
    rows.extend((name, f"{source['source_id']} · {source['source_revision']}")
                for name, source in report["sources"].items())
    if report.get("operations"):
        for name, source in report["operations"]["sources"].items():
            if source:
                rows.append((name, f"{source['source_id']} · {source['source_revision']}"))
    for row, (key, val) in enumerate(rows, 3):
        text = json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
        sheet.write_string(row, 0, key, fmt["label"])
        sheet.write_string(row, 1, text, fmt["body"])
        sheet.set_row(row, min(150, max(24, 18 * (1 + len(text) // 72))))


def analysis_book(report, result):
    buffer = BytesIO()
    definitions = {m["key"]: m for m in catalog()["metrics"]}
    vacancy_labels = {v["vacancy_key"]: v["label"] for v in report["vacancies"]}
    with xlsxwriter.Workbook(buffer, OPTIONS) as book:
        summary = book.add_worksheet("Сводка среза")
        sheet = book.add_worksheet("Анализ")
        fmt = formats(book)
        for tab in (summary, sheet):
            tab.set_column(0, 0, 29)
            tab.set_column(1, 1, 36)
            tab.set_column(2, 9, 20)
        q = result["query"]
        heading(summary, fmt, "Кадровый отчёт · выбранный срез",
                f"{source_label(report)}  ·  месяцы {q['start_month']:02d}–{q['end_month']:02d}")
        selected = ", ".join(vacancy_labels[k] for k in q["vacancy_keys"]) or "все вакансии"
        outcomes = ", ".join(OUTCOMES[k] for k in q["outcomes"]) or "все исходы"
        summary.merge_range(2, 0, 2, 5, f"{selected} · {outcomes}", fmt["body"])
        summary.set_row(2, 30)
        summary.set_column(0, 0, 42)
        summary.write_row(3, 0, ["Показатель", "Итог", "Год назад", "Изменение", "Числитель", "Знаменатель"], fmt["head"])
        for row, (key, cell) in enumerate(result["totals"].items(), 4):
            prev = cell.get("previous")
            unit = definitions[key]["unit"]
            label = definitions[key]["label"] + (", %" if unit == "%" else ", дни" if unit == "дни" else "")
            summary.write_row(row, 0, [label, cell["value"] if cell["status"] == "complete" else display(cell), prev, cell.get("delta"),
                                       cell.get("numerator"), cell.get("denominator")])
            if unit == "%":
                summary.write_comment(row, 3, "Разница между долями выражена в процентных пунктах.")
            summary.set_row(row, 26)
        heading(sheet, fmt, "Детализация", source_label(report), 9)
        sheet.write_row(3, 0, ["Группа", "Показатель", "Точное значение", "Нижняя граница", "Год назад",
                               "Изменение", "Изменение, %", "Числитель", "Знаменатель", "Качество"], fmt["head"])
        sheet.freeze_panes(4, 2)
        row = 4
        chart_pos = 6 + len(result["totals"])
        for key in q["metrics"]:
            start = row
            for group in result["rows"]:
                dims = group["dimensions"]
                parts = [str(vacancy_labels.get(v, v) if k == "vacancy" else OUTCOMES.get(v, v)
                             if k == "outcome" else v) for k, v in dims.items()]
                cell = group["metrics"][key]
                value = cell["value"]
                sheet.write_row(row, 0, [" · ".join(parts) or "За период", definitions[key]["label"],
                                         value if cell["status"] == "complete" else None,
                                         value if cell["status"] == "partial" else None,
                                         cell.get("previous"), cell.get("delta"), cell.get("percent_change"),
                                         cell.get("numerator"), cell.get("denominator"), STATUS.get(cell["status"], cell["status"])])
                row += 1
            if row > start and any(r["metrics"][key]["value"] is not None for r in result["rows"]):
                chart = book.add_chart({"type": "column"})
                end = min(row - 1, start + 23)
                for col, color, title in [(2, "#176B64", "Точно"), (3, "#C08432", "Не менее")]:
                    chart.add_series({"name": title, "categories": ["Анализ", start, 0, end, 0],
                                      "values": ["Анализ", start, col, end, col], "fill": {"color": color}})
                chart.set_title({"name": definitions[key]["label"] + (" · первые 24 группы" if end < row - 1 else "")})
                chart.set_legend({"position": "bottom"})
                chart.set_size({"width": 700, "height": 285})
                summary.insert_chart(chart_pos, 0, chart)
                chart_pos += 16
        if row > 4:
            sheet.autofilter(3, 0, row - 1, 9)
        passport(book, report, q)
    return buffer.getvalue()
