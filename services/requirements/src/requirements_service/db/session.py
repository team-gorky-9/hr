"""Создание SQLAlchemy Engine и фабрики сессий."""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def create_db_engine(database_url: str) -> Engine:
    """Создать синхронный SQLAlchemy Engine для PostgreSQL или SQLite."""
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def create_session_factory(engine: Engine) -> sessionmaker:
    """Создать фабрику синхронных сессий без автосброса атрибутов после commit."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
