"""Формулировки вопросов — модель; какие вопросы и к чему они относятся — код (interview.md, §3)."""
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from app.ai.client import LLMClient
from app.interview.gaps import Gap

GUIDE_PROMPT_VERSION = "guide-v2"
CORE_CHUNK = 12  # строк ядра на один вызов

GUIDE_SYSTEM = (
    "Ты помогаешь кадровику муниципальной администрации подготовить телефонный разговор с кандидатом. "
    "Решение принимает человек. Тебе передают пробелы — сведения, которых не хватило в резюме, — с "
    "критериями из профиля должности. Для каждого пробела сформулируй ОДИН вопрос и критерий ответа. "
    "Правила: (1) спрашивай о фактах и рабочих ситуациях, не о личности и не о частной жизни; "
    "(2) вопрос нейтральный, без подсказки правильного ответа и без упоминания оценки или баллов; "
    "(3) вопрос — одно-два предложения, не длиннее 300 символов, на русском, на «вы»; "
    "(4) good_answer — кратко, какие факты должны прозвучать, чтобы пробел закрылся (по критерию met): "
    "описание для кадровика, а не реплика от лица кандидата, например «назван уровень, вуз и год окончания»; "
    "insufficient_answer — какой ответ оставляет пробел открытым (по критерию unknown), тоже описанием; "
    "(5) если в пробеле несколько навыков, спроси о них одним вопросом через пример рабочей ситуации, "
    "не перечисляя все дословно; "
    "(6) верни ровно по одному элементу на каждый переданный gap_ref_id и не придумывай новых."
)

CORE_SYSTEM = (
    "Ты помогаешь составить единые вопросы собеседования по должности — одинаковые для всех кандидатов. "
    "Для каждой строки профиля сформулируй один вопрос о рабочей ситуации или знании и критерий ответа "
    "по её acceptance. Не оценивай личность, не задавай вопросов о частной жизни, не подсказывай ответ. "
    "Вопрос не длиннее 300 символов, на «вы». Верни ровно по одному элементу на каждый row_key."
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QuestionItem(_Strict):
    ref: str = Field(description="gap_ref_id пробела или row_key строки профиля — ровно как передан")
    question: str = Field(min_length=5, max_length=300)
    good_answer: str = Field(min_length=3, max_length=400)
    insufficient_answer: str = Field(min_length=3, max_length=400)


class QuestionSet(_Strict):
    items: list[QuestionItem] = Field(default_factory=list)


def _keyed(expected: set[str]) -> type[QuestionSet]:
    """Ключи ответа — только запрошенные и по одному разу. В тексте ошибки — только наши ключи
    (сообщение уходит в журнал вызовов): так модель один раз исправляет ответ, затем — ошибка."""
    allowed = ", ".join(sorted(expected))

    def check(self):
        seen: set[str] = set()
        for number, item in enumerate(self.items, 1):
            if item.ref not in expected:
                raise ValueError(f"элемент {number}: ref не из запрошенных; допустимы только: {allowed}")
            if item.ref in seen:
                raise ValueError(f"ref = {item.ref!r} повторяется; верни по одному элементу на ключ")
            seen.add(item.ref)
        return self

    return create_model("QuestionSet", __base__=QuestionSet,
                        __validators__={"_check_refs": model_validator(mode="after")(check)})


def generate_clarifications(gaps: list[Gap], llm: LLMClient) -> tuple[dict[str, QuestionItem], list[str]]:
    """Вопросы по пробелам. Пустой список — ноль вызовов модели. Текст резюме не передаётся:
    достаточно заголовков пробелов, критериев и уже найденных цитат."""
    if not gaps:
        return {}, []
    payload = [{"gap_ref_id": g.gap_ref_id, "title": g.title,
                "criteria": [{k: v for k, v in a.items() if k in ("text", "met", "unknown", "limit")}
                             for a in g.acceptance],
                "known_quotes": g.known_quotes} for g in gaps]
    answer = llm.complete_structured(
        GUIDE_SYSTEM, "Пробелы:\n" + json.dumps(payload, ensure_ascii=False, indent=1),
        _keyed({g.gap_ref_id for g in gaps}), model_role="assess", prompt_version=GUIDE_PROMPT_VERSION,
    )
    items = {i.ref: i for i in answer.items}
    missing = [g.gap_ref_id for g in gaps if g.gap_ref_id not in items]
    return items, missing


def core_rows(profile) -> list[dict[str, Any]]:
    """Строки профиля этапа interview — источник общего ядра (одинакового для всех кандидатов)."""
    rows = []
    for requirement in profile.formal_requirements:
        if _stage(requirement) == "interview":
            rows.append({"row_key": requirement.key, "text": requirement.description,
                         "acceptance": requirement.acceptance or {}, "order": (0, requirement.sort_order, 0),
                         "source": {"type": "profile_row", "key": requirement.key,
                                    "requirement_id": str(requirement.id)}})
    for competency in profile.competencies:
        for indicator in competency.indicators:
            if _stage(indicator) == "interview" and not indicator.excluded_from_scoring:
                rows.append({"row_key": indicator.key, "text": f"{competency.name}: {indicator.text}",
                             "acceptance": indicator.acceptance or {},
                             "order": (1, competency.sort_order, indicator.sort_order),
                             "source": {"type": "profile_row", "key": indicator.key,
                                        "competency_id": str(competency.id)}})
    return sorted(rows, key=lambda r: r["order"])


def generate_core(rows: list[dict[str, Any]], llm: LLMClient) -> tuple[dict[str, QuestionItem], int]:
    """Вопросы ядра — один раз на версию профиля (хранит вызывающий). Пачками по CORE_CHUNK строк."""
    items: dict[str, QuestionItem] = {}
    calls = 0
    for start in range(0, len(rows), CORE_CHUNK):
        chunk = rows[start:start + CORE_CHUNK]
        payload = [{"row_key": r["row_key"], "text": r["text"],
                    "criteria": {k: v for k, v in r["acceptance"].items() if k in ("met", "unknown", "limit")}}
                   for r in chunk]
        answer = llm.complete_structured(
            CORE_SYSTEM, "Строки профиля:\n" + json.dumps(payload, ensure_ascii=False, indent=1),
            _keyed({r["row_key"] for r in chunk}), model_role="assess", prompt_version=GUIDE_PROMPT_VERSION,
        )
        calls += 1
        items.update({i.ref: i for i in answer.items})
    return items, calls


def _stage(row) -> str:
    value = getattr(row, "check_stage", None)
    return getattr(value, "value", value)
