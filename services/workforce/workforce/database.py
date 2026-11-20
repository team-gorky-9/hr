import hashlib
import hmac
import json
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from workforce.models import Actor, Department, Organization


def make_engine(url):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _):
            dbapi_connection.isolation_level = None
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
            dbapi_connection.execute("PRAGMA busy_timeout=15000")

        @event.listens_for(engine, "begin")
        def begin(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def migration_config():
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return config


def migrate(engine):
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}:{digest}"


def verify_password(password, encoded):
    return hmac.compare_digest(password_hash(password, encoded.split(":")[0]), encoded)


def seed(engine, settings):
    organization = json.loads((settings.fixture_dir / "organization.json").read_text(encoding="utf-8"))
    actors = json.loads((settings.fixture_dir / "actors.json").read_text(encoding="utf-8"))["actors"]
    with Session(engine) as session, session.begin():
        # Seed runs once before API/worker start; existing records and revoked sessions are preserved.
        for item in organization["organizations"]:
            if session.get(Organization, item["id"]) is None:
                session.add(Organization(**item))
        session.flush()
        for item in organization["departments"]:
            if session.get(Department, item["id"]) is None:
                session.add(Department(**item))
        for item in actors:
            if session.scalar(select(Actor).where(Actor.login == item["login"])) is None:
                session.add(
                    Actor(
                        id=item["actor_id"],
                        login=item["login"],
                        organization_id=item["organization_id"],
                        grants=item["grants"],
                        active=item["active"],
                        password_hash=password_hash(item["password"]),
                    )
                )
