"""Тесты outbox, недоступности/восстановления брокера, повтора и рестарта сервиса."""
from datetime import timedelta
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
import pytest

from requirements_service.api.app import create_app
from requirements_service.db.base import utcnow
from tests.conftest import ACTOR_DEPT_1, ORG_1, ORG_2, auth_headers, run_alembic_upgrade
from tests.support.consumer import (
    ConsumerCrashBeforeAck,
    InMemoryBroker,
    RequirementsApprovedConsumer,
)
from tests.test_e2e_acceptance import _make_economist_draft


def _prepare_accepted_draft(client: TestClient) -> tuple[str, str]:
    src = client.post(
        "/api/v1/sources",
        headers=auth_headers("hr"),
        files={
            "file": (
                "jd.txt",
                (
                    "Сотрудник составляет финансовые таблицы и проверяет исходные суммы.\n"
                    "Сотрудник объясняет выявленные расхождения в расчёте."
                ).encode("utf-8"),
                "text/plain",
            )
        },
        data={"position_code": "economist-training"},
    ).json()
    draft = client.post(
        "/api/v1/drafts",
        headers=auth_headers("hr"),
        json={"position_code": "economist-training", "content": _make_economist_draft(src["id"])},
    ).json()
    client.post(
        f"/api/v1/drafts/{draft['id']}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 1, "reviewer_actor_id": ACTOR_DEPT_1},
    )
    client.post(
        f"/api/v1/drafts/{draft['id']}/review",
        headers=auth_headers("department"),
        json={"expected_revision": 2, "result": "accepted", "note": "Принято"},
    )
    return draft["id"], src["id"]


def test_broker_outage_restart_persistence_retry_and_consumer_crash_before_ack(
    make_settings,
    tmp_path: Path,
):
    # 1. Стартуем при недоступном брокере.
    broker = InMemoryBroker(available=False)
    settings = make_settings(outbox_max_attempts=2, outbox_base_backoff_sec=0.0)
    run_alembic_upgrade(settings.database_url)

    app1 = create_app(settings, publisher=broker)
    with TestClient(app1) as client1:
        ready = client1.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["broker"] == "unavailable"

        draft_id, source_id = _prepare_accepted_draft(client1)
        approved_resp = client1.post(
            f"/api/v1/drafts/{draft_id}/approve",
            headers=auth_headers("hr"),
            json={"expected_revision": 3, "approval_basis": "Утверждено при сбое брокера"},
        )
        assert approved_resp.status_code == 201
        profile_id = approved_resp.json()["id"]

        # При недоступном брокере профиль сохранён, доставка в pending.
        deliveries = client1.get("/api/v1/deliveries?status=pending", headers={"Authorization": "Bearer fixture:hr"}).json()
        assert len(deliveries["items"]) == 1
        event_id = deliveries["items"][0]["event_id"]

        # Ошибки до исчерпания лимита переводят в failed.
        assert app1.state.outbox_relay.flush_once() == 0
        assert app1.state.outbox_relay.flush_once(now=utcnow() + timedelta(seconds=5)) == 0
        failed = client1.get("/api/v1/deliveries?status=failed", headers={"Authorization": "Bearer fixture:hr"}).json()
        assert len(failed["items"]) == 1
        assert failed["items"][0]["event_id"] == event_id
        assert failed["items"][0]["attempts"] == 2
        assert "unavailable" in failed["items"][0]["last_error"]
        # Полный payload и токены не утекают в GET /deliveries.
        assert "payload" not in failed["items"][0]

    # 2. Симулируем полный рестарт сервиса и восстановление брокера.
    broker.available = True
    app2 = create_app(settings, publisher=broker)
    with TestClient(app2) as client2:
        # После рестарта сохранены профиль, файл источника и failed-доставка.
        assert client2.get(f"/api/v1/profiles/{profile_id}", headers={"Authorization": "Bearer fixture:hr"}).status_code == 200
        assert client2.get(f"/api/v1/documents/{source_id}/content", headers={"Authorization": "Bearer fixture:hr"}).status_code == 200
        assert client2.get("/ready").json()["broker"] == "ok"

        # Ручной повтор доставки через API отправляет событие.
        retry_resp = client2.post(
            f"/api/v1/deliveries/{event_id}/retry",
            headers=auth_headers("hr"),
        )
        assert retry_resp.status_code == 200
        assert retry_resp.json()["status"] == "sent"
        assert broker.queue_len("w1.demo-recruitment.requirements.approved") == 1

        # 3. Получатель падает ПОСЛЕ commit в свою БД, но ДО ack брокеру.
        consumer = RequirementsApprovedConsumer(
            db_path=tmp_path / "consumer.db",
            fetch_profile_http=lambda pid, _org: (
                client2.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).status_code,
                client2.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).json(),
            ),
            allowed_organization_ids={ORG_1},
        )
        with pytest.raises(ConsumerCrashBeforeAck):
            consumer.consume_one_in_memory(broker, crash_after_commit_before_ack=True)

        # Сообщение вернулось в очередь как redelivered, в БД потребителя уже 1 запись.
        assert broker.queue_len("w1.demo-recruitment.requirements.approved") == 1
        assert len(consumer.list_received_profiles()) == 1

        # Повторная обработка того же сообщения после перезапуска подписчика: дубликат игнорируется безопасно!
        assert consumer.consume_one_in_memory(broker) == "duplicate"
        assert len(consumer.list_received_profiles()) == 1
        assert consumer.inbox_count() == 1
        assert broker.queue_len("w1.demo-recruitment.requirements.approved") == 0


def test_consumer_routes_invalid_schema_producer_or_org_to_dead_letter(env, tmp_path: Path):
    _app, client, _settings, broker = env
    consumer = RequirementsApprovedConsumer(
        db_path=tmp_path / "consumer.db",
        fetch_profile_http=lambda pid, _org: (
            client.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).status_code,
            client.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).json(),
        ),
        allowed_organization_ids={ORG_1},
    )

    # 1. Неподдерживаемая версия схемы -> dead-letter.
    broker.push_raw(
        consumer.QUEUE_NAME,
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "requirements.approved",
            "schema_version": "2.0",
            "producer": "requirements",
            "organization_id": ORG_1,
            "payload": {},
        },
    )
    assert consumer.consume_one_in_memory(broker) == "dead_letter"

    # 2. Неожиданный producer -> dead-letter.
    broker.push_raw(
        consumer.QUEUE_NAME,
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "requirements.approved",
            "schema_version": "1.0",
            "producer": "rogue-service",
            "organization_id": ORG_1,
            "payload": {},
        },
    )
    assert consumer.consume_one_in_memory(broker) == "dead_letter"

    # 3. Чужая организация -> dead-letter.
    broker.push_raw(
        consumer.QUEUE_NAME,
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "requirements.approved",
            "schema_version": "1.0",
            "producer": "requirements",
            "organization_id": ORG_2,
            "payload": {},
        },
    )
    assert consumer.consume_one_in_memory(broker) == "dead_letter"

    dlq_items = broker.drain_dead_letters()
    assert [item["reason"] for item in dlq_items] == [
        "unsupported_schema_version",
        "unexpected_producer",
        "unauthorized_organization",
    ]
    assert consumer.inbox_count() == 0
