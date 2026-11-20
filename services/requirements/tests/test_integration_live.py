"""Live-интеграционный тест с настоящими PostgreSQL 17 (Alembic) и RabbitMQ (pika).

Пропускается с явной причиной, если TEST_DATABASE_URL или TEST_RABBITMQ_URL не заданы.
"""
import os
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from requirements_service.api.app import create_app
from requirements_service.config import Settings
from requirements_service.db.session import create_db_engine
from tests.conftest import ORG_1, auth_headers, run_alembic_upgrade
from tests.support.consumer import ConsumerCrashBeforeAck, RequirementsApprovedConsumer
from tests.test_outbox_and_broker import _prepare_accepted_draft

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_RABBITMQ_URL = os.environ.get("TEST_RABBITMQ_URL")


@pytest.mark.integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL or not TEST_RABBITMQ_URL,
    reason="Требуются TEST_DATABASE_URL (PostgreSQL 17) и TEST_RABBITMQ_URL (RabbitMQ)",
)
def test_live_postgres_alembic_and_rabbitmq_end_to_end(tmp_path: Path):
    engine = create_db_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()

    run_alembic_upgrade(TEST_DATABASE_URL)
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        rabbitmq_url=TEST_RABBITMQ_URL,
        file_root=tmp_path / "files",
        outbox_poll_interval_sec=0.0,
        seed_on_startup=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        draft_id, _source_id = _prepare_accepted_draft(client)
        approve = client.post(
            f"/api/v1/drafts/{draft_id}/approve",
            headers=auth_headers("hr"),
            json={"expected_revision": 3, "approval_basis": "Live PostgreSQL + RabbitMQ test"},
        )
        assert approve.status_code == 201
        profile_id = approve.json()["id"]

        assert app.state.outbox_relay.flush_once() >= 1

        consumer = RequirementsApprovedConsumer(
            db_path=tmp_path / f"consumer-{uuid.uuid4().hex}.db",
            fetch_profile_http=lambda pid, _org: (
                client.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).status_code,
                client.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).json(),
            ),
            allowed_organization_ids={ORG_1},
        )
        with pytest.raises(ConsumerCrashBeforeAck):
            consumer.consume_from_rabbitmq(
                TEST_RABBITMQ_URL,
                max_messages=1,
                crash_after_commit_before_ack=True,
            )
        outcomes = consumer.consume_from_rabbitmq(TEST_RABBITMQ_URL, max_messages=1)
        assert outcomes == ["duplicate"]
        received = consumer.list_received_profiles()
        assert len(received) == 1
        assert received[0]["profile_id"] == profile_id
