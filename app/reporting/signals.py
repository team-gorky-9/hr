"""Explain changes in the count of incoming applications using the frozen report only."""
from calendar import monthrange
from datetime import date, timedelta
from statistics import median

METRIC = "applications_received"
LOOKBACK = 12
MIN_HISTORY = 6
THRESHOLD = 3.5
NORMAL_MAD_SCALE = 1.4826


def _contributions(report):
    current = report["totals"][METRIC]
    previous = report["previous_totals"][METRIC]
    comparable = report["sources"]["applications"]["comparable_to_previous_year"]
    result = {"status": "unavailable", "reason": None, "current": current["value"],
              "previous": previous["value"], "current_status": current["status"],
              "previous_status": previous["status"], "net_change": None, "gross_change": None, "rows": []}
    if report["interim"]:
        result["reason"] = "interim_period"
    elif not comparable:
        result["reason"] = "incomparable_source"
    elif current["status"] != "complete" or previous["status"] != "complete":
        result["reason"] = "incomplete_coverage"
    if result["reason"]:
        return result

    # Application arrivals are additive over months. Unlike reached applicants, they
    # can be reconstructed from the saved monthly vacancy breakdown for the prior year.
    previous_counts = {}
    labels = {}
    for month in report["previous_months"]:
        for vacancy in month["vacancies"]:
            key = vacancy["vacancy_key"]
            cell = vacancy[METRIC]
            if cell["status"] != "complete":
                result["reason"] = "incomplete_vacancy_coverage"
                return result
            previous_counts[key] = previous_counts.get(key, 0) + cell["value"]
            labels[key] = vacancy["label"]
    current_counts = {}
    for vacancy in report["vacancies"]:
        key = vacancy["vacancy_key"]
        labels[key] = vacancy["label"]
        if vacancy[METRIC]["status"] != "complete":
            result["reason"] = "incomplete_vacancy_coverage"
            return result
        current_counts[key] = vacancy[METRIC]["value"]
    if sum(previous_counts.values()) != previous["value"] or sum(current_counts.values()) != current["value"]:
        result["reason"] = "inconsistent_vacancy_totals"
        return result
    rows = []
    for key, label in labels.items():
        before = previous_counts.get(key, 0)
        now = current_counts.get(key, 0)
        rows.append({"vacancy_key": key, "label": label, "previous": before, "current": now,
                     "delta": now - before})
    gross = sum(abs(row["delta"]) for row in rows)
    net = sum(row["delta"] for row in rows)
    for row in rows:
        row["share_of_gross_pct"] = round(100 * abs(row["delta"]) / gross, 2) if gross else None
        row["share_of_net_pct"] = round(100 * row["delta"] / net, 2) if net else None
    rows.sort(key=lambda row: (-abs(row["delta"]), row["vacancy_key"]))
    return {**result, "status": "complete", "net_change": net,
            "gross_change": gross, "rows": rows}


def _heatmap(report):
    cells = []
    for month in report["months"]:
        for vacancy in month["vacancies"]:
            cells.append({"month": month["month"], "vacancy_key": vacancy["vacancy_key"],
                          "label": vacancy["label"], **vacancy[METRIC]})
    return {"metric": METRIC, "months": [m["month"] for m in report["months"]],
            "vacancies": [{"vacancy_key": v["vacancy_key"], "label": v["label"]} for v in report["vacancies"]],
            "cells": cells}


def _closed(month, cutoff):
    year, number = map(int, month.split("-"))
    last = date(year, number, monthrange(year, number)[1])
    return last + timedelta(days=1) <= cutoff


