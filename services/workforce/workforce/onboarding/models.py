from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from workforce.models import Base, Resource, now


class Template(Base):
    __tablename__ = "onboarding_templates"
    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    steps: Mapped[list] = mapped_column(JSON)


class Program(Resource, Base):
    __tablename__ = "onboarding_programs"
    __table_args__ = (
        UniqueConstraint("workforce_assignment_id", "template_code", "template_version"),
        ForeignKeyConstraint(
            ["template_code", "template_version"],
            ["onboarding_templates.code", "onboarding_templates.version"],
        ),
        CheckConstraint("status IN ('active', 'intro_completed', 'cancelled')", name="onboarding_status"),
    )
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    workforce_assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"))
    template_code: Mapped[str] = mapped_column(String(100))
    template_version: Mapped[int] = mapped_column(Integer)
    assigned_by_actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(30), default="active")
    steps: Mapped[list] = mapped_column(JSON)
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
