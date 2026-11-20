"""Отбор: отклики, этапы, интервью, обратная связь департамента, кадровый резерв."""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.db.enums import (
    ApplicationSource,
    DeadlineExtensionReason,
    FeedbackOutcome,
    HandoffChannel,
    HandoffStatus,
    InterviewKind,
    InterviewResult,
    ProcessFactStatus,
    QuestionAuthor,
    RejectionSide,
    ReserveStatus,
)
from app.db.models.candidates import Candidate
from app.db.models.positions import Vacancy


class SelectionStage(Base):
    """Справочник этапов отбора. Кадровик может добавить свой этап без миграции."""
    __tablename__ = "selection_stages"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    # Из финального этапа (принят, отказ, кандидат отказался) переходов нет.
    is_final: Mapped[bool] = mapped_column(Boolean)


class RejectionReason(Base):
    """Справочник причин отказа: чтобы их можно было посчитать, а не искать в комментариях."""
    __tablename__ = "rejection_reasons"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    side: Mapped[RejectionSide] = mapped_column(str_enum(RejectionSide, "side"))


class Application(Base):
    """Участие кандидата в отборе на вакансию.

    vacancy_id пуст для откликов на должности вне платформы — например, строки
    «История общения с кандидатом» из резюме консультанта: тогда заполнено
    external_position_title.
    """
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    vacancy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE")
    )
    external_position_title: Mapped[str | None] = mapped_column(String(512))
    # Публикация hh, на которую пришёл отклик (подвал резюме «Отклик на вакансию: «…»») [v1.6].
    # Не путать с external_position_title: там должность вне платформы, здесь — откуда пришёл отклик.
    posting_title: Mapped[str | None] = mapped_column(String(512))
    source: Mapped[ApplicationSource] = mapped_column(str_enum(ApplicationSource, "source"))
    applied_at: Mapped[date | None] = mapped_column(Date)
    # Текущий этап; история переходов — в stage_events (развилка Р5).
    current_stage_code: Mapped[str] = mapped_column(ForeignKey("selection_stages.code"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    candidate: Mapped[Candidate] = relationship()
    vacancy: Mapped[Vacancy | None] = relationship()
    current_stage: Mapped[SelectionStage] = relationship()

    __table_args__ = (
        CheckConstraint(
            "vacancy_id IS NOT NULL OR external_position_title IS NOT NULL",
            name="has_target",
        ),
        # Один кандидат не может дважды участвовать в отборе на одну вакансию.
        Index(
            "uq_applications_candidate_vacancy",
            "candidate_id",
            "vacancy_id",
            unique=True,
            postgresql_where=sa_text("vacancy_id IS NOT NULL"),
        ),
        # Внешний отклик из «Истории общения» не повторяется: кандидат + название + дата [v1.6].
        Index(
            "uq_applications_history",
            "candidate_id",
            "external_position_title",
            "applied_at",
            unique=True,
            postgresql_where=sa_text("source = 'history'"),
            postgresql_nulls_not_distinct=True,
        ),
    )


class StageEvent(Base):
    """Переход отклика между этапами: кто, когда, почему. Записи только добавляются."""
    __tablename__ = "stage_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Порядковый номер события. Время created_at = начало транзакции (now()), и у нескольких
    # переходов в одной транзакции оно совпадает; порядок истории задаёт seq.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    from_stage_code: Mapped[str | None] = mapped_column(ForeignKey("selection_stages.code"))
    to_stage_code: Mapped[str] = mapped_column(ForeignKey("selection_stages.code"))
    rejection_reason_code: Mapped[str | None] = mapped_column(ForeignKey("rejection_reasons.code"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


class Interview(Base):
    """Телефонное интервью кадровика или собеседование в департаменте."""
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[InterviewKind] = mapped_column(str_enum(InterviewKind, "kind"))
    interviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[InterviewResult] = mapped_column(
        str_enum(InterviewResult, "result"),
        default=InterviewResult.PENDING,
        server_default="pending",
    )
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InterviewQuestion.sort_order",
    )


class InterviewQuestion(Base):
    """Вопрос интервью. Привязан к компетенции или к пробелу в резюме, чтобы
    разных кандидатов проверяли по одним критериям."""
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    competency_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competencies.id", ondelete="SET NULL")
    )
    # Чего не хватает в резюме: «не указан опыт работы с обращениями граждан».
    gap: Mapped[str | None] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    author: Mapped[QuestionAuthor] = mapped_column(str_enum(QuestionAuthor, "author"))
    answer_notes: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    interview: Mapped[Interview] = relationship(back_populates="questions")


class ProductionCalendarDay(Base):
    """Переопределения рабочих/нерабочих дней производственного календаря РФ (праздники и рабочие субботы)."""
    __tablename__ = "production_calendar_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    is_working_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    title: Mapped[str | None] = mapped_column(String(256))


class HandoffAttempt(Base):
    """Конкретная передача отклика получателю с замороженным снимком сводки и ожиданием ответа (workflow-01)."""
    __tablename__ = "handoff_attempts"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    stage_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stage_events.id", ondelete="SET NULL")
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    recipient_name: Mapped[str] = mapped_column(String(256))
    recipient_department: Mapped[str] = mapped_column(String(512))
    channel: Mapped[HandoffChannel] = mapped_column(str_enum(HandoffChannel, "channel"))
    handed_off_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    initial_due_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    reminder_date: Mapped[date] = mapped_column(Date)
    deadline_business_days: Mapped[int] = mapped_column(SmallInteger, default=10, server_default="10")
    reminder_business_day: Mapped[int] = mapped_column(SmallInteger, default=7, server_default="7")
    extensions_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at_column()
    summary_revision: Mapped[str] = mapped_column(String(64))
    summary_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[HandoffStatus] = mapped_column(
        str_enum(HandoffStatus, "status"),
        default=HandoffStatus.AWAITING_RESPONSE,
        server_default="awaiting_response",
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(128))
    closed_by_stage_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stage_events.id", ondelete="SET NULL")
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        Index(
            "uq_handoff_attempts_request_id",
            "request_id",
            unique=True,
            postgresql_where=sa_text("request_id IS NOT NULL"),
        ),
        Index(
            "ix_handoff_attempts_open_status",
            "status",
            "recipient_department",
            postgresql_where=sa_text("status = 'awaiting_response'"),
        ),
    )


class HandoffDeadlineExtension(Base):
    """Запись переноса срока ответа департамента кадровиком (исходный срок сохраняется на попытке)."""
    __tablename__ = "handoff_deadline_extensions"

    id: Mapped[uuid.UUID] = uuid_pk()
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handoff_attempts.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(SmallInteger)
    previous_due_date: Mapped[date] = mapped_column(Date)
    new_due_date: Mapped[date] = mapped_column(Date)
    previous_reminder_date: Mapped[date] = mapped_column(Date)
    new_reminder_date: Mapped[date] = mapped_column(Date)
    was_overdue: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reason_code: Mapped[DeadlineExtensionReason] = mapped_column(
        str_enum(DeadlineExtensionReason, "reason_code")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        CheckConstraint("seq >= 1", name="seq_positive"),
        Index(
            "uq_handoff_deadline_extensions_attempt_seq",
            "attempt_id",
            "seq",
            unique=True,
        ),
        Index(
            "uq_handoff_deadline_extensions_request_id",
            "request_id",
            unique=True,
            postgresql_where=sa_text("request_id IS NOT NULL"),
        ),
    )


class DepartmentFeedback(Base):
    """Итог рассмотрения кандидата департаментом — то, что сейчас теряется (проблема 6 кейса)."""
    __tablename__ = "department_feedback"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("handoff_attempts.id", ondelete="CASCADE"), index=True
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department_feedback.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    contact_status: Mapped[ProcessFactStatus] = mapped_column(
        str_enum(ProcessFactStatus, "contact_status"),
        default=ProcessFactStatus.NOT_REPORTED,
        server_default="not_reported",
    )
    interview_status: Mapped[ProcessFactStatus] = mapped_column(
        str_enum(ProcessFactStatus, "interview_status"),
        default=ProcessFactStatus.NOT_REPORTED,
        server_default="not_reported",
    )
    interview_held: Mapped[bool | None] = mapped_column(Boolean)
    outcome: Mapped[FeedbackOutcome] = mapped_column(
        str_enum(FeedbackOutcome, "outcome"),
        default=FeedbackOutcome.PENDING,
        server_default="pending",
    )
    # Коды подтверждённых компетенций: ["ИТК", "РК"].
    confirmed_competencies: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    gaps: Mapped[str | None] = mapped_column(Text)
    rejection_reason_code: Mapped[str | None] = mapped_column(ForeignKey("rejection_reasons.code"))
    keep_in_reserve: Mapped[bool | None] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text)
    response_channel: Mapped[HandoffChannel | None] = mapped_column(
        str_enum(HandoffChannel, "response_channel")
    )
    reported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reported_by_name: Mapped[str | None] = mapped_column(String(256))
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    received_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index(
            "uq_department_feedback_supersedes_id",
            "supersedes_id",
            unique=True,
            postgresql_where=sa_text("supersedes_id IS NOT NULL"),
        ),
        Index(
            "uq_department_feedback_attempt_revision",
            "attempt_id",
            "revision",
            unique=True,
            postgresql_where=sa_text("attempt_id IS NOT NULL"),
        ),
        Index(
            "uq_department_feedback_request_id",
            "request_id",
            unique=True,
            postgresql_where=sa_text("request_id IS NOT NULL"),
        ),
    )


