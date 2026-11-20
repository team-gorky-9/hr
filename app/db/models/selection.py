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
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false as sa_false,
    func,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.db.enums import (
    AnswerSource,
    ApplicationSource,
    FeedbackOutcome,
    InterviewKind,
    InterviewQuestionKind,
    InterviewResult,
    QuestionAuthor,
    RejectionSide,
    ReserveStatus,
    RubricStatus,
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

    __table_args__ = (
        # [v1.9] Одна открытая встреча на пару (отклик, вид). Гайд — отдельная запись
        # (interview_guides): перегенерация не создаёт ещё один «звонок» в отчётах.
        Index(
            "uq_interviews_open",
            "application_id",
            "kind",
            unique=True,
            postgresql_where=sa_text("result = 'pending'"),
        ),
    )


class InterviewGuide(Base):
    """Версия гайда к встрече [v1.9]: снимок вопросов, собранных по одной базовой оценке.

    Перегенерация создаёт новую версию той же встречи; прежняя читается по номеру.
    """
    __tablename__ = "interview_guides"

    id: Mapped[uuid.UUID] = uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    guide_version: Mapped[int] = mapped_column(Integer)
    # Базовая оценка сборки: версия из save_assessment (вывод модели по резюме), а не из confirm.
    # CASCADE: гайд принадлежит паре «кандидат × профиль»; при удалении кандидата его оценки и отклики
    # удаляются разными цепочками каскада, и ссылка без CASCADE проверялась бы раньше, чем дойдёт до гайда.
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requirement_profiles.id", ondelete="CASCADE"))
    # Отпечаток строк рубрики ядра, вошедших в гайд: (row_key, version, status).
    rubric_version: Mapped[str | None] = mapped_column(String(32))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    model_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Пробелы сверх бюджета и не сгенерированные: [{"gap_ref_id", "title", "reason"}].
    uncovered_gaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    # Версия создана миграцией 0007 из старых interviews: оценки, по которой собрана, нет.
    is_migrated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_column()

    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="guide", order_by="InterviewQuestion.sort_order"
    )

    __table_args__ = (
        UniqueConstraint("interview_id", "guide_version", name="uq_interview_guides_version"),
        CheckConstraint(
            "is_migrated OR (assessment_id IS NOT NULL AND profile_id IS NOT NULL)", name="assessment_unless_migrated"
        ),
        CheckConstraint("guide_version >= 1", name="guide_version_positive"),
    )


class InterviewRubricQuestion(Base):
    """Вопрос общего ядра для строки профиля этапа interview [v1.9].

    Генерируется один раз на версию профиля, поэтому у всех кандидатов одинаков.
    Ровно одна ссылка: на формальное требование или на ключ индикатора компетенции.
    """
    __tablename__ = "interview_rubric_questions"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement_profiles.id", ondelete="CASCADE"))
    row_key: Mapped[str] = mapped_column(String(64))
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("formal_requirements.id", ondelete="CASCADE"))
    indicator_key: Mapped[str | None] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    # {"good_answer": "...", "insufficient_answer": "..."}
    criterion: Mapped[dict[str, Any]] = mapped_column(JSONB)
    author: Mapped[QuestionAuthor] = mapped_column(str_enum(QuestionAuthor, "author"))
    status: Mapped[RubricStatus] = mapped_column(
        str_enum(RubricStatus, "status"), default=RubricStatus.DRAFT, server_default="draft"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint("profile_id", "row_key", name="uq_interview_rubric_questions_row"),
        CheckConstraint("(requirement_id IS NULL) <> (indicator_key IS NULL)", name="one_row_reference"),
        CheckConstraint(
            "(status = 'approved') = (approved_at IS NOT NULL AND approved_by_user_id IS NOT NULL)",
            name="approval_fields",
        ),
    )


class InterviewQuestion(Base):
    """Вопрос интервью. Привязан к компетенции или к пробелу в резюме, чтобы
    разных кандидатов проверяли по одним критериям.

    [v1.9] Вопрос принадлежит версии гайда (guide_id). Вопрос ядра ссылается на строку рубрики,
    уточнение — на пробел (gap_ref_id). Ответы — в interview_answers с ревизиями;
    answer_notes больше не пишется (перенесён миграцией 0007).
    """
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    guide_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_guides.id", ondelete="CASCADE"))
    kind: Mapped[InterviewQuestionKind] = mapped_column(
        str_enum(InterviewQuestionKind, "kind"),
        default=InterviewQuestionKind.CLARIFICATION,
        server_default="clarification",
    )
    competency_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competencies.id", ondelete="SET NULL")
    )
    # Заголовок пробела: «не указан опыт работы с обращениями граждан».
    gap: Mapped[str | None] = mapped_column(Text)
    gap_ref_id: Mapped[str | None] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    # {"good_answer": "...", "insufficient_answer": "..."}
    criterion: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Откуда вопрос: [{"type": "formal_check" | "indicator" | "group" | "card_missing" | "profile_row", ...}]
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("formal_requirements.id"))
    indicator_key: Mapped[str | None] = mapped_column(String(64))
    rubric_question_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_rubric_questions.id"))
    # Тот же пробел или та же строка ядра в прошлой версии гайда: её ответ показывается как перенесённый.
    carried_from_question_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_questions.id"))
    author: Mapped[QuestionAuthor] = mapped_column(str_enum(QuestionAuthor, "author"))
    answer_notes: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    interview: Mapped[Interview] = relationship(back_populates="questions")
    guide: Mapped[InterviewGuide] = relationship(back_populates="questions")

    __table_args__ = (
        Index(
            "uq_interview_questions_gap",
            "guide_id",
            "gap_ref_id",
            unique=True,
            postgresql_where=sa_text("gap_ref_id IS NOT NULL"),
        ),
        CheckConstraint(
            "(kind = 'core') = (rubric_question_id IS NOT NULL AND gap_ref_id IS NULL)", name="core_has_rubric"
        ),
    )


class InterviewAnswer(Base):
    """Ревизия ответа кандидата на вопрос [v1.9]. Строки только добавляются:
    исправление — новая ревизия, прежняя читается."""
    __tablename__ = "interview_answers"

    id: Mapped[uuid.UUID] = uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[AnswerSource] = mapped_column(str_enum(AnswerSource, "source"))
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # Исправленная ревизия; у первой ревизии перенесённого вопроса — ответ прежнего вопроса.
    previous_answer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_answers.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint("question_id", "revision", name="uq_interview_answers_revision"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        # Автор и ключ запроса неизвестны только у ответов, перенесённых из answer_notes.
        CheckConstraint(
            "(source = 'unknown' AND author_user_id IS NULL AND request_id IS NULL)"
            " OR (source <> 'unknown' AND author_user_id IS NOT NULL AND request_id IS NOT NULL)",
            name="author_known",
        ),
    )


class DepartmentFeedback(Base):
    """Итог рассмотрения кандидата департаментом — то, что сейчас теряется (проблема 6 кейса)."""
    __tablename__ = "department_feedback"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
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
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    received_at: Mapped[datetime] = created_at_column()


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
