"""Render a fixed report version as a standalone workbook with native charts."""
import io

import xlsxwriter


LABELS = {
    "applications_received": "Поступившие отклики",
    "phone_interviews_held": "Состоявшиеся телефонные интервью",
    "applications_with_phone_interview": "Отклики с разговором",
}
STATUS = {
    "complete": "Полные данные",
    "partial": "Неполные данные",
    "unavailable": "Нет данных",
    "future": "За пределами периода",
}
OUTCOMES = {"continue": "Продолжили", "stop": "Завершили", "pending": "Ожидают решения"}
COMPARISON = {
    "incomplete_coverage": "Неполное покрытие",
    "incomparable_source": "Источники несопоставимы",
    "zero_baseline": "Нет базы для процента",
    "interim_period": "Промежуточный период",
}


def write_metric(sheet, row, column, metric):
    """Keep an observed lower bound numeric, with its meaning in the adjacent cell."""
    if metric["value"] is not None:
        sheet.write_number(row, column, metric["value"])
    status = STATUS[metric["status"]]
    if metric["status"] == "partial" and metric["value"] is not None:
        status = "Не менее"
    sheet.write_string(row, column + 1, status)


def make_workbook(report: dict) -> bytes:
    buffer = io.BytesIO()
    options = {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}
    with xlsxwriter.Workbook(buffer, options) as book:
        summary = book.add_worksheet("Итоги")
        monthly = book.add_worksheet("Помесячно")
        detail = book.add_worksheet("Вакансии")
        notes = book.add_worksheet("Методика")
        title = book.add_format({"bold": True, "font_size": 17, "font_color": "#174C49"})
        head = book.add_format({"bold": True, "bg_color": "#D8EEEB", "text_wrap": True})
        mode = "Учебный" if report["mode"] == "demo" else "Рабочий"
        summary.write(0, 0, f"Годовой отчёт о подборе · {report['year']}", title)
        summary.write(1, 0, report["scope_label"])
        period = "Промежуточный" if report["interim"] else "Закрытый год"
        summary.write(2, 0, f"{mode} · {period} · граница наблюдения {report['observed_until']} (исключая дату)")
        summary.write(3, 0, f"Выгрузка {report['extracted_at']}")
        summary.write(4, 0, f"Версия {report['snapshot_id']}")
        summary.write_row(6, 0, ["Показатель", "Число", "Покрытие", "Изменение, ед.", "Изменение, %", "Условие сравнения"], head)
        for row, (key, name) in enumerate(LABELS.items(), 7):
            summary.write(row, 0, name)
            write_metric(summary, row, 1, report["totals"][key])
            comparison = report["comparison"][key]
            summary.write(row, 3, comparison["delta"])
            summary.write(row, 4, comparison["percent"])
            summary.write(row, 5, COMPARISON.get(comparison["reason"]))
        summary.set_column(0, 0, 38)
        summary.set_column(1, 5, 21)
        monthly.set_column(0, 0, 13)
        monthly.set_column(1, 18, 21)
        series = list(LABELS.values()) + list(OUTCOMES.values()) + ["Отклики год назад"]
        monthly.write_row(0, 0, ["Месяц", *[cell for name in series for cell in (name, "Покрытие")],
                                "Точная оценка", "Нижняя граница",
                                "Год назад, точно", "Год назад, нижняя граница"], head)
        monthly.set_row(0, 48)
        for row, (month, previous) in enumerate(zip(report["months"], report["previous_months"], strict=True), 1):
            monthly.write(row, 0, month["month"])
            previous_count = previous["metrics"]["applications_received"]
            metrics = [*[month["metrics"][key] for key in LABELS],
                       *[month["outcomes"][key] for key in OUTCOMES], previous_count]
            for number, metric in enumerate(metrics):
                write_metric(monthly, row, 1 + number * 2, metric)
            for base, metric in [(15, metrics[0]), (17, previous_count)]:
                if metric["value"] is not None:
                    monthly.write_number(row, base + int(metric["status"] == "partial"), metric["value"])
        monthly.freeze_panes(1, 1)
        line = book.add_chart({"type": "line"})
        comparable = report["sources"]["applications"]["comparable_to_previous_year"]
        for offset, label in enumerate(["Отчётный год", "Отчётный год, не менее",
                                        "Предыдущий год", "Предыдущий год, не менее"]):
            if offset >= 2 and not comparable:
                continue
            color = "#1B7267" if offset < 2 else "#B47743"
            partial = offset % 2 == 1
            line.add_series({"name": label, "categories": ["Помесячно", 1, 0, 12, 0],
                             "values": ["Помесячно", 1, 15 + offset, 12, 15 + offset],
                             "line": {"none": True} if partial else {"color": color},
                             "marker": {"type": "diamond" if partial else "circle", "size": 5,
                                        "fill": {"color": color}}})
        line.show_blanks_as("gap")
        line.set_title({"name": "Динамика поступления откликов"})
        summary.insert_chart("A13", line)
        stacked = book.add_chart({"type": "column", "subtype": "stacked"})
        for index, (outcome, label) in enumerate(OUTCOMES.items()):
            points = [{"fill": {"color": "#A6ABB2"}} if m["outcomes"][outcome]["status"] == "partial" else None
                      for m in report["months"]]
            stacked.add_series({"name": label, "categories": ["Помесячно", 1, 0, 12, 0],
                                "values": ["Помесячно", 1, 7 + index * 2, 12, 7 + index * 2],
                                "points": points})
        stacked.set_title({"name": "Разговоры по исходам · серым показана нижняя граница"})
        summary.insert_chart("A30", stacked)
        detail.write_row(0, 0, ["Период", "Вакансия", "Поступления", "Покрытие", "С разговором", "Покрытие"], head)
        detail.set_column(0, 0, 15)
        detail.set_column(1, 1, 42)
        detail.set_column(2, 5, 21)
        detail.freeze_panes(1, 2)
        row = 1
        for interval, vacancies in [(str(report["year"]), report["vacancies"]),
                                    *((m["month"], m["vacancies"]) for m in report["months"])]:
            for vacancy in vacancies:
                detail.write_row(row, 0, [interval, vacancy["label"]])
                write_metric(detail, row, 2, vacancy["applications_received"])
                write_metric(detail, row, 4, vacancy["applications_with_phone_interview"])
                row += 1
        if report["vacancies"]:
            bar = book.add_chart({"type": "bar"})
            end = len(report["vacancies"])
            bar.add_series({"name": "Поступления", "categories": ["Вакансии", 1, 1, end, 1],
                            "values": ["Вакансии", 1, 2, end, 2],
                            "points": [{"fill": {"color": "#A6ABB2"}} if v["applications_received"]["status"] == "partial"
                                       else None for v in report["vacancies"]]})
            bar.set_y_axis({"reverse": True})
            bar.set_title({"name": "Вакансии по поступлениям · серым показана нижняя граница"})
            summary.insert_chart("A47", bar)
        notes.set_column(0, 0, 36)
        notes.set_column(1, 1, 95)
        notes.write_row(0, 0, ["Показатель", "Правило"], head)
        notes.write_row(1, 0, [LABELS["applications_received"], "Разные отклики по дате поступления."])
        notes.write_row(2, 0, [LABELS["phone_interviews_held"], "Разные состоявшиеся разговоры по фактической дате."])
        notes.write_row(3, 0, [LABELS["applications_with_phone_interview"], "Разные отклики с разговором за период. Год считается по объединению откликов."])
        notes.write_row(4, 0, ["Нижняя граница", "В источнике есть пропуск. Нулевое точное значение требует полного покрытия."])
        notes.write_row(5, 0, ["Идентификатор версии", report["snapshot_id"]])
        notes.write_row(6, 0, ["Версия методики", report["metric_version"]])
        for row, (name, source) in enumerate(report["sources"].items(), 8):
            notes.write_row(row, 0, [name, f"{source['source_id']} · {source['source_revision']}"])
        for row, (name, count) in enumerate(report["quality"].items(), 11):
            notes.write_row(row, 0, [name, count])
        from .analysis_excel import add_brief, add_heatmap, operations_sheet
        from .operations import query_operations

        brief = add_brief(book, report)
        brief.activate()
        brief.set_first_sheet()
        add_heatmap(book, report)
        if report.get("operations"):
            operations_sheet(book, report, query_operations(report, 1, 12, []))
    return buffer.getvalue()
