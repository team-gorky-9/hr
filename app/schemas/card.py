"""Форматы данных, которые хранятся в JSONB и передаются между модулями.

CandidateCard — карточка кандидата (столбец candidate_cards.card).
Evidence — доказательство: дословная цитата из очищенного текста резюме и её место.

Схема повторяет черновик контракта из docs/project-context.md штаба. Отличия
(период работы разбит на start/end; id, source и raw_text вынесены в таблицы)
перечислены в hr/docs/modules/db.md и выносятся на согласование с Родионом.
"""
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.periods import PARTIAL_DATE, date_range

# Код специальности по ОКСО: «09.03.03».
OKSO_CODE = r"^\d{2}\.\d{2}\.\d{2}$"


class EducationLevel(StrEnum):
    """Закрытый словарь уровня образования. Ступень (бакалавр, магистр…) — в `degree`."""
    HIGHER = "высшее"
    INCOMPLETE_HIGHER = "неоконченное высшее"
    VOCATIONAL = "среднее профессиональное"
    SECONDARY = "среднее общее"


class EducationStatus(StrEnum):
    COMPLETED = "completed"      # окончил
    IN_PROGRESS = "in_progress"  # учится сейчас
    INCOMPLETE = "incomplete"    # не окончил, обучение прервано


class CourseKind(StrEnum):
    RETRAINING = "retraining"                        # профессиональная переподготовка
    QUALIFICATION_UPGRADE = "qualification_upgrade"  # повышение квалификации
    OTHER = "other"


class ExperienceKind(StrEnum):
    WORK = "work"
    INTERNSHIP = "internship"
    CONTRACT = "contract"   # подряд, ГПХ, фриланс по договору
    PROJECT = "project"     # учебный или личный проект


def normalize_education_level(raw: str) -> EducationLevel | None:
    """Свободная формулировка → значение словаря или None, если уровень не распознан.

    Покрывает формулировки hh.ru из архива «Кадры»: «Высшее образование (Бакалавр)»,
    «Неоконченное высшее образование», «Среднее специальное образование», «Среднее образование».
    """
    text = " ".join(raw.lower().replace("ё", "е").split())
    if not text:
        return None
    if text in {level.value for level in EducationLevel}:
        return EducationLevel(text)
    if "неоконч" in text or "незаконч" in text:
        return EducationLevel.INCOMPLETE_HIGHER
    if any(w in text for w in ("среднее специальн", "среднее профессион", "колледж", "техникум")) or text == "спо":
        return EducationLevel.VOCATIONAL
    if any(w in text for w in ("высш", "бакалавр", "магист", "специалитет", "специалист",
                               "кандидат наук", "доктор наук", "аспирант")):
        return EducationLevel.HIGHER
    if "среднее" in text or "школ" in text:
        return EducationLevel.SECONDARY
    return None


class _Strict(BaseModel):
    # Лишние поля — ошибка: опечатка в ответе модели не должна молча теряться.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Education(_Strict):
    level: EducationLevel | None = None  # закрытый словарь; не распознан → null, текст в level_raw
    level_raw: str | None = None         # формулировка уровня из резюме, как написано
    degree: str | None = None            # «бакалавр», «магистр», «специалист»
    status: EducationStatus | None = None
    course: int | None = Field(default=None, ge=1, le=6)  # курс, если учится или не окончил
    institution: str | None = None
    faculty: str | None = None
    field: str | None = None             # направление или специальность
    field_code: str | None = Field(default=None, pattern=OKSO_CODE)  # ОКСО, если указан в резюме
    year: int | None = Field(default=None, ge=1950, le=2100)

    @model_validator(mode="before")
    @classmethod
    def _normalize_level(cls, data: Any) -> Any:
        """Свободная строка уровня (модель или карточка до v1.4) не отклоняется:
        распознанная → значение словаря, нераспознанная → null. Исходник — в level_raw."""
        if not isinstance(data, dict) or not isinstance(data.get("level"), str):
            return data
        raw = data["level"].strip()
        if raw in {level.value for level in EducationLevel}:
            return data
        data = dict(data)
        normalized = normalize_education_level(raw)
        data["level"] = normalized.value if normalized else None
        if raw and not data.get("level_raw"):
            data["level_raw"] = raw
        return data


class Course(_Strict):
    """Повышение квалификации, курсы, профпереподготовка."""
    title: str
    organization: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    kind: CourseKind | None = None
    field: str | None = None          # направление переподготовки: «Юриспруденция», «ГМУ»
    completed: bool | None = None
    hours: float | None = Field(default=None, ge=0)  # если указано; порог часов нормой не задан


class Experience(_Strict):
    position: str | None = None
    organization: str | None = None  # в данных организаторов обезличено: «Организация 1»
    # «2019», «2024-05» или «2024-05-17»: точность — как в резюме, без выдумывания месяца.
    start: str | None = Field(default=None, pattern=PARTIAL_DATE)
    end: str | None = Field(default=None, pattern=PARTIAL_DATE)
    is_current: bool = False         # «по настоящее время»
    kind: ExperienceKind | None = None
    duties: list[str] = Field(default_factory=list)

    @field_validator("start", "end")
    @classmethod
    def _real_date(cls, value: str | None) -> str | None:
        if value is not None:
            date_range(value)  # «2024-02-30» → ошибка
        return value

    @model_validator(mode="after")
    def _end_after_start(self) -> "Experience":
        # С учётом точности: ошибка, только если конец точно раньше начала.
        # «2024-05» → «2024» допустимо: год окончания может включать май.
        if self.start and self.end and date_range(self.end)[1] < date_range(self.start)[0]:
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
