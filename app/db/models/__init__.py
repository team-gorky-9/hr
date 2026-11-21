"""Все модели базы. Импорт этого пакета регистрирует таблицы в Base.metadata
(его использует Alembic для автогенерации миграций)."""
from app.db.models.assessments import Assessment, CompetencyScore, FormalCheck
from app.db.models.candidates import Candidate, CandidateCard, CandidatePii, CandidateSkill, CandidateText
from app.db.models.positions import (
    Competency,
    CompetencyIndicator,
    FormalRequirement,
    Position,
    ProfileSource,
    RequirementProfile,
    Vacancy,
)
from app.db.models.management import AnnualReportRelease
from app.db.models.matching import MatchingSuggestion
from app.db.models.search import Embedding
from app.db.models.selection import (
    Application,
    DepartmentFeedback,
    HandoffAttempt,
    HandoffDeadlineExtension,
    Interview,
    InterviewAnswer,
    InterviewGuide,
    InterviewQuestion,
    InterviewRubricQuestion,
    ProductionCalendarDay,
    RejectionReason,
    ReserveEntry,
    SelectionStage,
    StageEvent,
)
from app.db.models.sources import SourceDocument
from app.db.models.postings import ApplicationPostingSource
from app.db.models.users import AuditLog, User

__all__ = [
    "AnnualReportRelease",
    "MatchingSuggestion",
    "Application",
    "ApplicationPostingSource",
    "Assessment",
    "AuditLog",
    "Candidate",
    "CandidateCard",
    "CandidatePii",
    "CandidateSkill",
    "CandidateText",
    "Competency",
    "CompetencyIndicator",
    "CompetencyScore",
    "DepartmentFeedback",
    "Embedding",
    "FormalCheck",
    "FormalRequirement",
    "HandoffAttempt",
    "HandoffDeadlineExtension",
    "Interview",
    "InterviewAnswer",
    "InterviewGuide",
    "InterviewQuestion",
    "InterviewRubricQuestion",
    "Position",
    "ProductionCalendarDay",
    "ProfileSource",
    "RejectionReason",
    "RequirementProfile",
    "ReserveEntry",
    "SelectionStage",
    "SourceDocument",
    "StageEvent",
    "User",
    "Vacancy",
]
