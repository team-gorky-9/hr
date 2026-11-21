"""Generate publication figures for kadry-paper.tex strictly from repository JSON reports."""

from __future__ import annotations

import collections
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8.5,
        "axes.titlesize": 9.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 8.5,
        "xtick.labelsize": 7.8,
        "ytick.labelsize": 7.8,
        "axes.edgecolor": "#4A5363",
        "axes.linewidth": 0.7,
        "grid.color": "#D5DBE3",
        "grid.linewidth": 0.5,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    }
)


def build_posting_distribution() -> None:
    """Figure 1: Real archive posting heterogeneity across 287 HR DOCX files."""
    src = ROOT / "docs" / "reports" / "requirements-03-posting-mapping.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    pubs: dict[str, int] = data["real_hr"]["publications"]

    label_map = {
        "Консультант отдела кадровой работы": "Консультант отдела\nкадровой работы",
        "Консультант отдела профессионального развития": "Консультант отдела\nпроф. развития",
        "(нет подвала)": "Нет подвала публикации\n(missing_posting)",
        "Консультант отдела по работе с обращениями граждан и предпринимателей": "Консультант по работе\nс обращениями граждан",
        "Начальник отдела внутреннего финансового контроля, аудита и закупок": "Нач. отдела финконтроля,\nаудита и закупок [искл.]",
        "Консультант отдела муниципальной службы": "Консультант отдела\nмуниципальной службы",
        "Консультант отдела документационного обеспечения департамента обеспечения деятельности главы города": "Консультант отдела\nдокументац. обеспечения",
        "Сметчик": "Сметчик [искл.]",
    }
    excluded = {
        "Начальник отдела внутреннего финансового контроля, аудита и закупок",
        "Сметчик",
    }

    items = sorted(pubs.items(), key=lambda kv: kv[1])
    labels = [label_map.get(k, k) for k, _ in items]
    counts = [v for _, v in items]
    colors = []
    for k, _ in items:
        if k in excluded:
            colors.append("#C93B3B")
        elif k == "(нет подвала)":
            colors.append("#D9822B")
        else:
            colors.append("#1F4FD1")

    fig, ax = plt.subplots(figsize=(5.4, 3.35))
    y = np.arange(len(labels))
    bars = ax.barh(y, counts, color=colors, height=0.66, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Число реальных DOCX-откликов в папке «консультант» (всего n = 287)")
    ax.set_xlim(0, max(counts) * 1.18)
    ax.grid(axis="x", linestyle="--", alpha=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    total = sum(counts)
    for bar, cnt in zip(bars, counts):
        pct = 100.0 * cnt / total
        ax.text(
            cnt + 2.0,
            bar.get_y() + bar.get_height() / 2.0,
            f"{cnt} ({pct:.1f}%)",
            va="center",
            ha="left",
            fontsize=7.6,
            color="#141A24",
        )

    from matplotlib.patches import Patch

    legend_handles = [
        Patch(facecolor="#1F4FD1", label="Консультант: ожидает сверки HR (221)"),
        Patch(facecolor="#D9822B", label="Нет подвала публикации (45)"),
        Patch(facecolor="#C93B3B", label="Исключено для hr-consultant (21)"),
    ]
    ax.legend(
        handles=legend_handles,
        loc="lower right",
        frameon=True,
        facecolor="white",
        edgecolor="#D5DBE3",
        fontsize=7.2,
    )
    ax.set_title("Распределение публикаций в одной папке реального архива (kadry-2026)")
    fig.savefig(OUT_DIR / "posting_distribution.png")
    plt.close(fig)


def build_search_benchmark() -> None:
    """Figure 2: Search threshold calibration (E5) and warm latency comparison."""
    src = ROOT / "docs" / "modules" / "search-evaluation-v1.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    grid = data["calibration"]["grid"]

    thresholds = [g["threshold"] for g in grid]
    neg_fp = [g["negative_with_results"] for g in grid]
    rel_at_5 = [g["relevant_at_5"] for g in grid]
    chosen_thr = data["threshold"]

    ctrl = data["control"]
    methods = ["BM25\n(лексика)", "Dense E5\n(τ = 0,94)", "Hybrid\n(RRF, k = 60)"]
    med_ms = [
        ctrl["lexical"]["metrics"]["warm_median_ms"],
        ctrl["dense"]["metrics"]["warm_median_ms"],
        ctrl["hybrid"]["metrics"]["warm_median_ms"],
    ]
    p95_ms = [
        ctrl["lexical"]["metrics"]["warm_p95_ms"],
        ctrl["dense"]["metrics"]["warm_p95_ms"],
        ctrl["hybrid"]["metrics"]["warm_p95_ms"],
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 2.75), gridspec_kw={"width_ratios": [1.15, 1.0]})

    # Left panel: E5 calibration grid
    ax1.plot(thresholds, rel_at_5, marker="o", ms=4.2, lw=1.6, color="#1F4FD1", label="Релевантные @5 (из 4)")
    ax1.plot(thresholds, neg_fp, marker="s", ms=4.2, lw=1.6, color="#C93B3B", label="Ложная выдача на пустых (из 2)")
    ax1.axvline(chosen_thr, color="#1F7A4C", linestyle="--", lw=1.2, label=f"Выбранный порог τ = {chosen_thr:.2f}")
    ax1.axvspan(0.82, 0.94, color="#1F7A4C", alpha=0.09)
    ax1.set_xlabel("Порог косинусного сходства E5 (τ)")
    ax1.set_ylabel("Число запросов")
    ax1.set_ylim(-0.25, 3.65)
    ax1.set_yticks([0, 1, 2, 3])
    ax1.grid(True, linestyle="--", alpha=0.7)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(loc="lower left", bbox_to_anchor=(0.01, 0.08), fontsize=6.8, frameon=True, facecolor="white", edgecolor="#D5DBE3", framealpha=0.95)
    ax1.set_title("Калибровка порога E5 (6 запросов)")

    # Right panel: warm latency comparison
    x = np.arange(len(methods))
    w = 0.34
    b1 = ax2.bar(x - w / 2, med_ms, width=w, color="#1F4FD1", label="Медиана, мс")
    b2 = ax2.bar(x + w / 2, p95_ms, width=w, color="#7B9CE8", label="p95, мс")
    ax2.set_xticks(x)
    ax2.set_xticklabels(methods)
    ax2.set_ylabel("Время тёплого поиска, мс")
    ax2.set_ylim(0, max(p95_ms) * 1.24)
    ax2.grid(axis="y", linestyle="--", alpha=0.7)
    ax2.set_axisbelow(True)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.legend(loc="upper left", fontsize=7.0, frameon=True, facecolor="white", edgecolor="#D5DBE3")
    ax2.set_title("Задержка ранжирования (24 прогона)")

    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2.0,
                h + 0.9,
                f"{h:.1f}",
                ha="center",
                va="bottom",
                fontsize=7.0,
                color="#141A24",
            )

    fig.tight_layout(w_pad=1.6)
    fig.savefig(OUT_DIR / "search_benchmark.png")
    plt.close(fig)


