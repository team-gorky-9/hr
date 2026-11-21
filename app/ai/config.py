"""Настройки модели из .env (контракт assessment.md, п. 2). В коде сервисов модель не зашита."""
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["yandexgpt", "openai_compat", "fake"] = "yandexgpt"
    llm_base_url: str = "https://llm.api.cloud.yandex.net/v1"
    yandex_api_key: SecretStr | None = None
    # Only explicit openai_compat overrides use this key. Production defaults remain Yandex.
    llm_api_key: SecretStr | None = None
    yandex_folder_id: str | None = None
    # {folder} подставляется из YANDEX_FOLDER_ID.
    llm_extract_model: str = "gpt://{folder}/yandexgpt-lite/latest"
    llm_assess_model: str = "gpt://{folder}/yandexgpt/latest"
    llm_temperature: float = 0.0
    llm_timeout_sec: float = 30.0
    llm_max_retries: int = 1
    # Максимум токенов ответа: оценка компетенции с цитатами укладывается в 2000.
    llm_max_tokens: int = 2000
    # auto: сначала response_format=json_schema, при отказе провайдера — JSON по инструкции.
    llm_structured_mode: Literal["auto", "json_schema", "prompt_json"] = "auto"

    def api_key(self) -> str | None:
        secret = self.llm_api_key if self.llm_provider == "openai_compat" else self.yandex_api_key
        if secret is None and self.llm_provider == "openai_compat":
            secret = self.yandex_api_key  # Existing compatible configurations remain valid.
        return secret.get_secret_value() if secret else None

    def model_for(self, role: str) -> str:
        template = self.llm_extract_model if role == "extract" else self.llm_assess_model
        return template.replace("{folder}", self.yandex_folder_id or "")
