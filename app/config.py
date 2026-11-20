"""Настройки приложения из переменных окружения и файла .env."""
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.search.encoder import DEFAULT_THRESHOLD


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Значение по умолчанию совпадает с docker-compose.yml и годится только для разработки.
    database_url: str = "postgresql+psycopg://hr:hr@localhost:5432/hr"

    # С каких адресов браузер может обращаться к API (CORS). По умолчанию — dev-сервер Vite.
    # В .env задаётся JSON-списком: CORS_ORIGINS=["http://localhost:5173"]
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    hr_search_work_token: SecretStr | None = None
    hr_search_semantic_enabled: bool = False
    hr_search_dense_threshold: float = Field(default=DEFAULT_THRESHOLD, ge=0, le=1)

    # Срок ответа департамента на переданный отклик (workflow-01): 10 рабочих дней,
    # предупреждение «скоро срок» с 7-го рабочего дня (по производственному календарю РФ).
    handoff_feedback_deadline_business_days: int = Field(default=10, ge=1, le=90)
    handoff_feedback_reminder_business_day: int = Field(default=7, ge=1, le=90)


settings = Settings()
