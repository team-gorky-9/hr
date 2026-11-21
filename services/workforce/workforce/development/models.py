from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from workforce.models import Base, Resource


class Goal(Resource, Base):
    __tablename__ = "development_goals"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="private")
    shared_with_actor_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
    share_basis: Mapped[dict | None] = mapped_column(JSON)


class GoalVersion(Base):
    __tablename__ = "development_goal_versions"
    goal_id: Mapped[str] = mapped_column(ForeignKey("development_goals.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON)


class Plan(Resource, Base):
    __tablename__ = "development_plans"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("development_goals.id"))
    owner_actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"), index=True)
    manager_actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    reviewer_actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    assignment_basis: Mapped[dict] = mapped_column(JSON)
    title: Mapped[str] = mapped_column(String(300))
    criteria: Mapped[list] = mapped_column(JSON)
    activities: Mapped[list] = mapped_column(JSON)
    goal_revision: Mapped[int] = mapped_column(Integer)
    goal_snapshot: Mapped[dict] = mapped_column(JSON)
    agreed_revision: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    decision_note: Mapped[str | None] = mapped_column(Text)