class ReserveEntry(Base):
    """Кадровый резерв. Резерв — не этап отбора: кандидат может получить отказ
    на одну вакансию и одновременно остаться в резерве на должность или направление."""
    __tablename__ = "reserve_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    # Для какой должности резерв; пусто — резерв по направлению (competency_area).
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL")
    )
    competency_area: Mapped[str | None] = mapped_column(String(256))
    source_application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    # Обоснование профессиональной пригодности: почему человек нужен в резерве.
    reason: Mapped[str | None] = mapped_column(Text)
    # Основание повторного контакта: когда и зачем к нему вернуться [v1.8].
    contact_basis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReserveStatus] = mapped_column(
        str_enum(ReserveStatus, "status"), default=ReserveStatus.ACTIVE, server_default="active"
    )
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    added_at: Mapped[datetime] = created_at_column()
    valid_until: Mapped[date | None] = mapped_column(Date)
    # Как закончился период резерва: отзыв основания или истечение срока [v1.8].
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)
    ended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    candidate: Mapped[Candidate] = relationship()

    __table_args__ = (
        CheckConstraint(
            "position_id IS NOT NULL OR competency_area IS NOT NULL",
            name="has_target",
        ),
        # Одна активная запись на кандидата и цель [v1.8]. Цель — должность, если она указана,
        # иначе направление. Индексы держат правило и при двух одновременных запросах.
        Index(
            "uq_reserve_active_position",
            "candidate_id",
            "position_id",
            unique=True,
            postgresql_where=sa_text("status = 'active' AND position_id IS NOT NULL"),
        ),
        Index(
            "uq_reserve_active_area",
            "candidate_id",
            "competency_area",
            unique=True,
            postgresql_where=sa_text("status = 'active' AND position_id IS NULL"),
        ),
    )
