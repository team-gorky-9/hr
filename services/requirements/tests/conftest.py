"""Общие фикстуры для автономных и интеграционных тестов сервиса требований."""
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest

from requirements_service.api.app import create_app
from requirements_service.config import Settings
from tests.support.consumer import InMemoryBroker

SERVICE_ROOT = Path(__file__).resolve().parents[1]

ORG_1 = "00000000-0000-4000-8000-000000000001"
ORG_2 = "00000000-0000-4000-8000-000000000002"
ACTOR_HR_1 = "00000000-0000-4000-8000-000000000101"
ACTOR_ADMIN_1 = "00000000-0000-4000-8000-000000000102"
ACTOR_DEPT_1 = "00000000-0000-4000-8000-000000000103"
ACTOR_EMP_1 = "00000000-0000-4000-8000-000000000104"
ACTOR_CAND_1 = "00000000-0000-4000-8000-000000000105"
ACTOR_HR_OTHER = "00000000-0000-4000-8000-000000000106"


def auth_headers(login: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer fixture:{login}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    else:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    return headers


def run_alembic_upgrade(database_url: str) -> None:
    cfg = Config(str(SERVICE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    cfg.attributes["database_url"] = database_url
    command.upgrade(cfg, "head")


@pytest.fixture()
def broker() -> InMemoryBroker:
    return InMemoryBroker(available=True)


@pytest.fixture()
def make_settings(tmp_path: Path):
    def _factory(**overrides) -> Settings:
        db_path = tmp_path / "requirements.db"
        file_root = tmp_path / "files"
        kwargs = {
            "database_url": f"sqlite+pysqlite:///{db_path}",
            "file_root": file_root,
            "outbox_poll_interval_sec": 0.0,
            "outbox_max_attempts": 3,
            "outbox_base_backoff_sec": 1.0,
            "seed_on_startup": True,
        }
        kwargs.update(overrides)
        return Settings(**kwargs)

    return _factory


@pytest.fixture()
def env(make_settings, broker: InMemoryBroker):
    settings = make_settings()
    run_alembic_upgrade(settings.database_url)
    app = create_app(settings, publisher=broker)
    with TestClient(app) as client:
        yield app, client, settings, broker
