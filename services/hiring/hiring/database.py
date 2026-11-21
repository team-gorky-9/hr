from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def make_engine(url: str, *, connect_timeout: float | None = None):
    options = {}
    if connect_timeout is not None and url.startswith("postgresql"):
        from math import ceil
        options = {"connect_args": {"connect_timeout": max(1, ceil(connect_timeout))},
                   "pool_timeout": connect_timeout}
    return create_engine(url, pool_pre_ping=True, **options)


def migration_config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    return config


def migrate(engine) -> None:
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def at_head(engine) -> bool:
    head = ScriptDirectory.from_config(migration_config()).get_current_head()
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision() == head
