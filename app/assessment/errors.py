"""Ошибки оценивания (контракт assessment.md, п. 3). Во всех случаях оценка не создаётся."""
from app.ai.errors import LLMInvalidResponseError, LLMUnavailableError

__all__ = ["AssessmentDomainError", "LLMInvalidResponseError", "LLMUnavailableError", "RuleUnsupportedError"]


class AssessmentDomainError(Exception):
    """Оценивать нельзя: профиль не тот или не в том статусе, нет текста, устарела карточка."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class RuleUnsupportedError(Exception):
    """Правило профиля в неизвестном формате: оценка по профилю не создаётся вовсе."""
    reason = "rule_unsupported"
