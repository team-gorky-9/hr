"""Гайд интервью: пробелы оценки → уточняющие вопросы с критерием ответа (контракт interview.md v0.1).

Пробелы собирает код (gaps.py), формулировки — модель с проверкой ключей (generate.py).
Хранение гайда и ответов — модуль БД по контракту; здесь только расчёт.
"""
from app.interview.gaps import GapPlan, assemble_gaps
from app.interview.service import GuideDraft, build_guide

__all__ = ["GapPlan", "GuideDraft", "assemble_gaps", "build_guide"]
