"""requirement profiles: one format for all positions

Единый формат профиля требований (контракт БД v1.1, п. 4.3):
- источники версии профиля — таблица requirement_profile_sources;
- у формальных требований, компетенций и индикаторов — устойчивый ключ строки и её
  происхождение (origin, список ссылок на документы с адресом и цитатой или обоснование);
  столбец formal_requirements.source_quote заменён списком source_refs;
- у индикаторов и формальных требований — способ проверки и критерии выполнения (acceptance);
  у индикаторов — обязательность и признак исключения из оценки;
- ранг и эталонный уровень компетенции необязательны (есть только в матрице заказчика);
- у профиля — признак учебного профиля и основание утверждения.

Строки, созданные до этой миграции, получают origin = 'team' с пометкой (в неё же
переносится прежняя цитата формального требования), ключ «legacy.<начало id>»
и verification = 'resume': источника у них не было.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROW_TABLES = ('formal_requirements', 'competencies', 'competency_indicators')
LEGACY_NOTE = 'создано до миграции 0002, источник не указан'
ROW_SOURCE_CHECK = (
    "(origin = 'source' AND jsonb_array_length(source_refs) > 0)"
    " OR (origin = 'team' AND note IS NOT NULL)"
)
KEY_UNIQUE = {
    'formal_requirements': ('profile_id', 'uq_formal_requirements_profile_key'),
    'competencies': ('profile_id', 'uq_competencies_profile_key'),
    'competency_indicators': ('competency_id', 'uq_competency_indicators_competency_key'),
}


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    op.create_table('requirement_profile_sources',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('profile_id', sa.UUID(), nullable=False),
    sa.Column('source_document_id', sa.UUID(), nullable=False),
    sa.Column('role', _enum('job_description', 'competency_matrix', 'vacancy_posting', 'regulation', 'other', name='role'), nullable=False),
    sa.Column('observed_revision', sa.String(length=128), nullable=True),
    sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['requirement_profiles.id'], name=op.f('fk_requirement_profile_sources_profile_id_requirement_profiles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_documents.id'], name=op.f('fk_requirement_profile_sources_source_document_id_source_documents'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_requirement_profile_sources')),
    sa.UniqueConstraint('profile_id', 'source_document_id', name='uq_requirement_profile_sources_document')
    )

    op.add_column('requirement_profiles', sa.Column('is_synthetic', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('requirement_profiles', sa.Column('approval_basis', sa.Text(), nullable=True))

    # Ключ и происхождение строки — у трёх таблиц одинаково. Сначала столбцы допускают NULL,
    # затем старые строки заполняются, затем NOT NULL, уникальность и проверка.
    for table in ROW_TABLES:
        op.add_column(table, sa.Column('key', sa.String(length=64), nullable=True))
        op.add_column(table, sa.Column('origin', _enum('source', 'team', name='origin'), nullable=True))
        op.add_column(table, sa.Column('source_refs', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
        op.add_column(table, sa.Column('note', sa.Text(), nullable=True))
        legacy_note = "'" + LEGACY_NOTE + "'"
        if table == 'formal_requirements':  # прежняя цитата без документа сохраняется в пометке
            legacy_note = legacy_note + " || coalesce('; цитата: ' || source_quote, '')"
        op.execute(f"UPDATE {table} SET origin = 'team', note = {legacy_note},"
                   f" key = 'legacy.' || left(id::text, 8)")
        op.alter_column(table, 'key', nullable=False)
        op.alter_column(table, 'origin', nullable=False)
        parent, name = KEY_UNIQUE[table]
        op.create_unique_constraint(name, table, [parent, 'key'])
        op.create_check_constraint(op.f(f'ck_{table}_row_source'), table, ROW_SOURCE_CHECK)
    op.drop_column('formal_requirements', 'source_quote')

    for table in ('formal_requirements', 'competency_indicators'):
        op.add_column(table, sa.Column('verification', _enum('resume', 'documents', 'interview', 'test', name='verification'), nullable=True))
        op.execute(f"UPDATE {table} SET verification = 'resume'")
        op.alter_column(table, 'verification', nullable=False)
        op.add_column(table, sa.Column('acceptance', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    op.add_column('competency_indicators', sa.Column('is_mandatory', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('competency_indicators', sa.Column('excluded_from_scoring', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    # Ранг и эталон — справочно, только из матрицы заказчика.
    op.alter_column('competencies', 'rank', existing_type=sa.VARCHAR(length=32), nullable=True)
    op.alter_column('competencies', 'target_level_min', existing_type=sa.SMALLINT(), nullable=True)
    op.alter_column('competencies', 'target_level_max', existing_type=sa.SMALLINT(), nullable=True)
    op.drop_constraint(op.f('ck_competencies_target_level_range'), 'competencies', type_='check')
    op.create_check_constraint(
        op.f('ck_competencies_target_level_range'), 'competencies',
        "(target_level_min IS NULL AND target_level_max IS NULL)"
        " OR (target_level_min >= 0 AND target_level_min <= target_level_max AND target_level_max <= 100)",
    )


def downgrade() -> None:
    # Откат возможен, только если у всех компетенций есть ранг и эталон.
    op.drop_constraint(op.f('ck_competencies_target_level_range'), 'competencies', type_='check')
    op.create_check_constraint(
        op.f('ck_competencies_target_level_range'), 'competencies',
        "target_level_min >= 0 AND target_level_min <= target_level_max AND target_level_max <= 100",
    )
    op.alter_column('competencies', 'target_level_max', existing_type=sa.SMALLINT(), nullable=False)
    op.alter_column('competencies', 'target_level_min', existing_type=sa.SMALLINT(), nullable=False)
    op.alter_column('competencies', 'rank', existing_type=sa.VARCHAR(length=32), nullable=False)

    op.drop_column('competency_indicators', 'excluded_from_scoring')
    op.drop_column('competency_indicators', 'is_mandatory')
    for table in ('formal_requirements', 'competency_indicators'):
        op.drop_column(table, 'acceptance')
        op.drop_constraint(op.f(f'ck_{table}_verification'), table, type_='check')
        op.drop_column(table, 'verification')

    op.add_column('formal_requirements', sa.Column('source_quote', sa.Text(), nullable=True))
    op.execute("UPDATE formal_requirements SET source_quote = source_refs -> 0 ->> 'quote'")
    for table in ROW_TABLES:
        op.drop_constraint(op.f(f'ck_{table}_row_source'), table, type_='check')
        op.drop_constraint(KEY_UNIQUE[table][1], table, type_='unique')
        op.drop_constraint(op.f(f'ck_{table}_origin'), table, type_='check')
        op.drop_column(table, 'note')
        op.drop_column(table, 'source_refs')
        op.drop_column(table, 'origin')
        op.drop_column(table, 'key')

    op.drop_column('requirement_profiles', 'approval_basis')
    op.drop_column('requirement_profiles', 'is_synthetic')
    op.drop_table('requirement_profile_sources')
