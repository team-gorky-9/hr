"""Справочники и исходные должности. Повторный запуск безопасен: существующие записи обновляются.

Запуск: uv run python -m app.db.seed
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import Channel, RejectionSide
from app.db.models import Position, RejectionReason, SelectionStage, Vacancy

# Этапы из процесса «как есть» в кейсе. Резерв — не этап (см. ReserveEntry).
STAGES: list[tuple[str, str, bool]] = [
    ("new", "Новый отклик", False),
    ("screening", "Первичный отбор", False),
    ("phone_interview", "Телефонное интервью", False),
    ("sent_to_department", "Передан в департамент", False),
    ("department_interview", "Собеседование в департаменте", False),
    ("documents", "Оформление документов", False),
    ("hired", "Принят", True),
    ("rejected", "Отказ", True),
    ("withdrawn", "Кандидат отказался", True),
]
INITIAL_STAGE = "new"

REJECTION_REASONS: list[tuple[str, str, RejectionSide]] = [
    ("formal_requirements", "Не соответствует формальным требованиям должности", RejectionSide.EMPLOYER),
    ("competencies", "Не подтверждены необходимые компетенции", RejectionSide.EMPLOYER),
    ("experience", "Недостаточно профессионального опыта", RejectionSide.EMPLOYER),
    ("legal_restrictions", "Ограничения, установленные законом для муниципальной службы", RejectionSide.EMPLOYER),
    ("position_filled", "Должность замещена другим кандидатом", RejectionSide.EMPLOYER),
    ("candidate_declined", "Кандидат отказался от продолжения отбора", RejectionSide.CANDIDATE),
    ("no_response", "Кандидат не выходит на связь", RejectionSide.CANDIDATE),
    ("other", "Другое (указать в комментарии)", RejectionSide.OTHER),
]

AC_EMPLOYER = "АНО «Аналитический центр города Нижнего Новгорода»"
CITY_ADMINISTRATION = "Администрация города Нижнего Новгорода"


@dataclass(frozen=True)
class PositionSeed:
    code: str
    title: str
    employer: str
    is_municipal_service: bool
    # Папка в архиве организаторов «Кадры»: по ней импорт находит должность отклика.
    source_folder: str
    service_group: str | None = None


# Шесть должностей из данных организаторов. Названия — из «Вакансия.txt» и ДИ.
POSITIONS: list[PositionSeed] = [
    PositionSeed("junior-python-dev", "Junior Python-разработчик", AC_EMPLOYER, False,
                 "Junior Python-разработчик"),
    PositionSeed("python-dev", "Python-разработчик", AC_EMPLOYER, False, "Python-разработчик"),
    PositionSeed("qa-manual", "QA Engineer (Manual)", AC_EMPLOYER, False, "QA Engineer Manual"),
    PositionSeed("frontend-dev", "Frontend developer", AC_EMPLOYER, False, "Frontend developer"),
    PositionSeed("junior-ux-ui", "Junior UX/UI Дизайнер", AC_EMPLOYER, False, "Junior UX_UI Дизайнер"),
    PositionSeed(
        "hr-consultant",
        "Консультант сектора подбора кадров отдела подбора кадров и мотивации "
        "департамента кадровой политики и развития муниципального управления",
        CITY_ADMINISTRATION,
        True,
        "консультанта сектора подбора кадров",
        service_group="Ведущая группа должностей муниципальной службы (группа 3)",
    ),
]

# Папка архива → код должности. Импорт использует это вместо разбора названия папки.
POSITION_CODE_BY_FOLDER: dict[str, str] = {p.source_folder: p.code for p in POSITIONS}


def seed_reference_data(session: Session) -> None:
    for order, (code, title, is_final) in enumerate(STAGES, start=1):
        session.merge(SelectionStage(code=code, title=title, sort_order=order, is_final=is_final))
    for code, title, side in REJECTION_REASONS:
        session.merge(RejectionReason(code=code, title=title, side=side))
    session.flush()


def seed_positions(session: Session) -> None:
    """Должности и по одной открытой вакансии на hh.ru для каждой: отклики в архиве
    организаторов выгружены из hh.ru (формат «hh_txt» и «hh_docx»)."""
    for seed in POSITIONS:
        position = session.scalar(select(Position).where(Position.code == seed.code))
        if position is None:
            position = Position(code=seed.code)
            session.add(position)
        position.title = seed.title
        position.employer = seed.employer
        position.is_municipal_service = seed.is_municipal_service
        position.service_group = seed.service_group
        session.flush()

        has_vacancy = session.scalar(
            select(Vacancy.id).where(Vacancy.position_id == position.id, Vacancy.channel == Channel.HH_RU)
        )
        if has_vacancy is None:
            session.add(Vacancy(position_id=position.id, channel=Channel.HH_RU, title=seed.title))
    session.flush()


def seed_all(session: Session) -> None:
    seed_reference_data(session)
    seed_positions(session)


if __name__ == "__main__":
    import sys

    from app.db.session import SessionLocal

    sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию не в UTF-8

    with SessionLocal() as session:
        seed_all(session)
        session.commit()
    print(f"Справочники загружены: этапов {len(STAGES)}, причин отказа {len(REJECTION_REASONS)}, "
          f"должностей {len(POSITIONS)}")
