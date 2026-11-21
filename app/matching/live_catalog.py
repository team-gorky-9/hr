"""Read the application's actual open vacancies and their current approved profiles."""
from datetime import UTC, datetime
from sqlalchemy import select
from app.db import repository as repo
from app.db.enums import VacancyStatus
from app.db.models import Vacancy, Position
from app.matching.schemas import VacancySnapshot


def legacy_catalog(session, contour):
    observed = datetime.now(UTC)
    rows = session.execute(select(Vacancy, Position).join(Position, Position.id == Vacancy.position_id)
                           .where(Vacancy.status == VacancyStatus.OPEN).order_by(Vacancy.id)).all()
    snapshots = []
    for vacancy, position in rows:
        profile = repo.get_approved_profile(session, position.id, synthetic=contour == "training")
        snapshots.append(VacancySnapshot(ref={"system": "legacy-hr", "id": vacancy.id}, revision=1,
            title=vacancy.title, description=position.title, position_code=position.code,
            status="published", contour=contour, observed_at=observed,
            profile_ref={"system": "legacy-hr", "id": profile.id, "version": profile.version} if profile else None))
    return snapshots
