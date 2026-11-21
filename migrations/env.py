"""Настройка Alembic: откуда брать адрес базы и описание таблиц."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import app.db.models  # noqa: F401  регистрирует все таблицы в Base.metadata
import app.assessment.artifacts  # noqa: F401
from app.config import settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    # Тесты передают адрес тестовой базы через config.attributes; иначе — из настроек (.env).
    return config.attributes.get("database_url") or settings.database_url


def run_migrations_offline() -> None:
    """Печать SQL без подключения: alembic upgrade head --sql."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(database_url())
    with engine.connect() as connection:
        _run(connection)
    engine.dispose()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
