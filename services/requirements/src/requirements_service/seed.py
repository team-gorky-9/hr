"""Идемпотентная начальная загрузка учебной организации и должностей из organization.json."""
import argparse
import json
from pathlib import Path
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import load_settings
from .db.base import utcnow
from .db.models import Position
from .db.session import create_db_engine, create_session_factory


def seed_positions(
    session: Session,
    *,
    org_path: Path,
    default_organization_id: uuid.UUID,
) -> int:
    """Создать отсутствующие должности из organization.json; повторный запуск безопасен."""
    if not org_path.is_file():
        return 0
    payload = json.loads(org_path.read_text(encoding="utf-8"))
    organizations = payload.get("organizations", [])
    target_org_id = (
        uuid.UUID(str(organizations[0]["id"]))
        if organizations
        else default_organization_id
    )
    created = 0
    now = utcnow()
    for pos in payload.get("positions", []):
        code = str(pos["code"]).strip()
        title = str(pos["title"]).strip()
        existing = session.scalar(
            select(Position).where(
                Position.organization_id == target_org_id,
                Position.code == code,
            )
        )
        if existing is not None:
            continue
        session.add(
            Position(
                organization_id=target_org_id,
                code=code,
                title=title,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        created += 1
    session.flush()
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Начальное заполнение должностей сервиса требований")
    parser.parse_args(argv)
    settings = load_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            count = seed_positions(
                session,
                org_path=settings.fixture_org_path,
                default_organization_id=uuid.UUID(settings.seed_organization_id),
            )
            session.commit()
        print(f"seeded positions: {count}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
