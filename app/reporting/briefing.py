"""Evidence-linked statements for a management report, independent of the client."""
from .analytics import AnalyticsQuery, catalog, query_report
from .operations import query_operations
from .signals import build_signals

REASONS = {
    "missing_business_date": "Есть записи без даты события",
    "coverage_gap": "Источник охватывает часть периода",
    "coverage_unknown": "Полнота источника неизвестна",
    "outside_period": "За пределами периода наблюдения",
    "zero_baseline": "В базовом периоде ноль",
}


def display(cell):
    value = cell["value"]
    if value is None:
        return {"future": "за пределами периода", "partial": "неполные данные"}.get(cell["status"], "нет данных")
    number = f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    return ("не менее " if cell["status"] == "partial" else "") + number


def executive_brief(report):
    findings = []

    def add(section, statement, evidence):
        findings.append({"section": section, "statement": statement, "evidence": evidence})

    totals = report["totals"]
    add("Поступления", f"Отклики за период — {display(totals['applications_received'])}.",
        "totals.applications_received")
    add("Телефонный отбор",
        f"Состоявшиеся разговоры — {display(totals['phone_interviews_held'])}. "
        f"Отклики с разговором — {display(totals['applications_with_phone_interview'])}.",
        "totals.phone_interviews_held, totals.applications_with_phone_interview")
    measured = [m for m in report["months"] if m["metrics"]["applications_received"]["value"]]
    if measured:
        peak = max(m["metrics"]["applications_received"]["value"] for m in measured)
        leaders = [m["month"] for m in measured if m["metrics"]["applications_received"]["value"] == peak]
        add("Нагрузка", f"Максимум среди датированных поступлений — {peak}. "
            f"Месяцы с таким числом: {', '.join(leaders)}.", "months[].metrics.applications_received")
    undated = report["quality"]["undated_applications"]
    if undated:
        add("Что уточнить", f"Уточнить даты у {undated} откликов исходного пакета. "
            "Пока их нельзя распределить между месяцами.", "quality.undated_applications")
    if totals["phone_interviews_held"]["status"] == "unavailable":
        add("Что уточнить", "Для оценки сроков первого разговора и исходов нужен журнал телефонных интервью.",
            "totals.phone_interviews_held.status")

    if report.get("analytics_index") is not None:
        cohort = query_report(report, AnalyticsQuery(metrics=["phone_within_14d_pct", "median_days_to_first_call"],
                                                   compare_previous=False))["totals"]
        for key, title, unit in [("phone_within_14d_pct", "Первый разговор в течение 14 дней", "%"),
                ("median_days_to_first_call", "Медиана ожидания среди откликов с первым разговором", " дн")]:
            if cohort[key]["value"] is not None:
                add("Сроки подбора", f"{title} — {display(cohort[key])}{unit}.", f"analytics.total.{key}")
    if report.get("operations"):
        ops = query_operations(report, 1, 12, [])
        for section, metric, title in [
                ("workforce", "headcount", "Численность на конец периода"),
                ("workforce", "hires", "Принято за период"), ("workforce", "exits", "Выбыло за период"),
                ("handoffs", "open_over_15", "Передачи без ответа более 15 дней на дату среза")]:
            cell = ops[section][metric]
            add("Штат и подразделения", f"{title} — {display(cell)}.", f"operations.{section}.{metric}")
        open_cell = ops["handoffs"]["open"]
        if open_cell["status"] == "complete" and open_cell["value"]:
            largest = max(ops["by_department"], key=lambda d: d["handoffs"]["open"]["value"] or 0)
            add("Ожидают ответа", f"Всего открытых передач — {display(open_cell)}. "
                f"В подразделении «{largest['label']}» — {display(largest['handoffs']['open'])}.",
                "operations.by_department[].handoffs.open")

    section_titles = {"contributions": "Вклад вакансий", "heatmap": "Нагрузка по вакансиям",
                      "unusual_volume": "Отклонение объёма"}
    for signal in build_signals(report)["signals"]:
        findings.append({**signal, "section": section_titles.get(signal["section"], signal["section"])})
    return {"snapshot_id": report["snapshot_id"], "scope": report["scope_label"],
            "year": report["year"], "mode": report["mode"], "period_start": report["period_start"],
            "period_end_exclusive": report["period_end_exclusive"], "findings": findings,
            "sources": report["sources"], "quality": report["quality"]}


def chart_specs(report, result):
    """Inline Vega-Lite per measure. Independent scales preserve incompatible units."""
    definitions = {metric["key"]: metric for metric in catalog()["metrics"]}
    vacancies = {v["vacancy_key"]: v["label"] for v in report["vacancies"]}
    outcomes = {"continue": "Продолжили", "stop": "Завершили", "pending": "Ожидают решения"}
    specs = []
    for key in result["query"]["metrics"]:
        metric = definitions[key]
        points = []
        for row in result["rows"]:
            parts = []
            for name, item in row["dimensions"].items():
                if name == "vacancy":
                    item = vacancies.get(item, item)
                elif name == "outcome":
                    item = outcomes.get(item, item)
                parts.append(str(item))
            label = " · ".join(parts) or "За период"
            cell = row["metrics"][key]
            points.append({"group": label, "value": cell["value"], "reading": display(cell),
                           "quality": cell["status"]})
        specs.append({"metric": key, "spec": {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": metric["label"], "description": metric["definition"], "width": "container",
            "data": {"values": points}, "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "y": {"field": "group", "type": "nominal", "sort": None, "title": None},
                "x": {"field": "value", "type": "quantitative", "title": metric["label"]},
                "color": {"field": "quality", "type": "nominal", "legend": None,
                          "scale": {"domain": ["complete", "partial"], "range": ["#126760", "#b97724"]}},
                "tooltip": [{"field": "group", "title": "Срез"}, {"field": "reading", "title": metric["label"]}],
            }}})
    return specs
