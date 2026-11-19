"""Фиксированные наборы значений. В базе они хранятся строкой с CHECK-ограничением.

Наборы, которые кадровик может пополнять сам (этапы отбора, причины отказа),
сюда не входят: это таблицы-справочники в selection.py.
"""
from enum import StrEnum


class DocumentKind(StrEnum):
    RESUME = "resume"                    # резюме или отклик кандидата
    JOB_DESCRIPTION = "job_description"  # должностная инструкция
    VACANCY_POSTING = "vacancy_posting"  # текст вакансии на площадке
    COMPETENCY_MATRIX = "competency_matrix"
    REGULATION = "regulation"            # положения, кодекс этики, законы
    OTHER = "other"


class Channel(StrEnum):
    """Откуда пришёл документ или где опубликована вакансия (каналы из кейса)."""
    HH_RU = "hh_ru"
    RABOTA_ROSSII = "rabota_rossii"
    CITY_SITE = "city_site"
    EMAIL = "email"
    CITIZEN_APPEAL = "citizen_appeal"    # обращение гражданина по 59-ФЗ
    INTERNSHIP = "internship"            # студенты-практиканты
    INTERNAL = "internal"                # внутренние документы администрации
    OTHER = "other"


class FileFormat(StrEnum):
    HH_TXT = "hh_txt"
    HH_DOCX = "hh_docx"
    DOCX = "docx"
    PDF = "pdf"
    TXT = "txt"
    OTHER = "other"


class UserRole(StrEnum):
    HR = "hr"                  # кадровый специалист
    DEPARTMENT = "department"  # руководитель или сотрудник департамента-заказчика
    ADMIN = "admin"


class AuditAction(StrEnum):
    VIEW_PII = "view_pii"
    LLM_CALL = "llm_call"
    STAGE_CHANGE = "stage_change"
    EXPORT = "export"
    OTHER = "other"


class RequirementStatus(StrEnum):
    DRAFT = "draft"        # предложено (моделью или человеком), не утверждено
    APPROVED = "approved"  # утверждено кадровиком, по нему оцениваем
    ARCHIVED = "archived"


class CompetencyRank(StrEnum):
    """Ранги из матрицы заказчика: КР, БР, СР."""
    KEY = "key"
    BASIC = "basic"
    SPECIAL = "special"


class FormalRequirementKind(StrEnum):
    """Юридически значимые требования из должностной инструкции."""
    EDUCATION_LEVEL = "education_level"
    EDUCATION_FIELD = "education_field"
    EXPERIENCE = "experience"
    KNOWLEDGE = "knowledge"  # знание законов и актов, проверяется на интервью
    OTHER = "other"


class CheckResult(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"  # в резюме нет сведений: это повод уточнить, а не отказать


class VacancyStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ApplicationSource(StrEnum):
    RESPONSE = "response"  # отклик из файла площадки
    HISTORY = "history"    # строка «История общения с кандидатом» в резюме
    MANUAL = "manual"      # кадровик добавил кандидата на вакансию сам


class RejectionSide(StrEnum):
    EMPLOYER = "employer"
    CANDIDATE = "candidate"
    OTHER = "other"


class InterviewKind(StrEnum):
    PHONE = "phone"
    DEPARTMENT = "department"


class InterviewResult(StrEnum):
    PENDING = "pending"
    CONTINUE = "continue"
    STOP = "stop"
    NO_ANSWER = "no_answer"


class QuestionAuthor(StrEnum):
    MODEL = "model"
    HUMAN = "human"


class FeedbackOutcome(StrEnum):
    PENDING = "pending"
    FIT = "fit"
    NOT_FIT = "not_fit"


class ReserveStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    HIRED = "hired"


class ChunkKind(StrEnum):
    """Какая часть резюме превращена в вектор."""
    EXPERIENCE = "experience"
    ABOUT = "about"
    SKILLS = "skills"
    EDUCATION = "education"
    COVER_LETTER = "cover_letter"
    FULL = "full"
