"""Тестовый подписчик requirements.approved для автономной и live-проверки RabbitMQ.

Поддерживает:
- работу поверх настоящего брокера RabbitMQ (pika) и автономного InMemoryBroker;
- проверку версии схемы, producer и организации (невалидные сообщения уходят в dead-letter);
- HTTP-чтение профиля GET /api/v1/profiles/{id} и валидацию формата requirement-draft/1.0;
- транзакционную идемпотентность потребителя (consumer_inbox по event_id);
- симуляцию падения после commit до ack с безопасной повторной обработкой.
"""
from collections import deque
from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Callable
import uuid

import pika

from requirements_service.messaging.transport import BrokerPublishError
from requirements_service.validation import validate_draft_content


class ConsumerCrashBeforeAck(RuntimeError):
    """Тестовое прерывание обработчика после commit в БД, но до AMQP ack."""


@dataclass
class BrokerMessage:
    exchange: str
    routing_key: str
    body: bytes
    redelivered: bool = False


class InMemoryBroker:
    """Локальная потокобезопасная модель topic exchange + durable очередей с ack/requeue/DLQ."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self._lock = threading.Lock()
        self._queues: dict[str, deque[BrokerMessage]] = {
            "w1.demo-recruitment.requirements.approved": deque(),
            "w1.demo-recruitment.dead": deque(),
        }

    def publish(self, *, exchange: str, routing_key: str, envelope: dict[str, Any]) -> None:
        if not self.available:
            raise BrokerPublishError("In-memory broker unavailable (simulated outage)")
        raw = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        with self._lock:
            if exchange == "w1.requirements" and routing_key == "requirements.approved":
                self._queues["w1.demo-recruitment.requirements.approved"].append(
                    BrokerMessage(exchange=exchange, routing_key=routing_key, body=raw)
                )

    def push_raw(self, queue_name: str, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self._lock:
            self._queues.setdefault(queue_name, deque()).append(
                BrokerMessage(exchange="w1.requirements", routing_key="requirements.approved", body=raw)
            )

    def push_dead_letter(self, queue_name: str, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self._lock:
            self._queues.setdefault(queue_name, deque()).append(
                BrokerMessage(exchange="", routing_key=queue_name, body=raw)
            )

    def pop(self, queue_name: str) -> BrokerMessage | None:
        with self._lock:
            q = self._queues.get(queue_name)
            if not q:
                return None
            return q.popleft()

    def requeue_front(self, queue_name: str, msg: BrokerMessage) -> None:
        with self._lock:
            msg.redelivered = True
            self._queues.setdefault(queue_name, deque()).appendleft(msg)

    def queue_len(self, queue_name: str) -> int:
        with self._lock:
            return len(self._queues.get(queue_name, ()))

    def drain_dead_letters(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            msg = self.pop("w1.demo-recruitment.dead")
            if msg is None:
                return items
            items.append(json.loads(msg.body.decode("utf-8")))

    def check_health(self) -> bool:
        return self.available

    def close(self) -> None:
        return None


@dataclass
class ConsumerState:
    db_path: Path
    stored_profiles: list[dict[str, Any]] = field(default_factory=list)


class RequirementsApprovedConsumer:
    """Потребитель событий requirements.approved с идемпотентным inbox и HTTP-валидацией."""

    QUEUE_NAME = "w1.demo-recruitment.requirements.approved"
    DLQ_NAME = "w1.demo-recruitment.dead"

    def __init__(
        self,
        *,
        db_path: Path,
        fetch_profile_http: Callable[[str, str], tuple[int, dict[str, Any]]],
        allowed_organization_ids: set[str] | None = None,
    ) -> None:
        self._db_path = db_path
        self._fetch_profile_http = fetch_profile_http
        self._allowed_orgs = allowed_organization_ids
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consumer_inbox (
                    event_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consumer_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    profile_id TEXT NOT NULL,
                    position_code TEXT NOT NULL,
                    profile_version INTEGER NOT NULL,
                    contour TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def list_received_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_id, profile_id, position_code, profile_version, contour FROM consumer_profiles ORDER BY id ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    def inbox_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM consumer_inbox").fetchone()
            return int(row["cnt"])

    def process_message_bytes(
        self,
        body: bytes,
        *,
        crash_after_commit_before_ack: bool = False,
    ) -> tuple[str, dict[str, Any] | None]:
        """Обработать сырое сообщение. Возвращает (status, dead_letter_payload|None).

        status ∈ {'processed', 'duplicate', 'dead_letter'}.
        """
        try:
            envelope = json.loads(body.decode("utf-8"))
        except Exception as exc:
            return "dead_letter", {"reason": f"invalid_json: {exc}", "raw": body.decode("utf-8", "replace")}

        if not isinstance(envelope, dict):
            return "dead_letter", {"reason": "envelope_not_object"}
        if envelope.get("schema_version") != "1.0":
            return "dead_letter", {"reason": "unsupported_schema_version", "envelope": envelope}
        if envelope.get("event_type") != "requirements.approved":
            return "dead_letter", {"reason": "unexpected_event_type", "envelope": envelope}
        if envelope.get("producer") != "requirements":
            return "dead_letter", {"reason": "unexpected_producer", "envelope": envelope}

        org_id = str(envelope.get("organization_id", ""))
        if self._allowed_orgs is not None and org_id not in self._allowed_orgs:
            return "dead_letter", {"reason": "unauthorized_organization", "envelope": envelope}

        try:
            event_id = str(uuid.UUID(str(envelope["event_id"])))
            payload = envelope["payload"]
            profile_id = str(uuid.UUID(str(payload["profile_id"])))
            profile_version = int(payload["profile_version"])
            contour = str(payload["contour"])
            position_code = str(payload["position_code"])
        except Exception as exc:
            return "dead_letter", {"reason": f"invalid_payload: {exc}", "envelope": envelope}

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT event_id FROM consumer_inbox WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                return "duplicate", None

            status_code, profile_body = self._fetch_profile_http(profile_id, org_id)
            if status_code != 200:
                raise RuntimeError(f"Failed to fetch approved profile {profile_id}: HTTP {status_code}")

            validated = validate_draft_content(profile_body["content"])
            if profile_body["version"] != profile_version or profile_body["contour"] != contour:
                raise RuntimeError("Profile metadata mismatch between event and HTTP API")
            if validated.position_code != position_code:
                raise RuntimeError("Position code mismatch between event and profile content")

            conn.execute(
                "INSERT INTO consumer_inbox (event_id, organization_id, profile_id) VALUES (?, ?, ?)",
                (event_id, org_id, profile_id),
            )
            conn.execute(
                """
                INSERT INTO consumer_profiles (event_id, profile_id, position_code, profile_version, contour)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, profile_id, position_code, profile_version, contour),
            )
            conn.commit()

        if crash_after_commit_before_ack:
            raise ConsumerCrashBeforeAck("Simulated worker crash after DB commit before AMQP ack")
        return "processed", None

    def consume_one_in_memory(
        self,
        broker: InMemoryBroker,
        *,
        crash_after_commit_before_ack: bool = False,
    ) -> str | None:
        """Считать и обработать одно сообщение из InMemoryBroker."""
        msg = broker.pop(self.QUEUE_NAME)
        if msg is None:
            return None
        try:
            outcome, dead_payload = self.process_message_bytes(
                msg.body,
                crash_after_commit_before_ack=crash_after_commit_before_ack,
            )
        except ConsumerCrashBeforeAck:
            broker.requeue_front(self.QUEUE_NAME, msg)
            raise
        if outcome == "dead_letter" and dead_payload is not None:
            broker.push_dead_letter(self.DLQ_NAME, dead_payload)
        return outcome

    def consume_from_rabbitmq(
        self,
        rabbitmq_url: str,
        *,
        max_messages: int = 1,
        crash_after_commit_before_ack: bool = False,
    ) -> list[str]:
        """Считать сообщения из настоящего RabbitMQ (manual ack после commit в БД)."""
        params = pika.URLParameters(rabbitmq_url)
        conn = pika.BlockingConnection(params)
        channel = conn.channel()
        channel.exchange_declare(exchange="w1.requirements", exchange_type="topic", durable=True)
        channel.queue_declare(queue=self.QUEUE_NAME, durable=True)
        channel.queue_declare(queue=self.DLQ_NAME, durable=True)
        channel.queue_bind(
            queue=self.QUEUE_NAME,
            exchange="w1.requirements",
            routing_key="requirements.approved",
        )
        outcomes: list[str] = []
        try:
            for _ in range(max_messages):
                method, _props, body = channel.basic_get(queue=self.QUEUE_NAME, auto_ack=False)
                if method is None:
                    break
                try:
                    outcome, dead_payload = self.process_message_bytes(
                        body,
                        crash_after_commit_before_ack=crash_after_commit_before_ack,
                    )
                except ConsumerCrashBeforeAck:
                    channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    raise
                if outcome == "dead_letter" and dead_payload is not None:
                    channel.basic_publish(
                        exchange="",
                        routing_key=self.DLQ_NAME,
                        body=json.dumps(dead_payload, ensure_ascii=False).encode("utf-8"),
                        properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
                    )
                channel.basic_ack(delivery_tag=method.delivery_tag)
                outcomes.append(outcome)
            return outcomes
        finally:
            if conn.is_open:
                conn.close()
