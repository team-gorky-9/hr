"""Курсорная пагинация по стабильному порядку (created_at, id)."""
import base64
from datetime import datetime, timezone
import json
from typing import Any, Callable, Sequence
import uuid

from sqlalchemy import and_, or_

from .errors import ServiceError


def encode_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    """Закодировать пару (created_at, id) в непрозрачный cursor."""
    ts = created_at.astimezone(timezone.utc).isoformat() if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc).isoformat()
    raw = json.dumps({"ts": ts, "id": str(item_id)}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    """Разобрать opaque cursor или вернуть 422 VALIDATION_ERROR при подделке."""
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        ts = datetime.fromisoformat(data["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        item_id = uuid.UUID(data["id"])
        return ts.astimezone(timezone.utc), item_id
    except Exception as exc:
        raise ServiceError(
            422,
            "VALIDATION_ERROR",
            "Некорректный курсор пагинации.",
            field="cursor",
        ) from exc


def apply_cursor_filter(stmt, created_col, id_col, cursor: str | None):
    """Применить фильтр стабильной сортировки (created_at, id) > cursor."""
    decoded = decode_cursor(cursor)
    if decoded is not None:
        ts, item_id = decoded
        stmt = stmt.where(
            or_(
                created_col > ts,
                and_(created_col == ts, id_col > item_id),
            )
        )
    return stmt.order_by(created_col.asc(), id_col.asc())


def build_page(
    rows: Sequence[Any],
    *,
    limit: int,
    serializer: Callable[[Any], Any],
    get_created_at: Callable[[Any], datetime] = lambda row: row.created_at,
    get_id: Callable[[Any], uuid.UUID] = lambda row: row.id,
) -> tuple[list[Any], str | None]:
    """Собрать страницу результатов и next_cursor при выборке limit + 1."""
    has_more = len(rows) > limit
    page_rows = list(rows[:limit])
    items = [serializer(row) for row in page_rows]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = encode_cursor(get_created_at(last), get_id(last))
    return items, next_cursor
