"""Requirements operations: caller owns the transaction, each write owns a savepoint."""
from contextlib import contextmanager
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import repository as repo
from app.db.enums import RequirementStatus, UserRole
from app.db.models import Position, RequirementProfile, SourceDocument, User
from .errors import RequirementError, invalid
from .schemas import validate_draft


@contextmanager
def atomic(session):
    try:
        with session.begin_nested():
            yield
    except IntegrityError as error:
        constraint = getattr(getattr(error.orig, 'diag', None), 'constraint_name', None)
        code = 'version_conflict' if constraint == 'uq_requirement_profiles_version' else 'database_constraint'
        raise RequirementError(code, 'Запись конфликтует с ограничениями БД; операция отменена.') from error
    except repo.RepositoryError as error:
        raise invalid() from error


def lock_position(session, *, code=None, position_id=None):
    condition = Position.code == code if code is not None else Position.id == position_id
    position = session.scalar(select(Position).where(condition).with_for_update())
    if position is None:
        raise RequirementError('position_not_found', 'Должность не найдена.', 'position_code')
    return position


def quote_in_document(quote: str, text: str) -> bool:
    """A profile quote may join nonadjacent source paragraphs with newlines.

    Keep each fragment verbatim and in source order. Package imports additionally
    verify the explicit paragraph IDs against the original document bytes.
    """
    offset = 0
    for fragment in quote.splitlines():
        start = text.find(fragment, offset)
        if start < 0:
            return False
        offset = start + len(fragment)
    return bool(quote.strip())


def create_validated(session, draft, *, created_by, version=None):
    if not isinstance(created_by, str) or not created_by.strip() or len(created_by.strip()) > 128:
        raise invalid('created_by')
    position = lock_position(session, code=draft.position_code)
    if version is not None and session.scalar(select(RequirementProfile.id).where(
        RequirementProfile.position_id == position.id,
        RequirementProfile.is_synthetic == draft.is_synthetic,
        RequirementProfile.version == version,
    )) is not None:
        raise RequirementError('version_conflict', 'Версия пакета уже загружена; используйте новую версию.')
    documents = {}
    for source in draft.sources:
        document = session.get(SourceDocument, source.source_document_id)
        if document is None:
            raise RequirementError('source_not_found', 'Исходный документ не зарегистрирован.', 'sources')
        documents[document.id] = document
    for row in [*draft.formal_requirements, *draft.competencies, *(r for c in draft.competencies for r in c.indicators)]:
        for ref in row.source_refs:
            document = documents.get(ref.source_document_id)
            if document is None or not quote_in_document(ref.quote, document.raw_text or ''):
                raise RequirementError('source_mismatch', 'Цитата не подтверждается источником профиля.', 'source_refs')
    return repo.create_requirement_profile(
        session, position_id=position.id, created_by=created_by.strip(), version=version,
        is_synthetic=draft.is_synthetic, sources=draft.sources, formal_requirements=draft.formal_requirements,
        competencies=draft.competencies, note=draft.note,
    )


def load_profile_draft(session, data, *, created_by):
    draft = validate_draft(data)
    with atomic(session):
        return create_validated(session, draft, created_by=created_by)


def approve_profile(session, profile_id: uuid.UUID, *, approved_by_user_id: uuid.UUID, approval_basis: str):
    with atomic(session):
        profile = session.get(RequirementProfile, profile_id)
        user = session.get(User, approved_by_user_id)
        if profile is None:
            raise RequirementError('profile_not_found', 'Профиль не найден.')
        lock_position(session, position_id=profile.position_id)
        session.refresh(profile)
        if user is not None:
            session.refresh(user)
        if (profile.status != RequirementStatus.DRAFT or user is None or not user.is_active
                or user.role not in (UserRole.HR, UserRole.ADMIN)
                or not isinstance(approval_basis, str) or not approval_basis.strip()):
            raise RequirementError('approval_refused', 'Нужны черновик, активный HR/admin и непустое основание.')
        return repo.approve_requirement_profile(session, profile.id,
            approved_by_user_id=user.id, approval_basis=approval_basis)


def get_approved_profile(session, position_id: uuid.UUID, *, synthetic=False):
    return repo.get_approved_profile(session, position_id, synthetic=synthetic)
