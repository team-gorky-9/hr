"""Утвердить профиль требований от имени кадровика — отдельный шаг, как в рабочем процессе.

    # последний черновик учебного профиля должности
    uv run python -m scripts.approve_profile --position-code python-dev --synthetic \
        --approver hr-demo --basis "учебный профиль для qa-01"
    # конкретная версия
    uv run python -m scripts.approve_profile --profile-id <uuid> --approver hr-demo --basis "..."

Загрузчик и оценщик профиль не утверждают (docs/modules/assessment.md): без утверждённого
профиля API отвечает `no_approved_profile`. Скрипт вызывает repository.approve_requirement_profile —
те же проверки, что в рабочем пути: только черновик, активный кадровик или администратор,
непустое основание; прежняя утверждённая версия того же контура уходит в архив.

Пользователь с логином --approver должен уже существовать. Скрипт не создаёт пользователей
и не меняет их роли: неактивный или с другой ролью получит отказ функции утверждения.
Без --commit изменения откатываются — так можно проверить, что будет утверждено.
"""
import argparse
import json
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import RequirementStatus
from app.db.models import Position, RequirementProfile, User


def find_draft(session: Session, *, profile_id: str | None, position_code: str | None,
               synthetic: bool) -> RequirementProfile:
    if profile_id:
        profile = session.get(RequirementProfile, uuid.UUID(profile_id))
        if profile is None:
            raise SystemExit(f"нет профиля {profile_id}")
        return profile
    position = session.scalar(select(Position).where(Position.code == position_code))
    if position is None:
        raise SystemExit(f"нет должности {position_code}")
    profile = session.scalars(
        select(RequirementProfile)
        .where(RequirementProfile.position_id == position.id,
               RequirementProfile.is_synthetic.is_(synthetic),
               RequirementProfile.status == RequirementStatus.DRAFT)
        .order_by(RequirementProfile.version.desc())
    ).first()
    if profile is None:
        contour = "учебного" if synthetic else "рабочего"
        raise SystemExit(f"у должности {position_code} нет черновика {contour} профиля")
    return profile


def approver(session: Session, login: str) -> User:
    user = session.scalar(select(User).where(User.login == login))
    if user is None:
        raise repo.RepositoryError("утверждающий пользователь не найден; укажите логин существующего кадровика или администратора")
    return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.approve_profile", description=__doc__.split("\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--profile-id", help="UUID профиля-черновика")
    target.add_argument("--position-code", help="код должности: берётся последний черновик контура")
    parser.add_argument("--synthetic", action="store_true", help="учебный контур (с --position-code)")
    parser.add_argument("--approver", required=True, help="логин кадровика, который утверждает")
    parser.add_argument("--basis", required=True, help="основание утверждения: что проверено и кем")
    parser.add_argument("--commit", action="store_true", help="записать; без флага — проверка с откатом")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal  # подключение к базе — только при запуске

    with SessionLocal() as session:
        profile = find_draft(session, profile_id=args.profile_id, position_code=args.position_code,
                             synthetic=args.synthetic)
        previous = repo.get_approved_profile(session, profile.position_id, synthetic=profile.is_synthetic)
        try:
            user = approver(session, args.approver)
            approved = repo.approve_requirement_profile(session, profile.id, approved_by_user_id=user.id,
                                                        approval_basis=args.basis)
        except repo.RepositoryError as error:
            session.rollback()
            print(json.dumps({"status": "refused", "error": str(error)}, ensure_ascii=False))
            return 1
        result = {
            "status": "approved" if args.commit else "dry_run",
            "profile_id": str(approved.id),
            "version": approved.version,
            "is_synthetic": approved.is_synthetic,
            "approver": user.login,
            "approver_created": False,
            "archived_previous": str(previous.id) if previous is not None else None,
        }
        if args.commit:
            session.commit()
        else:
            session.rollback()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
