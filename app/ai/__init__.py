"""Слой доступа к языковой модели. Сервисы зависят только от интерфейса LLMClient."""
from app.ai.client import CallInfo, LLMClient, ModelRole, build_client
from app.ai.config import LLMConfig
from app.ai.errors import LLMError, LLMInvalidResponseError, LLMUnavailableError
from app.ai.fake import FakeLLMClient

__all__ = [
    "CallInfo",
    "FakeLLMClient",
    "LLMClient",
    "LLMConfig",
    "LLMError",
    "LLMInvalidResponseError",
    "LLMUnavailableError",
    "ModelRole",
    "build_client",
]
