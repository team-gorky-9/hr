"""Форматы данных, которые хранятся в JSONB и передаются между модулями.

CandidateCard — карточка кандидата (столбец candidate_cards.card).
Evidence — доказательство: дословная цитата из очищенного текста резюме и её место.

Схема повторяет черновик контракта из docs/project-context.md штаба. Отличия
(период работы разбит на start/end; id, source и raw_text вынесены в таблицы)
перечислены в hr/docs/modules/db.md и выносятся на согласование с Родионом.
"""
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Месяц в формате «2024-05».
YEAR_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


class _Strict(BaseModel):
    # Лишние поля — ошибка: опечатка в ответе модели не должна молча теряться.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Education(_Strict):
    level: str | None = None        # «высшее», «среднее профессиональное»
    degree: str | None = None       # «бакалавр», «магистр», «специалист»
    institution: str | None = None
    faculty: str | None = None
    field: str | None = None        # направление или специальность
    year: int | None = Field(default=None, ge=1950, le=2100)


class Course(_Strict):
    """Повышение квалификации, курсы, профпереподготовка."""
    title: str
    organization: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)


class Experience(_Strict):
    position: str | None = None
    organization: str | None = None  # в данных организаторов обезличено: «Организация 1»
    start: str | None = Field(default=None, pattern=YEAR_MONTH)
    end: str | None = Field(default=None, pattern=YEAR_MONTH)
    is_current: bool = False         # «по настоящее время»
    duties: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_after_start(self) -> "Experience":
        if self.start and self.end and self.end < self.start:
            raise ValueError(f"конец периода {self.end} раньше начала {self.start}")
        if self.is_current and self.end:
            raise ValueError("у текущего места работы не может быть даты окончания")
        return self


class Skill(_Strict):
    name: str = Field(min_length=1)
    level: str | None = None


class Language(_Strict):
    name: str = Field(min_length=1)
    level: str | None = None  # «Родной», «B1 — Средний»


class CandidateCard(_Strict):
    """Единая карточка кандидата, в которую приводится резюме любого формата."""
    headline: str | None = None                       # заголовок резюме
    applied_to: list[str] = Field(default_factory=list)  # названия должностей из отклика
    education: list[Education] = Field(default_factory=list)
    courses: list[Course] = Field(default_factory=list)
    experience_years: float | None = Field(default=None, ge=0, le=80)
    experience: list[Experience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    about: str | None = None
    cover_letter: str | None = None
    # Чего не хватает для оценки: «сопроводительное письмо», «направление подготовки».
    missing: list[str] = Field(default_factory=list)
    # Персональные данные убраны из карточки и текста, переданного модели.
    pii_hidden: bool = True


class Evidence(_Strict):
    """Цитата-доказательство. start/end — позиция в candidate_texts.text
    (как срез Python: text[start:end] == quote)."""
    candidate_text_id: uuid.UUID
    quote: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def _length_matches(self) -> "Evidence":
        if self.end - self.start != len(self.quote):
            raise ValueError("длина цитаты не совпадает с её границами start/end")
        return self


def evidence_matches(text: str, evidence: Evidence) -> bool:
    """Цитата стоит в тексте ровно на указанном месте."""
    return text[evidence.start:evidence.end] == evidence.quote
