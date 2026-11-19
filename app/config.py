"""Настройки приложения из переменных окружения и файла .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Значение по умолчанию совпадает с docker-compose.yml и годится только для разработки.
    database_url: str = "postgresql+psycopg://hr:hr@localhost:5432/hr"


settings = Settings()
