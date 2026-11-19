from alembic import command
from sqlalchemy import inspect

from app.db.base import Base
from tests.conftest import alembic_config


def test_models_match_migrations(engine, database_url):
    """Модели и миграции не разошлись: иначе alembic check бросит исключение."""
    command.check(alembic_config(database_url))


def test_all_tables_created(engine):
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables


def test_vector_extension_installed(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT 1 FROM pg_extension WHERE extname = 'vector'").scalar() == 1
