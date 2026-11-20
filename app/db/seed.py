"""Справочники и исходные должности. Повторный запуск безопасен: существующие записи обновляются.

Запуск: uv run python -m app.db.seed
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import Channel, RejectionSide, UserRole
from app.db.models import Position, ProductionCalendarDay, RejectionReason, SelectionStage, User, Vacancy

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


# Учётки стенда для учебной авторизации API (заголовок X-User-Login, api.md п. 1.2).
# Пароля нет: это подпись действия в журналах, а не защита.
DEMO_USERS: list[tuple[str, str, UserRole, str | None]] = [
    ("hr_demo", "Кадровик (учётка стенда)", UserRole.HR, None),
    ("dept_demo", "Представитель департамента (учётка стенда)", UserRole.DEPARTMENT,
     "Департамент-заказчик (учебный)"),
    ("dept2_demo", "Представитель второго департамента (учётка стенда)", UserRole.DEPARTMENT,
     "Департамент финансов (учебный)"),
    ("admin_demo", "Администратор (учётка стенда)", UserRole.ADMIN, None),
]


def seed_demo_users(session: Session) -> None:
    for login, full_name, role, department in DEMO_USERS:
        user = session.scalar(select(User).where(User.login == login))
        if user is None:
            user = User(login=login)
            session.add(user)
        user.full_name = full_name
        user.role = role
        user.department = department
        user.is_active = True
    session.flush()


# Производственный календарь РФ (ст. 112 ТК РФ и постановления Правительства о переносе выходных):
# false — нерабочий праздничный или перенесённый выходной день; true — рабочая суббота/воскресенье.
# На 2027 учтены официальные праздники ст. 112 ТК РФ и переносы совпавших выходных дней; при публикации
# нового постановления о переносах HR/администратор обновляет таблицу production_calendar_days.
PRODUCTION_CALENDAR_DAYS: list[tuple[date, bool, str]] = [
    # 2025 (ПП РФ от 04.10.2024 № 1335)
    *[(date(2025, 1, d), False, "Новогодние каникулы и Рождество") for d in range(1, 9)],
    (date(2025, 2, 23), False, "День защитника Отечества"),
    (date(2025, 3, 8), False, "Международный женский день"),
    (date(2025, 5, 1), False, "Праздник Весны и Труда"),
    (date(2025, 5, 2), False, "Перенос выходного с 4 января"),
    (date(2025, 5, 8), False, "Перенос выходного с 23 февраля"),
    (date(2025, 5, 9), False, "День Победы"),
    (date(2025, 6, 12), False, "День России"),
    (date(2025, 6, 13), False, "Перенос выходного с 8 марта"),
    (date(2025, 11, 1), True, "Перенесённый рабочий день (суббота)"),
    (date(2025, 11, 3), False, "Перенос выходного с 1 ноября"),
    (date(2025, 11, 4), False, "День народного единства"),
    (date(2025, 12, 31), False, "Перенос выходного с 5 января"),
    # 2026 (ПП РФ от 24.09.2025 № 1466)
    *[(date(2026, 1, d), False, "Новогодние каникулы и Рождество") for d in range(1, 9)],
    (date(2026, 1, 9), False, "Перенос выходного с 3 января"),
    (date(2026, 2, 23), False, "День защитника Отечества"),
    (date(2026, 3, 8), False, "Международный женский день"),
    (date(2026, 3, 9), False, "Перенос выходного с 8 марта"),
    (date(2026, 5, 1), False, "Праздник Весны и Труда"),
    (date(2026, 5, 9), False, "День Победы"),
    (date(2026, 5, 11), False, "Перенос выходного с 9 мая"),
    (date(2026, 6, 12), False, "День России"),
    (date(2026, 11, 4), False, "День народного единства"),
    (date(2026, 12, 31), False, "Перенос выходного с 4 января"),
    # 2027 (ст. 112 ТК РФ)
    *[(date(2027, 1, d), False, "Новогодние каникулы и Рождество") for d in range(1, 9)],
    (date(2027, 2, 23), False, "День защитника Отечества"),
    (date(2027, 3, 8), False, "Международный женский день"),
    (date(2027, 5, 1), False, "Праздник Весны и Труда"),
    (date(2027, 5, 3), False, "Перенос выходного с 1 мая"),
    (date(2027, 5, 9), False, "День Победы"),
    (date(2027, 5, 10), False, "Перенос выходного с 9 мая"),
    (date(2027, 6, 12), False, "День России"),
    (date(2027, 6, 14), False, "Перенос выходного с 12 июня"),
    (date(2027, 11, 4), False, "День народного единства"),
]


def seed_production_calendar(session: Session) -> None:
    for day, is_working, title in PRODUCTION_CALENDAR_DAYS:
        session.merge(ProductionCalendarDay(day=day, is_working_day=is_working, title=title))
    session.flush()


def seed_all(session: Session) -> None:
    seed_reference_data(session)
    seed_positions(session)
    seed_demo_users(session)
    seed_production_calendar(session)


if __name__ == "__main__":
    import sys

    from app.db.session import SessionLocal

    sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию не в UTF-8

    with SessionLocal() as session:
        seed_all(session)
        session.commit()
    print(f"Справочники загружены: этапов {len(STAGES)}, причин отказа {len(REJECTION_REASONS)}, "
          f"должностей {len(POSITIONS)}, учёток стенда {len(DEMO_USERS)}")
