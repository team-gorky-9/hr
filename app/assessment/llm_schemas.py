"""Что модель возвращает при оценке. Статусы и цитаты — от модели, итог и числа — от кода."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PeriodItem(_Strict):
    """Одно место работы, стажировка или проект — как написано в резюме."""
    start: str | None = Field(default=None, description="Начало: 'ГГГГ-ММ', например '2024-05'; только год — 'ГГГГ'; нет — null")
    end: str | None = Field(default=None, description="Конец в том же формате; при 'по настоящее время' — null и is_current=true")
    is_current: bool = False
    kind: Literal["work", "contract", "internship", "project", "unknown"] = Field(
        description="work — работа по найму; contract — договор/фриланс; internship — стажировка; "
                    "project — учебный или личный проект; unknown — непонятно")
    relevant: bool | None = Field(default=None, description="Совпадают ли обязанности с описанием релевантного опыта; null, если его не спрашивали")
    quote: str = Field(description="Дословная строка резюме с датами или названием этого периода")
    context_before: str | None = Field(default=None, description="Несколько слов перед цитатой, если она может повторяться")


class StatementItem(_Strict):
    """Фраза вида «Опыт работы: 2 года 10 месяцев» или «Общий коммерческий опыт — 3 года»."""
    years: int = Field(ge=0, le=80)
    months: int = Field(default=0, ge=0, le=11)
    commercial: bool = Field(description="true, только если в фразе прямо сказано, что опыт коммерческий")
    quote: str


class AlternativeItem(_Strict):
    alternative_key: str
    status: Literal["confirmed", "refuted", "no_info"] = Field(
        description="confirmed — в тексте прямо подтверждено; refuted — в тексте прямо опровергнуто; "
                    "no_info — сведений нет (молчание резюме — это no_info, а не refuted)")
    quote: str | None = None
    context_before: str | None = None


class FormalExtraction(_Strict):
    periods: list[PeriodItem] = Field(default_factory=list)
    statement: StatementItem | None = None
    no_experience_quote: str | None = Field(default=None, description="Дословная фраза, где кандидат прямо пишет, что опыта нет")
    alternatives: list[AlternativeItem] = Field(default_factory=list)


class IndicatorItem(_Strict):
    indicator_key: str
    status: Literal["confirmed", "contradicted", "no_info"] = Field(
        description="confirmed — есть прямое свидетельство; contradicted — текст прямо опровергает; no_info — сведений нет")
    quote: str | None = None
    context_before: str | None = None


class CompetencyExtraction(_Strict):
    indicators: list[IndicatorItem] = Field(default_factory=list)
