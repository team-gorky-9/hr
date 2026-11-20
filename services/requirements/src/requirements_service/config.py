"""Конфигурация сервиса требований к должности."""
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES_DIR = SERVICE_ROOT / "fixtures" / "wave-1"


class Settings(BaseSettings):
    """Настройки приложения, БД, брокера, файлового хранилища и аутентификации."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "requirements"
    port: int = 8102

    database_url: str = "postgresql+psycopg://requirements:requirements@localhost:5432/requirements"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/%2F"

    auth_mode: Literal["fixture", "workforce"] = "fixture"
    workforce_base_url: str = "http://localhost:8101"
    workforce_timeout_sec: float = 5.0

    fixture_actors_path: Path = Field(default=DEFAULT_FIXTURES_DIR / "actors.json")
    fixture_org_path: Path = Field(default=DEFAULT_FIXTURES_DIR / "organization.json")

    file_root: Path = Field(default=SERVICE_ROOT / "data" / "files")
    file_max_bytes: int = 20 * 1024 * 1024  # 20 MiB

    outbox_exchange: str = "w1.requirements"
    outbox_poll_interval_sec: float = 0.0
    outbox_max_attempts: int = 5
    outbox_base_backoff_sec: float = 2.0

    seed_on_startup: bool = True
    seed_organization_id: str = "00000000-0000-4000-8000-000000000001"


def load_settings() -> Settings:
    """Создать экземпляр настроек из окружения."""
    return Settings()
