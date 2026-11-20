"""Заглушка модели для офлайн-тестов: ответы задаёт тест, сеть не нужна."""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.ai.client import CallInfo
from app.ai.errors import LLMInvalidResponseError, LLMUnavailableError

# Ответчик получает (роль, имя схемы, system, user) и возвращает dict, Pydantic-объект или исключение.
Responder = Callable[[str, str, str, str], Any]


@dataclass
class FakeLLMClient:
    responder: Responder
    calls: list[CallInfo] = field(default_factory=list)
    # Последние запросы целиком — тесты проверяют, что в модель ушёл только очищенный текст.
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def model_name(self, role: str) -> str:
        return f"fake-{role}"

    def complete_structured(self, system_prompt, user_prompt, response_model, *, model_role, prompt_version=""):
        info = CallInfo(role=model_role, model=self.model_name(model_role), prompt_version=prompt_version,
                        schema=response_model.__name__, mode="fake", attempts=1)
        self.calls.append(info)
        self.prompts.append((system_prompt, user_prompt))
        answer = self.responder(model_role, response_model.__name__, system_prompt, user_prompt)
        if isinstance(answer, BaseException):
            info.status = "unavailable" if isinstance(answer, LLMUnavailableError) else "invalid_response"
            info.error = str(answer)
            raise answer
        try:
            return answer if isinstance(answer, response_model) else response_model.model_validate(answer)
        except ValidationError as error:
            info.status, info.error = "invalid_response", "схема"
            raise LLMInvalidResponseError(f"ответ не прошёл схему {response_model.__name__}") from error
