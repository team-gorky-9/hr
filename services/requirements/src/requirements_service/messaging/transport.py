"""Транспортный слой публикации сообщений в RabbitMQ (pika с publisher confirm)."""
import json
import threading
from typing import Any, Protocol

import pika
from pika.exceptions import AMQPError, UnroutableError


class BrokerPublishError(Exception):
    """Ошибка подключения к брокеру или неподтверждённой публикации."""


class MessagePublisher(Protocol):
    """Абстракция издателя доменных событий (AMQP или тестовая подмена)."""

    def publish(self, *, exchange: str, routing_key: str, envelope: dict[str, Any]) -> None:
        """Опубликовать устойчивое сообщение с ожиданием подтверждения брокера."""
        ...

    def check_health(self) -> bool:
        """Проверить доступность брокера."""
        ...

    def close(self) -> None:
        """Освободить сетевые ресурсы."""
        ...


class RabbitMQPublisher:
    """Синхронный издатель AMQP на базе pika с publisher confirm и durable exchange."""

    def __init__(self, rabbitmq_url: str, *, connect_timeout_sec: float = 3.0) -> None:
        self._url = rabbitmq_url
        self._connect_timeout_sec = connect_timeout_sec
        self._lock = threading.Lock()
        self._declared_exchanges: set[str] = set()

    def _new_connection(self) -> pika.BlockingConnection:
        params = pika.URLParameters(self._url)
        params.socket_timeout = self._connect_timeout_sec
        params.blocked_connection_timeout = self._connect_timeout_sec
        return pika.BlockingConnection(params)

    def publish(self, *, exchange: str, routing_key: str, envelope: dict[str, Any]) -> None:
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        props = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,  # persistent
            message_id=str(envelope["event_id"]),
            correlation_id=str(envelope["correlation_id"]),
            type=str(envelope["event_type"]),
        )
        with self._lock:
            conn: pika.BlockingConnection | None = None
            try:
                conn = self._new_connection()
                channel = conn.channel()
                channel.exchange_declare(
                    exchange=exchange,
                    exchange_type="topic",
                    durable=True,
                )
                channel.confirm_delivery()
                channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=props,
                    mandatory=False,
                )
            except (AMQPError, UnroutableError, OSError) as exc:
                raise BrokerPublishError(f"RabbitMQ publish failed: {exc}") from exc
            finally:
                if conn is not None and conn.is_open:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def check_health(self) -> bool:
        with self._lock:
            conn: pika.BlockingConnection | None = None
            try:
                conn = self._new_connection()
                return bool(conn.is_open)
            except (AMQPError, OSError):
                return False
            finally:
                if conn is not None and conn.is_open:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def close(self) -> None:
        return None
