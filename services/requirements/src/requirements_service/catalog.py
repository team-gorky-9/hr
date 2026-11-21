"""Internal vacancy catalog: approved profile → draft → publication → closure."""
from datetime import datetime
import json
from typing import Literal
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.exc import StaleDataError

from .api.routes import ActorDep, SessionDep, SettingsDep
from .auth import require_hr_or_admin
from .db.base import Base, JSONType, UTCDateTime, UUIDType, utcnow
from .db.models import ApprovedProfile
from .errors import ServiceError


class Vacancy(Base):
    __tablename__ = "catalog_vacancies"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    department_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    position_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("approved_profiles.id"), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    close_reason: Mapped[str | None] = mapped_column(Text)
    # Compare-and-swap protects updates even when two requests read the same revision.
    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class VacancyHistory(Base):
    __tablename__ = "catalog_vacancy_history"
    __table_args__ = (UniqueConstraint("vacancy_id", "revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    vacancy_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("catalog_vacancies.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateVacancy(Input):
    department_id: uuid.UUID
    position_code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1)
    profile_id: uuid.UUID


class Revision(Input):
    expected_revision: int = Field(ge=1, strict=True)


class PatchVacancy(Revision):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, min_length=1)
    profile_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_changes(self):
        fields = self.model_fields_set - {"expected_revision"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("Укажите непустое изменение title, description или profile_id")
        return self


class CloseVacancy(Revision):
    reason: str = Field(min_length=1)


class VacancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: uuid.UUID
    position_code: str
    title: str
    description: str
    profile_id: uuid.UUID
    profile_version: int
    revision: int
    status: Literal["draft", "published", "closed"]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    closed_at: datetime | None
    close_reason: str | None


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    revision: int
    actor_id: uuid.UUID
    action: str
    recorded_at: datetime
    snapshot: VacancyOut


class VacancyDetail(VacancyOut):
    history: list[HistoryOut]


class VacancyList(BaseModel):
    items: list[VacancyOut]


class PublicVacancy(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    description: str
    position_code: str
    published_at: datetime


class PublicList(BaseModel):
    items: list[PublicVacancy]


router = APIRouter(prefix="/api/v1", tags=["Vacancy catalog"])


def get_vacancy(session, actor, vacancy_id):
    require_hr_or_admin(actor)
    row = session.scalar(select(Vacancy).where(
        Vacancy.id == vacancy_id, Vacancy.organization_id == actor.organization_id))
    if row is None:
        raise ServiceError(404, "NOT_FOUND", "Вакансия не найдена.")
    return row


def get_profile(session, actor, profile_id, position_code, *, current=False):
    profile = session.scalar(select(ApprovedProfile).where(
        ApprovedProfile.id == profile_id,
        ApprovedProfile.organization_id == actor.organization_id))
    if profile is None:
        # A foreign ID is indistinguishable from a missing ID.
        raise ServiceError(404, "NOT_FOUND", "Утверждённый профиль не найден.")
    if profile.position_code != position_code or (current and not profile.is_current):
        raise ServiceError(409, "PROFILE_NOT_READY", "Выберите применимый текущий профиль этой должности.")
    return profile


def check_revision(row, expected):
    if row.revision != expected:
        raise ServiceError(409, "STALE_REVISION", "Загрузите актуальную редакцию вакансии.")


def persist(session, row, actor, action):
    try:
        session.flush()
        snapshot = VacancyOut.model_validate(row).model_dump(mode="json")
        session.add(VacancyHistory(vacancy_id=row.id, revision=row.revision,
                                  actor_id=actor.actor_id, action=action, snapshot=snapshot))
        session.commit()
    except StaleDataError as exc:
        session.rollback()
        raise ServiceError(409, "STALE_REVISION", "Вакансия уже изменена другим запросом.") from exc
    return VacancyOut.model_validate(row)


@router.post("/catalog/vacancies", response_model=VacancyOut, status_code=201)
def create(body: CreateVacancy, actor: ActorDep, session: SessionDep, settings: SettingsDep):
    require_hr_or_admin(actor)
    departments = json.loads(settings.fixture_org_path.read_text(encoding="utf-8"))["departments"]
    if not any(d["id"] == str(body.department_id) and
               d["organization_id"] == str(actor.organization_id) for d in departments):
        raise ServiceError(422, "VALIDATION_ERROR", "Подразделение недоступно.", field="department_id")
    profile = get_profile(session, actor, body.profile_id, body.position_code)
    row = Vacancy(**body.model_dump(), organization_id=actor.organization_id,
                  profile_version=profile.version)
    session.add(row)
    return persist(session, row, actor, "created")


@router.get("/catalog/vacancies", response_model=VacancyList)
def list_private(actor: ActorDep, session: SessionDep,
                 status: Literal["draft", "published", "closed"] | None = None):
    require_hr_or_admin(actor)
    query = select(Vacancy).where(Vacancy.organization_id == actor.organization_id)
    if status is not None:
        query = query.where(Vacancy.status == status)
    return {"items": list(session.scalars(query.order_by(Vacancy.created_at, Vacancy.id)))}


@router.get("/catalog/vacancies/{vacancy_id}", response_model=VacancyDetail)
def read(vacancy_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    row = get_vacancy(session, actor, vacancy_id)
    history = list(session.scalars(select(VacancyHistory).where(
        VacancyHistory.vacancy_id == row.id).order_by(VacancyHistory.revision)))
    return {**VacancyOut.model_validate(row).model_dump(), "history": history}


@router.patch("/catalog/vacancies/{vacancy_id}", response_model=VacancyOut)
def patch(vacancy_id: uuid.UUID, body: PatchVacancy, actor: ActorDep, session: SessionDep):
    row = get_vacancy(session, actor, vacancy_id)
    check_revision(row, body.expected_revision)
    if row.status != "draft":
        raise ServiceError(409, "INVALID_STATE", "Редактировать можно только черновик.")
    changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if "profile_id" in changes:
        profile = get_profile(session, actor, body.profile_id, row.position_code)
        row.profile_version = profile.version
    for key, value in changes.items():
        setattr(row, key, value)
    row.revision += 1
    row.updated_at = utcnow()
    return persist(session, row, actor, "edited")


@router.post("/catalog/vacancies/{vacancy_id}/publish", response_model=VacancyOut)
def publish(vacancy_id: uuid.UUID, body: Revision, actor: ActorDep, session: SessionDep):
    row = get_vacancy(session, actor, vacancy_id)
    check_revision(row, body.expected_revision)
    if row.status != "draft":
        raise ServiceError(409, "INVALID_STATE", "Опубликовать можно только черновик.")
    get_profile(session, actor, row.profile_id, row.position_code, current=True)
    row.status = "published"
    row.published_at = row.updated_at = utcnow()
    row.revision += 1
    return persist(session, row, actor, "published")


@router.post("/catalog/vacancies/{vacancy_id}/close", response_model=VacancyOut)
def close(vacancy_id: uuid.UUID, body: CloseVacancy, actor: ActorDep, session: SessionDep):
    row = get_vacancy(session, actor, vacancy_id)
    check_revision(row, body.expected_revision)
    if row.status not in ("draft", "published"):
        raise ServiceError(409, "INVALID_STATE", "Вакансия уже закрыта.")
    row.status = "closed"
    row.close_reason = body.reason
    row.closed_at = row.updated_at = utcnow()
    row.revision += 1
    return persist(session, row, actor, "closed")


@router.get("/public/vacancies", response_model=PublicList)
def list_public(session: SessionDep):
    return {"items": list(session.scalars(select(Vacancy).where(
        Vacancy.status == "published").order_by(Vacancy.published_at, Vacancy.id)))}
