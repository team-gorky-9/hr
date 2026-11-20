"""Что модель возвращает при оценке. Статусы и цитаты — от модели, итог и числа — от кода."""
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    field_validator,
    model_validator,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# Модель без json_schema иногда отвечает статусом из смежного словаря. Однозначные синонимы
# приводим к своим значениям; всё неоднозначное остаётся ошибкой схемы и уходит на исправление.
_NO_INFO = {"no_info", "unknown", "none", "null", "no info", "not_found", "нет данных", "не указано"}
_CONFIRMED = {"confirmed", "met", "yes", "true", "подтверждено"}
_NEGATIVE = {"refuted", "contradicted", "not_met", "no", "false", "опровергнуто"}


def _status(value, negative: str):
    if value is None:
        return "no_info"
    if isinstance(value, bool):
        return "confirmed" if value else negative
    text = str(value).strip().lower()
    if text in _NO_INFO:
        return "no_info"
    if text in _CONFIRMED:
        return "confirmed"
    if text in _NEGATIVE:
        return negative
    return value


class PeriodItem(_Strict):
    """Одно место работы, стажировка или проект — как написано в резюме."""
    start: str | None = Field(default=None, description="Начало: 'ГГГГ-ММ-ДД', 'ГГГГ-ММ' или 'ГГГГ', с исходной точностью; нет — null")
    end: str | None = Field(default=None, description="Конец в том же формате; при 'по настоящее время' — null и is_current=true")
    is_current: bool = False
    kind: Literal["work", "contract", "internship", "project", "unknown"] = Field(
        description="work — работа по найму в организации: место работы, должность, «на работе в компании», "
                    "«работал в …», «сотрудник …» — даже без дат и названия компании; contract — договор, ГПХ, "
                    "фриланс; internship — стажировка или практика; project — учебный, личный или pet-проект и "
                    "«в проекте …» без указания, что это работа; unknown — только если по тексту нельзя понять, "
                    "работа это или проект")
    relevant: bool | None = Field(default=None, description="Совпадают ли обязанности с описанием релевантного опыта; null, если его не спрашивали")
    quote: str = Field(description="Дословная строка резюме с датами или названием этого периода")
    context_before: str | None = Field(default=None, description="Несколько слов перед цитатой, если она может повторяться")


class StatementItem(_Strict):
    """Фраза вида «Опыт работы: 2 года 10 месяцев» или «Общий коммерческий опыт — 3 года»."""
    years: int = Field(ge=0, le=80)
    months: int = Field(default=0, ge=0, le=11)
    commercial: bool = Field(description="true, только если в фразе прямо сказано, что опыт коммерческий")
    quote: str


class QuoteItem(_Strict):
    quote: str
    context_before: str | None = None


class AlternativeItem(_Strict):
    quotes: list[QuoteItem] = Field(default_factory=list)
    alternative_key: str
    status: Literal["confirmed", "refuted", "no_info"] = Field(
        description="confirmed — в тексте прямо подтверждено; refuted — в тексте прямо опровергнуто; "
                    "no_info — сведений нет (молчание резюме — это no_info, а не refuted)")
    quote: str | None = None
    context_before: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _synonyms(cls, value):
        return _status(value, "refuted")


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

    @field_validator("status", mode="before")
    @classmethod
    def _synonyms(cls, value):
        return _status(value, "contradicted")


class CompetencyExtraction(_Strict):
    indicators: list[IndicatorItem] = Field(default_factory=list)


def _keyed(base: type[BaseModel], field: str, attr: str, expected: set[str]) -> type[BaseModel]:
    """Та же схема, но ключи ответа сверяются с запрошенными.

    Ошибка ключа — это ValueError при разборе ответа, поэтому клиент один раз просит модель
    исправить JSON и называет допустимые ключи; только после неудачного исправления —
    LLMInvalidResponseError (контракт оценки, п. 7). Точный повтор одного ключа с тем же
    статусом склеивается (остаётся вариант с цитатой); один ключ с разными статусами —
    ошибка. Если ключей не запрашивали (например, только стаж), лишние элементы отбрасываются.
    """
    allowed = ", ".join(sorted(expected))

    def check(self):
        kept: dict[str, object] = {}
        for item in getattr(self, field):
            key = getattr(item, attr)
            if key not in expected:
                if not expected:
                    continue
                raise ValueError(f"{attr} = {key!r} не запрашивался; допустимы только: {allowed}")
            first = kept.get(key)
            if first is None:
                kept[key] = item
            elif first.status != item.status:
                raise ValueError(f"{attr} = {key!r} указан дважды с разными статусами; оставь один элемент")
            elif not first.quote and item.quote:
                kept[key] = item
        object.__setattr__(self, field, list(kept.values()))
        return self

    return create_model(base.__name__, __base__=base,
                        __validators__={"_check_keys": model_validator(mode="after")(check)})


def keyed_formal(alternative_keys: set[str]) -> type[FormalExtraction]:
    return _keyed(FormalExtraction, "alternatives", "alternative_key", alternative_keys)


def keyed_competency(indicator_keys: set[str]) -> type[CompetencyExtraction]:
    return _keyed(CompetencyExtraction, "indicators", "indicator_key", indicator_keys)