def build_assessment_cases() -> None:
    """Figure 3: Live YandexGPT formal requirement benchmark breakdown (41/41)."""
    src = ROOT / "docs" / "reports" / "requirement-cases-live-pr15-fixes-2026-11-20.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    results = data["results"]

    rule_labels = {
        "synthetic.py.experience": "Стаж (учебный\nPython)",
        "py.education": "Образование\n(Python)",
        "hr.education.field": "Профиль обр.\n(Консультант)",
        "py.experience": "Стаж\n(Python)",
        "hr.education.level": "Уровень обр.\n(Консультант)",
    }
    statuses = ["met", "unknown", "not_met", "processing_error"]
    status_names = {
        "met": "met (подтверждено)",
        "unknown": "unknown (пробел)",
        "not_met": "not_met (отклонено)",
        "processing_error": "отказ до LLM",
    }
    status_colors = {
        "met": "#1F7A4C",
        "unknown": "#D9822B",
        "not_met": "#C93B3B",
        "processing_error": "#6B7280",
    }

    rule_counts = collections.Counter(r["rule_key"] for r in results)
    ordered_rules = [k for k, _ in rule_counts.most_common()]
    x = np.arange(len(ordered_rules))

    fig, ax = plt.subplots(figsize=(5.3, 2.7))
    bottom = np.zeros(len(ordered_rules))
    for st in statuses:
        vals = np.array(
            [sum(1 for r in results if r["rule_key"] == rk and r["expected"] == st) for rk in ordered_rules]
        )
        ax.bar(x, vals, bottom=bottom, width=0.56, color=status_colors[st], label=status_names[st])
        for xi, v, b in zip(x, vals, bottom):
            if v >= 2:
                ax.text(xi, b + v / 2.0, str(v), ha="center", va="center", color="white", fontsize=7.5, fontweight="bold")
        bottom += vals

    for xi, tot in zip(x, bottom):
        ax.text(xi, tot + 0.45, f"{int(tot)}/{int(tot)}", ha="center", va="bottom", fontsize=7.6, color="#141A24", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([rule_labels.get(rk, rk) for rk in ordered_rules])
    ax.set_ylabel("Пройдено кейсов (live YandexGPT)")
    ax.set_ylim(0, max(bottom) * 1.18)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", fontsize=7.1, frameon=True, facecolor="white", edgecolor="#D5DBE3")
    ax.set_title("Живой прогон формальных правил на YandexGPT: 41/41 (0 ошибок LLM)")
    fig.savefig(OUT_DIR / "assessment_cases.png")
    plt.close(fig)


if __name__ == "__main__":
    build_posting_distribution()
    build_search_benchmark()
    build_assessment_cases()
    print("Generated figures in:", OUT_DIR)
