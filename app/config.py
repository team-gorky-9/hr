"""Настройки приложения из переменных окружения и файла .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Значение по умолчанию совпадает с docker-compose.yml и годится только для разработки.
    database_url: str = "postgresql+psycopg://hr:hr@localhost:5432/hr"

    # С каких адресов браузер может обращаться к API (CORS). По умолчанию — dev-сервер Vite.
    # В .env задаётся JSON-списком: CORS_ORIGINS=["http://localhost:5173"]
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
