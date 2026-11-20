"""contours of real and training data, result basis, alternatives, check_stage

Контракт БД v1.5 (раздел 16):
- учебный и рабочий контуры: признак is_synthetic у кандидата; у профиля версии и
  утверждённая версия считаются отдельно в каждом контуре; признак после создания
  не меняется (триггер);
- check_stage у формальных требований и индикаторов: screening | interview.
  Существующие строки: verification interview/test → interview, иначе screening;
- у результата формального требования: фактическое основание basis, признак
  предварительного результата, результаты альтернатив по ключам, кто подтвердил
  результат не по резюме; у оценки — признак предварительного допуска.

Существующие оценки получают basis = 'resume' (до этой миграции их писала только модель)
и is_preliminary = false: правило v1.3 уже понизило их met до unknown, отмечать нечего.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGE_TABLES = ('formal_requirements', 'competency_indicators')
SYNTHETIC_TABLES = ('candidates', 'requirement_profiles')
CHECK_STAGE_RULE = "check_stage = 'interview' OR verification IN ('resume', 'documents')"
BASIS_RULE = (
    "(basis = 'resume' AND confirmed_by_user_id IS NULL)"
    " OR (basis <> 'resume' AND confirmed_by_user_id IS NOT NULL"
    " AND jsonb_array_length(evidence) = 0 AND jsonb_array_length(alternatives) = 0)"
)


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    # --- Контуры -------------------------------------------------------------
    op.add_column('candidates', sa.Column('is_synthetic', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    op.drop_constraint('uq_requirement_profiles_version', 'requirement_profiles', type_='unique')
    op.create_unique_constraint(
        'uq_requirement_profiles_version', 'requirement_profiles', ['position_id', 'is_synthetic', 'version'],
    )
    op.drop_index('uq_requirement_profiles_approved', table_name='requirement_profiles',
                  postgresql_where=sa.text("status = 'approved'"))
    op.create_index('uq_requirement_profiles_approved', 'requirement_profiles', ['position_id', 'is_synthetic'],
                    unique=True, postgresql_where=sa.text("status = 'approved'"))

    # Признак контура меняться не может: иначе утверждённый учебный профиль стал бы рабочим,
    # а оценка реального кандидата — учебной. Функций смены нет, триггер закрывает прямой UPDATE.
    op.execute("""
        CREATE FUNCTION forbid_is_synthetic_change() RETURNS trigger AS $$
        BEGIN
            IF NEW.is_synthetic IS DISTINCT FROM OLD.is_synthetic THEN
                RAISE EXCEPTION 'is_synthetic в % не меняется после создания', TG_TABLE_NAME
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in SYNTHETIC_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_is_synthetic BEFORE UPDATE OF is_synthetic ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION forbid_is_synthetic_change()"
        )

    # --- Этап проверки строки профиля ------------------------------------------
    for table in STAGE_TABLES:
        op.add_column(table, sa.Column('check_stage', _enum('screening', 'interview', name='check_stage'),
                                       server_default='screening', nullable=False))
        op.execute(f"UPDATE {table} SET check_stage = 'interview' WHERE verification IN ('interview', 'test')")
        op.create_check_constraint(op.f(f'ck_{table}_check_stage_verification'), table, CHECK_STAGE_RULE)

    # --- Основание результата и альтернативы -------------------------------------
    op.add_column('formal_checks', sa.Column('basis', _enum('resume', 'documents', 'interview', 'test', name='basis'),
                                             server_default='resume', nullable=False))
    op.add_column('formal_checks', sa.Column('is_preliminary', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('assessments', sa.Column('formal_preliminary', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('formal_checks', sa.Column('alternatives', postgresql.JSONB(astext_type=sa.Text()),
                                             server_default='[]', nullable=False))
    op.add_column('formal_checks', sa.Column('confirmed_by_user_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_formal_checks_confirmed_by_user_id_users'), 'formal_checks', 'users',
                          ['confirmed_by_user_id'], ['id'], ondelete='RESTRICT')
    op.create_check_constraint(op.f('ck_formal_checks_basis_confirmation'), 'formal_checks', BASIS_RULE)


def downgrade() -> None:
    # Откат теряет основание и альтернативы. Строки, подтверждённые человеком, откат не
    # переносит: прежняя схема не умеет их отличить от вывода модели — откат отклоняется.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM formal_checks WHERE basis <> 'resume') THEN
                RAISE EXCEPTION 'есть результаты, подтверждённые не по резюме: откат 0003 сотрёт основание';
            END IF;
        END $$
    """)
    op.drop_constraint(op.f('ck_formal_checks_basis_confirmation'), 'formal_checks', type_='check')
    op.drop_constraint(op.f('fk_formal_checks_confirmed_by_user_id_users'), 'formal_checks', type_='foreignkey')
    op.drop_column('formal_checks', 'confirmed_by_user_id')
    op.drop_column('formal_checks', 'alternatives')
    op.drop_column('assessments', 'formal_preliminary')
    op.drop_column('formal_checks', 'is_preliminary')
    op.drop_constraint(op.f('ck_formal_checks_basis'), 'formal_checks', type_='check')
    op.drop_column('formal_checks', 'basis')

    for table in STAGE_TABLES:
        op.drop_constraint(op.f(f'ck_{table}_check_stage_verification'), table, type_='check')
        op.drop_constraint(op.f(f'ck_{table}_check_stage'), table, type_='check')
        op.drop_column(table, 'check_stage')

    for table in SYNTHETIC_TABLES:
        op.execute(f"DROP TRIGGER trg_{table}_is_synthetic ON {table}")
    op.execute("DROP FUNCTION forbid_is_synthetic_change()")

    # Откат к общей нумерации и одному утверждённому профилю на должность возможен,
    # только если учебные и рабочие профили не пересекаются — иначе база откажет.
    op.drop_index('uq_requirement_profiles_approved', table_name='requirement_profiles',
                  postgresql_where=sa.text("status = 'approved'"))
    op.create_index('uq_requirement_profiles_approved', 'requirement_profiles', ['position_id'],
                    unique=True, postgresql_where=sa.text("status = 'approved'"))
    op.drop_constraint('uq_requirement_profiles_version', 'requirement_profiles', type_='unique')
    op.create_unique_constraint('uq_requirement_profiles_version', 'requirement_profiles', ['position_id', 'version'])
    op.drop_column('candidates', 'is_synthetic')