def _unusual_volume(report):
    comparable = report["sources"]["applications"]["comparable_to_previous_year"]
    cutoff = date.fromisoformat(report["observed_until"])
    history = list(report["previous_months"]) if comparable else []
    rows = []
    for month in report["months"]:
        metric = month["metrics"][METRIC]
        recent = history[-LOOKBACK:]
        baseline = [m for m in recent if m["metrics"][METRIC]["status"] == "complete" and _closed(m["month"], cutoff)]
        values = [m["metrics"][METRIC]["value"] for m in baseline]
        center = median(values) if values else None
        mad = median(abs(v - center) for v in values) if values else None
        observed = metric["value"]
        row = {"month": month["month"], "observed": observed, "coverage": metric["status"],
               "reason_codes": metric["reason_codes"], "baseline_n": len(values),
               "baseline_months": [m["month"] for m in baseline], "median": center,
               "mad": mad, "deviation": None, "score": None, "status": "insufficient_history"}
        if not _closed(month["month"], cutoff):
            row["status"] = "open_or_future_month"
        elif metric["status"] != "complete":
            row["status"] = "incomplete_target"
        elif len(values) >= MIN_HISTORY:
            deviation = observed - center
            row["deviation"] = deviation
            if mad:
                score = deviation / (NORMAL_MAD_SCALE * mad)
                row["score"] = round(score, 4)
                row["status"] = "unusual" if abs(score) >= THRESHOLD else "within_range"
            elif max(values) == min(values):
                row["status"] = "flat_baseline_change" if deviation else "flat_baseline_unchanged"
            else:
                row["status"] = "zero_mad"
        rows.append(row)
        history.append(month)
    return {"metric": METRIC, "method": "rolling_median_mad", "min_history": MIN_HISTORY,
            "lookback_months": LOOKBACK, "normalizing_factor": NORMAL_MAD_SCALE, "threshold": THRESHOLD,
            "includes_prior_year": comparable, "year": report["year"], "months": rows}


def build_signals(report: dict) -> dict:
    contributions = _contributions(report)
    matrix = _heatmap(report)
    volume = _unusual_volume(report)
    statements = []

    def add(section, statement, evidence):
        statements.append({"section": section, "statement": statement,
                           "evidence": {"snapshot_id": report["snapshot_id"], "metric": METRIC, **evidence}})

    if contributions["status"] == "complete":
        net = contributions["net_change"]
        add("contributions", f"Откликов за год — {contributions['current']}, годом ранее — "
            f"{contributions['previous']}. Сумма изменений по вакансиям составляет {net:+d}.",
            {k: contributions[k] for k in ("current", "previous", "net_change", "gross_change")})
        if contributions["gross_change"]:
            leader = contributions["rows"][0]
            add("contributions", f"По вакансии «{leader['label']}» число откликов изменилось "
                f"с {leader['previous']} до {leader['current']} ({leader['delta']:+d}).", leader.copy())
    else:
        reasons = {"interim_period": "отчётный год ещё открыт", "incomparable_source": "источники двух лет несопоставимы",
                   "incomplete_coverage": "неполное покрытие года", "incomplete_vacancy_coverage": "неполное покрытие вакансий",
                   "inconsistent_vacancy_totals": "суммы по вакансиям расходятся с годовыми итогами"}
        add("contributions", f"Годовое изменение пока нельзя вычислить. Основание — {reasons[contributions['reason']]}.",
            {"reason": contributions["reason"], "year": report["year"]})

    complete_cells = [c for c in matrix["cells"] if c["status"] == "complete"]
    if complete_cells:
        largest = max(complete_cells, key=lambda c: c["value"])
        add("heatmap", f"Максимум среди полностью покрытых ячеек — {largest['value']} откликов "
            f"по вакансии «{largest['label']}» за {largest['month']}.",
            {**largest, "complete_cells": len(complete_cells), "all_cells": len(matrix["cells"])})

    for row in volume["months"]:
        if row["status"] == "unusual":
            add("unusual_volume", f"За {row['month']} учтено {row['observed']} откликов. Медиана предыдущих "
                f"полных месяцев — {row['median']:g}, MAD — {row['mad']:g}, нормированное отклонение — "
                f"{row['score']:g}.", row.copy())
        elif row["status"] == "flat_baseline_change":
            add("unusual_volume", f"За {row['month']} учтено {row['observed']} откликов. Каждый из предыдущих "
                f"{row['baseline_n']} покрытых месяцев имел {row['median']:g}. При постоянной базе "
                "нормированное отклонение неопределено.", row.copy())
    return {"snapshot_id": report["snapshot_id"], "year": report["year"], "signals": statements,
            "contributions": contributions, "heatmap": matrix, "unusual_volume": volume}
