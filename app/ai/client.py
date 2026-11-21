"""Интерфейс модели и клиент OpenAI-совместимого API (YandexGPT).

Сервисы вызывают только LLMClient.complete_structured и получают проверенный Pydantic-объект.
Клиент сам:
- просит у провайдера ответ по JSON-схеме (response_format=json_schema), а если провайдер
  такой формат не принимает — переходит на «JSON по инструкции» и дальше работает так;
- повторяет запрос при сетевом сбое, таймауте, 429 и 5xx;
- при невалидном ответе один раз просит модель исправить JSON, показав ошибку;
- ведёт журнал вызовов (calls) без текста запроса и без ключей — его пишет в audit_log сервис.
"""
import copy
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.config import LLMConfig
from app.ai.errors import LLMInvalidResponseError, LLMUnavailableError

ModelRole = Literal["extract", "assess"]
T = TypeVar("T", bound=BaseModel)


@dataclass
class CallInfo:
    """Метаданные одного обращения к модели: то, что можно хранить в журнале."""
    role: str
    model: str
    prompt_version: str
    schema: str
    status: Literal["ok", "invalid_response", "unavailable"] = "ok"
    mode: str = ""
    attempts: int = 0
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None

    def as_audit(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class LLMClient(Protocol):
    calls: list[CallInfo]

    def model_name(self, role: ModelRole) -> str: ...

    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        *,
        model_role: ModelRole,
        prompt_version: str = "",
    ) -> T: ...


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON-схема без $ref: часть провайдеров ссылки внутри схемы не понимает."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                return resolve(copy.deepcopy(defs[name]))
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(content: str) -> str:
    """Достать JSON-объект из ответа: без обрамления ``` и текста вокруг."""
    text = _FENCE.sub("", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return text
    return text[start : end + 1]


@dataclass
class OpenAICompatClient:
    """Клиент YandexGPT через OpenAI-совместимый API (api_key + project = каталог)."""
    config: LLMConfig
    calls: list[CallInfo] = field(default_factory=list)
    _mode: str = field(init=False, default="json_schema")
    _sdk: Any = field(init=False, default=None)

    def __post_init__(self) -> None:
        import openai  # импорт здесь: офлайн-тестам SDK не нужен

        if self.config.llm_structured_mode == "prompt_json":
            self._mode = "prompt_json"
        key = self.config.api_key()
        if not key:
            raise LLMUnavailableError("не задан ключ выбранного провайдера LLM")
        self._openai = openai
        self._sdk = openai.OpenAI(
            api_key=key,
            base_url=self.config.llm_base_url,
            project=self.config.yandex_folder_id if self.config.llm_provider == "yandexgpt" else None,
            timeout=self.config.llm_timeout_sec,
            max_retries=0,  # повторы считаем сами, чтобы видеть их в журнале
        )

    def model_name(self, role: ModelRole) -> str:
        return self.config.model_for(role)

    def _detail(self, error) -> str:
        """Текст ошибки провайдера (без ключа, не длиннее 300 символов) — чтобы понять причину 401/403/404."""
        body = getattr(error, "body", None)
        text = ""
        if isinstance(body, dict):
            inner = body.get("error", body)
            text = inner.get("message") if isinstance(inner, dict) else str(inner)
        text = str(text or getattr(error, "message", "") or "")
        key = self.config.api_key() or ""
        if key:
            text = text.replace(key, "***")
        text = " ".join(text.split())[:300]
        return f" — {text}" if text else ""

    def complete_structured(self, system_prompt, user_prompt, response_model, *, model_role, prompt_version=""):
        info = CallInfo(role=model_role, model=self.model_name(model_role), prompt_version=prompt_version,
                        schema=response_model.__name__)
        self.calls.append(info)
        started = time.monotonic()
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        repairs_left = 1
        transient_left = self.config.llm_max_retries
        try:
            while True:
                info.attempts += 1
                info.mode = self._mode
                try:
                    content, usage = self._request(info.model, messages, response_model)
                except self._openai.BadRequestError as error:
                    if self._mode == "json_schema" and self.config.llm_structured_mode == "auto":
                        # Провайдер не принял response_format — дальше просим JSON инструкцией.
                        self._mode = "prompt_json"
                        continue
                    raise LLMUnavailableError(f"провайдер отклонил запрос: HTTP {error.status_code}{self._detail(error)}") from None
                except (self._openai.APITimeoutError, self._openai.APIConnectionError,
                        self._openai.RateLimitError, self._openai.InternalServerError) as error:
                    if transient_left > 0:
                        transient_left -= 1
                        time.sleep(1.0)
                        continue
                    raise LLMUnavailableError(f"модель недоступна: {type(error).__name__}{self._detail(error)}") from None
                except self._openai.APIStatusError as error:
                    raise LLMUnavailableError(f"модель недоступна: HTTP {error.status_code}{self._detail(error)}") from None
                if usage is not None:
                    info.prompt_tokens = getattr(usage, "prompt_tokens", None)
                    info.completion_tokens = getattr(usage, "completion_tokens", None)
                try:
                    return response_model.model_validate_json(extract_json(content))
                except ValidationError as error:
                    if repairs_left == 0:
                        raise LLMInvalidResponseError(
                            f"ответ модели не прошёл схему {response_model.__name__}: {error.error_count()} ошибок; "
                            f"первая — {_first_problem(error, response_model)}"
                        ) from None
                    repairs_left -= 1
                    messages += [
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": _repair_request(error)},
                    ]
        except LLMUnavailableError as error:
            info.status, info.error = "unavailable", str(error)
            raise
        except LLMInvalidResponseError as error:
            info.status, info.error = "invalid_response", str(error)
            raise
        finally:
            info.latency_ms = int((time.monotonic() - started) * 1000)

    def _request(self, model: str, messages: list[dict[str, str]], response_model: type[BaseModel]) -> tuple[str, Any]:
        schema = inline_schema(response_model)
        extra: dict[str, Any] = {}
        if self._mode == "json_schema":
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": response_model.__name__, "schema": schema},
            }
            sent = messages
        else:
            instruction = (
                "\n\nОтветь ТОЛЬКО одним JSON-объектом без пояснений и без ```, строго по этой JSON-схеме:\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            sent = [{"role": "system", "content": messages[0]["content"] + instruction}, *messages[1:]]
        response = self._sdk.chat.completions.create(
            model=model,
            messages=sent,
            temperature=self.config.llm_temperature,
            max_tokens=self.config.llm_max_tokens,
            **extra,
        )
        return response.choices[0].message.content or "", getattr(response, "usage", None)


def _first_problem(error: ValidationError, response_model: type[BaseModel]) -> str:
    """Диагностика для журнала: msg и неизвестные имена полей могут содержать резюме."""
    field_names: set[str] = set()

    def collect_fields(schema):
        if isinstance(schema, dict):
            field_names.update(schema.get("properties", {}))
            for value in schema.values():
                collect_fields(value)
        elif isinstance(schema, list):
            for value in schema:
                collect_fields(value)

    collect_fields(response_model.model_json_schema())
    item = error.errors(include_input=False, include_context=False)[0]
    path = ".".join(str(p) if isinstance(p, int) or p in field_names else "<extra_field>"
                    for p in item["loc"]) or "ответ"
    # Не копируем произвольный текст пользовательского ValueError даже без input.
    return f"{path}: {item['type']}"[:200]


def _repair_request(error: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(str(p) for p in item['loc'])}: {item['msg']}" for item in error.errors()[:5]
    )
    return f"Твой ответ не прошёл проверку схемы ({problems}). Верни исправленный JSON-объект целиком."


def build_client(config: LLMConfig | None = None, *, fake: Callable[..., Any] | None = None) -> LLMClient:
    """Клиент по настройкам. provider=fake без ответчика — ошибка: заглушка нужна только в тестах."""
    config = config or LLMConfig()
    if config.llm_provider == "fake":
        from app.ai.fake import FakeLLMClient

        if fake is None:
            raise LLMUnavailableError("LLM_PROVIDER=fake годится только для тестов")
        return FakeLLMClient(fake)
    return OpenAICompatClient(config)
