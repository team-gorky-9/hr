"""Тесты базы работают на настоящей PostgreSQL с pgvector (TEST_DATABASE_URL).

Схема создаётся той же миграцией Alembic, что и на стенде, поэтому тесты проверяют
и миграцию. Каждый тест выполняется в транзакции, которая откатывается в конце.
"""
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, make_url
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.seed import seed_all

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _TestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")
    test_database_url: str | None = None


def alembic_config(url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _TestSettings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL не задан: тесты базы пропущены (см. README, раздел «Тесты»)")
    # Тесты удаляют всю схему базы. Защита от случайного запуска на рабочей базе.
    if not (make_url(url).database or "").endswith("_test"):
        pytest.exit(f"имя тестовой базы должно оканчиваться на _test: {make_url(url).database}", returncode=2)
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    command.upgrade(alembic_config(database_url), "head")
    with Session(engine) as session:
        seed_all(session)
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    # Коммиты внутри теста становятся точками сохранения; всё откатывается в конце.
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield db
    db.close()
    transaction.rollback()
    connection.close()
