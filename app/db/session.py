"""Подключение к базе: движок и фабрика сессий."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Сессия на один запрос; подходит как зависимость FastAPI (Depends)."""
    with SessionLocal() as session:
        yield session
