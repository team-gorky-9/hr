"""interview guides, answer revisions, core rubric, confirm with answer

Контракт БД v2.1 (раздел 22), контракт гайда interview.md v0.4 §5, задача interview-01:
- interview_guides — версии гайда к встрече; встреча (interviews) остаётся одной на звонок,
  поэтому перегенерация гайда не создаёт ещё одну запись в отчётах о звонках;
- interviews: одна открытая встреча (result = pending) на пару (отклик, вид);
- interview_questions — вопрос версии гайда: вид (core / clarification), пробел, источники,
  критерий ответа, ссылка на рубрику ядра и на тот же вопрос прошлой версии;
- interview_answers — ревизии ответа (строки только добавляются);
- interview_rubric_questions — вопросы ядра, одни на версию профиля;
- assessments.base_assessment_id и confirm_request_id — базовая оценка версии из confirm
  и ключ повтора подтверждения;
- formal_checks.source_answer_id — на какой ответ опирался кадровик.

Номер 0009: в ветке задачи миграция была 0007; после слияния requirements-03 (0007_posting_sources)
и workflow-01 (0008) она идёт следом за 0008.

Перенос: каждая прежняя встреча получает гайд версии 1 без оценки (is_migrated), её вопросы
привязываются к нему, непустой answer_notes становится ревизией 1 с source = unknown.
Прежние версии оценки из confirm_formal_check получают ссылку на ближайшую предыдущую
версию той же пары, записанную моделью (все строки basis = resume).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Оценки: базовая версия и ключ повтора подтверждения -------------------------
    op.add_column('assessments', sa.Column('base_assessment_id', sa.UUID(), nullable=True))
    op.add_column('assessments', sa.Column('confirm_request_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f('fk_assessments_base_assessment_id_assessments'), 'assessments', 'assessments',
        ['base_assessment_id'], ['id'],
    )
    op.create_unique_constraint(op.f('uq_assessments_confirm_request_id'), 'assessments', ['confirm_request_id'])
    op.create_check_constraint(
        op.f('ck_assessments_confirm_request_has_base'), 'assessments',
        'confirm_request_id IS NULL OR base_assessment_id IS NOT NULL',
    )
    op.execute("""
        UPDATE assessments a SET base_assessment_id = (
            SELECT b.id FROM assessments b
            WHERE b.candidate_id = a.candidate_id AND b.profile_id = a.profile_id AND b.version < a.version
              AND NOT EXISTS (SELECT 1 FROM formal_checks f WHERE f.assessment_id = b.id AND f.basis <> 'resume')
            ORDER BY b.version DESC LIMIT 1)
        WHERE EXISTS (SELECT 1 FROM formal_checks f WHERE f.assessment_id = a.id AND f.basis <> 'resume')
    """)

    # --- Встреча: одна открытая на (отклик, вид) ---------------------------------------
    op.create_index(
        'uq_interviews_open', 'interviews', ['application_id', 'kind'], unique=True,
        postgresql_where=sa.text("result = 'pending'"),
    )

    # --- Версии гайда --------------------------------------------------------------------
    op.create_table(
        'interview_guides',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('interview_id', sa.UUID(), nullable=False),
        sa.Column('guide_version', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.UUID(), nullable=True),
        sa.Column('profile_id', sa.UUID(), nullable=True),
        sa.Column('rubric_version', sa.String(length=32), nullable=True),
        sa.Column('prompt_version', sa.String(length=64), nullable=True),
        sa.Column('model_calls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('uncovered_gaps', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('request_id', sa.UUID(), nullable=True),
        sa.Column('is_migrated', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'is_migrated OR (assessment_id IS NOT NULL AND profile_id IS NOT NULL)',
            name=op.f('ck_interview_guides_assessment_unless_migrated'),
        ),
        sa.CheckConstraint('guide_version >= 1', name=op.f('ck_interview_guides_guide_version_positive')),
        sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'],
                                name=op.f('fk_interview_guides_interview_id_interviews'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'],
                                name=op.f('fk_interview_guides_assessment_id_assessments'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['profile_id'], ['requirement_profiles.id'],
                                name=op.f('fk_interview_guides_profile_id_requirement_profiles'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'],
                                name=op.f('fk_interview_guides_created_by_user_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_guides')),
        sa.UniqueConstraint('interview_id', 'guide_version', name='uq_interview_guides_version'),
        sa.UniqueConstraint('request_id', name=op.f('uq_interview_guides_request_id')),
    )

    # --- Рубрика ядра ----------------------------------------------------------------------
    op.create_table(
        'interview_rubric_questions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('profile_id', sa.UUID(), nullable=False),
        sa.Column('row_key', sa.String(length=64), nullable=False),
        sa.Column('requirement_id', sa.UUID(), nullable=True),
        sa.Column('indicator_key', sa.String(length=64), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('criterion', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('author', sa.Enum('model', 'human', name='author', native_enum=False, length=32,
                                    create_constraint=True), nullable=False),
        sa.Column('status', sa.Enum('draft', 'approved', name='status', native_enum=False, length=32,
                                    create_constraint=True), server_default='draft', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('approved_by_user_id', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('(requirement_id IS NULL) <> (indicator_key IS NULL)',
                           name=op.f('ck_interview_rubric_questions_one_row_reference')),
        sa.CheckConstraint(
            "(status = 'approved') = (approved_at IS NOT NULL AND approved_by_user_id IS NOT NULL)",
            name=op.f('ck_interview_rubric_questions_approval_fields'),
        ),
        sa.ForeignKeyConstraint(['profile_id'], ['requirement_profiles.id'],
                                name=op.f('fk_interview_rubric_questions_profile_id_requirement_profiles'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_id'], ['formal_requirements.id'],
                                name=op.f('fk_interview_rubric_questions_requirement_id_formal_requirements'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'],
                                name=op.f('fk_interview_rubric_questions_approved_by_user_id_users'),
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_rubric_questions')),
        sa.UniqueConstraint('profile_id', 'row_key', name='uq_interview_rubric_questions_row'),
    )

    # --- Вопросы: версия гайда, вид, пробел, источники ---------------------------------------
    op.add_column('interview_questions', sa.Column('guide_id', sa.UUID(), nullable=True))
    op.add_column('interview_questions', sa.Column(
        'kind', sa.Enum('core', 'clarification', name='kind', native_enum=False, length=32, create_constraint=True),
        server_default='clarification', nullable=False,
    ))
    op.add_column('interview_questions', sa.Column('gap_ref_id', sa.String(length=32), nullable=True))
    op.add_column('interview_questions', sa.Column('criterion', postgresql.JSONB(astext_type=sa.Text()),
                                                   nullable=True))
    op.add_column('interview_questions', sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()),
                                                   server_default='[]', nullable=False))
    op.add_column('interview_questions', sa.Column('requirement_id', sa.UUID(), nullable=True))
    op.add_column('interview_questions', sa.Column('indicator_key', sa.String(length=64), nullable=True))
    op.add_column('interview_questions', sa.Column('rubric_question_id', sa.UUID(), nullable=True))
    op.add_column('interview_questions', sa.Column('carried_from_question_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_interview_questions_guide_id_interview_guides'), 'interview_questions',
                          'interview_guides', ['guide_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_interview_questions_requirement_id_formal_requirements'), 'interview_questions',
                          'formal_requirements', ['requirement_id'], ['id'])
    op.create_foreign_key(op.f('fk_interview_questions_rubric_question_id_interview_rubric_questions'),
                          'interview_questions', 'interview_rubric_questions', ['rubric_question_id'], ['id'])
    op.create_foreign_key(op.f('fk_interview_questions_carried_from_question_id_interview_questions'),
                          'interview_questions', 'interview_questions', ['carried_from_question_id'], ['id'])
    op.create_index('uq_interview_questions_gap', 'interview_questions', ['guide_id', 'gap_ref_id'], unique=True,
                    postgresql_where=sa.text('gap_ref_id IS NOT NULL'))
    op.create_check_constraint(
        op.f('ck_interview_questions_core_has_rubric'), 'interview_questions',
        "(kind = 'core') = (rubric_question_id IS NOT NULL AND gap_ref_id IS NULL)",
    )

    # --- Ревизии ответов ---------------------------------------------------------------------
    op.create_table(
        'interview_answers',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('question_id', sa.UUID(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source', sa.Enum('phone', 'in_person', 'written', 'unknown', name='source', native_enum=False,
                                    length=32, create_constraint=True), nullable=False),
        sa.Column('author_user_id', sa.UUID(), nullable=True),
        sa.Column('previous_answer_id', sa.UUID(), nullable=True),
        sa.Column('request_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('revision >= 1', name=op.f('ck_interview_answers_revision_positive')),
        sa.CheckConstraint(
            "(source = 'unknown' AND author_user_id IS NULL AND request_id IS NULL)"
            " OR (source <> 'unknown' AND author_user_id IS NOT NULL AND request_id IS NOT NULL)",
            name=op.f('ck_interview_answers_author_known'),
        ),
        sa.ForeignKeyConstraint(['question_id'], ['interview_questions.id'],
                                name=op.f('fk_interview_answers_question_id_interview_questions'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'],
                                name=op.f('fk_interview_answers_author_user_id_users'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['previous_answer_id'], ['interview_answers.id'],
                                name=op.f('fk_interview_answers_previous_answer_id_interview_answers')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_answers')),
        sa.UniqueConstraint('question_id', 'revision', name='uq_interview_answers_revision'),
        sa.UniqueConstraint('request_id', name=op.f('uq_interview_answers_request_id')),
    )

    # --- Строка оценки: на какой ответ опирался кадровик --------------------------------------
    op.add_column('formal_checks', sa.Column('source_answer_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_formal_checks_source_answer_id_interview_answers'), 'formal_checks',
                          'interview_answers', ['source_answer_id'], ['id'])
    op.create_check_constraint(op.f('ck_formal_checks_answer_only_confirmed'), 'formal_checks',
                               "source_answer_id IS NULL OR basis <> 'resume'")

    # --- Перенос прежних встреч и заметок ------------------------------------------------------
    op.execute("""
        INSERT INTO interview_guides (interview_id, guide_version, is_migrated, created_at)
        SELECT id, 1, true, created_at FROM interviews
    """)
    op.execute("""
        UPDATE interview_questions q SET guide_id = g.id, kind = 'clarification'
        FROM interview_guides g WHERE g.interview_id = q.interview_id AND g.is_migrated
    """)
    op.execute("""
        INSERT INTO interview_answers (question_id, revision, text, source)
        SELECT id, 1, answer_notes, 'unknown' FROM interview_questions
        WHERE answer_notes IS NOT NULL AND length(trim(answer_notes)) > 0
    """)
    op.alter_column('interview_questions', 'guide_id', nullable=False)


def downgrade() -> None:
    # Ответы возвращаются в answer_notes только для вопросов без заметки: последняя ревизия.
    op.execute("""
        UPDATE interview_questions q SET answer_notes = a.text
        FROM (SELECT DISTINCT ON (question_id) question_id, text FROM interview_answers
              ORDER BY question_id, revision DESC) a
        WHERE a.question_id = q.id AND q.answer_notes IS NULL
    """)
    op.drop_constraint(op.f('ck_formal_checks_answer_only_confirmed'), 'formal_checks', type_='check')
    op.drop_constraint(op.f('fk_formal_checks_source_answer_id_interview_answers'), 'formal_checks',
                       type_='foreignkey')
    op.drop_column('formal_checks', 'source_answer_id')

    op.drop_table('interview_answers')

    op.drop_constraint(op.f('ck_interview_questions_core_has_rubric'), 'interview_questions', type_='check')
    op.drop_index('uq_interview_questions_gap', table_name='interview_questions',
                  postgresql_where=sa.text('gap_ref_id IS NOT NULL'))
    for name in ('carried_from_question_id_interview_questions', 'rubric_question_id_interview_rubric_questions',
                 'requirement_id_formal_requirements', 'guide_id_interview_guides'):
        op.drop_constraint(op.f(f'fk_interview_questions_{name}'), 'interview_questions', type_='foreignkey')
    # Вопросы новых версий гайда (не из переноса) в прежней схеме — лишние строки той же встречи.
    op.execute("""
        DELETE FROM interview_questions q USING interview_guides g
        WHERE g.id = q.guide_id AND NOT g.is_migrated
    """)
    op.drop_constraint(op.f('ck_interview_questions_kind'), 'interview_questions', type_='check')
    for column in ('carried_from_question_id', 'rubric_question_id', 'indicator_key', 'requirement_id', 'sources',
                   'criterion', 'gap_ref_id', 'kind', 'guide_id'):
        op.drop_column('interview_questions', column)

    op.drop_table('interview_rubric_questions')
    op.drop_table('interview_guides')
    op.drop_index('uq_interviews_open', table_name='interviews', postgresql_where=sa.text("result = 'pending'"))

    op.drop_constraint(op.f('ck_assessments_confirm_request_has_base'), 'assessments', type_='check')
    op.drop_constraint(op.f('uq_assessments_confirm_request_id'), 'assessments', type_='unique')
    op.drop_constraint(op.f('fk_assessments_base_assessment_id_assessments'), 'assessments', type_='foreignkey')
    op.drop_column('assessments', 'confirm_request_id')
    op.drop_column('assessments', 'base_assessment_id')
