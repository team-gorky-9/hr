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
    """Ранги из матрицы заказчика: КР, БР, СР. Справочно: есть только там, где есть матрица."""
    KEY = "key"
    BASIC = "basic"
    SPECIAL = "special"


class VerificationMethod(StrEnum):
    """Где можно подтвердить требование. Единый формат профиля для всех должностей."""
    RESUME = "resume"        # по тексту резюме
    DOCUMENTS = "documents"  # по документам: диплом, трудовая книжка
    INTERVIEW = "interview"  # только на интервью: личные качества, знание законов
    TEST = "test"            # практическое задание


class CheckStage(StrEnum):
    """На каком этапе отбора проверяется строка профиля [v1.5].

    `screening` — первичный отбор по резюме: строка входит в итог formal_result и в счётчики.
    Требование «по документам» тоже проверяется здесь предварительно (basis = resume).
    `interview` — только на интервью: в итог разбора резюме не входит, уходит в вопросы.
    """
    SCREENING = "screening"
    INTERVIEW = "interview"


class RowOrigin(StrEnum):
    """Откуда строка профиля требований."""
    SOURCE = "source"  # перенесена из документа: есть документ, адрес и цитата
    TEAM = "team"      # сформулирована командой (группировка, интерпретация): есть обоснование


class SourceRole(StrEnum):
    """Роль документа в профиле требований."""
    JOB_DESCRIPTION = "job_description"
    COMPETENCY_MATRIX = "competency_matrix"
    VACANCY_POSTING = "vacancy_posting"
    REGULATION = "regulation"
    OTHER = "other"


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


class InterviewQuestionKind(StrEnum):
    """Вид вопроса гайда [v1.9]."""
    CORE = "core"                    # общее ядро должности: одинаково для всех кандидатов версии профиля
    CLARIFICATION = "clarification"  # уточнение по пробелу именно этого кандидата


class AnswerSource(StrEnum):
    """Откуда ответ кандидата [v1.9]."""
    PHONE = "phone"
    IN_PERSON = "in_person"
    WRITTEN = "written"
    UNKNOWN = "unknown"  # только перенос старых answer_notes миграцией 0007; через API не передаётся


class RubricStatus(StrEnum):
    """Статус вопроса рубрики ядра [v1.9]."""
    DRAFT = "draft"
    APPROVED = "approved"


class FeedbackOutcome(StrEnum):
    PENDING = "pending"
    FIT = "fit"
    NOT_FIT = "not_fit"


class ReserveStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"  # основание отозвано кадровиком
    HIRED = "hired"
    EXPIRED = "expired"      # срок резерва истёк; закрывается при новом периоде на ту же цель [v1.8]


class ChunkKind(StrEnum):
    """Какая часть резюме превращена в вектор."""
    EXPERIENCE = "experience"
    ABOUT = "about"
    SKILLS = "skills"
    EDUCATION = "education"
    COVER_LETTER = "cover_letter"
    FULL = "full"
