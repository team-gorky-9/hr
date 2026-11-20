"""Resolve response → scoped posting decision → position → approved profile.

No mutation on reads, no inference from a resume's first SourceDocument path.
Snapshot writes belong to the caller's transaction and never alter applications.
"""
import hashlib
import json
import uuid
from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.db import repository as repo
from app.db.enums import ApplicationSource, AuditAction
from app.db.models import Application, ApplicationPostingSource, AuditLog, Candidate, Position
from app.postings.registry import Registry, RegistryContext, Resolution, get_default_registry, resolve_posting


class ApplicationResolution(BaseModel):
    model_config = ConfigDict(frozen=True)
    application_id: uuid.UUID
    candidate_id: uuid.UUID
    is_training: bool
    mapping: Resolution
    position_id: uuid.UUID | None = None
    position_code: str | None = None
    profile_id: uuid.UUID | None = None
    profile_version: int | None = None
    ready: bool = False
    reason: str


def resolve_application(session, application_id, *, registry: Registry | None = None) -> ApplicationResolution:
    registry = registry or get_default_registry()
    application = session.get(Application, application_id)
    if application is None:
        raise ValueError('application_not_found')
    candidate = session.get(Candidate, application.candidate_id)
    sources = session.scalars(select(ApplicationPostingSource).where(
        ApplicationPostingSource.application_id == application.id)).all()
    contexts = [RegistryContext(dataset_id=s.dataset_id, dataset_sha256=s.dataset_sha256,
        channel=s.channel, source_folder=s.source_folder, is_synthetic=candidate.is_synthetic) for s in sources]
    mapping = resolve_posting(registry, posting_title=application.posting_title, contexts=contexts,
                              is_synthetic=candidate.is_synthetic)
    values = dict(application_id=application.id, candidate_id=candidate.id,
                  is_training=candidate.is_synthetic, mapping=mapping)
    if application.source != ApplicationSource.RESPONSE:
        return ApplicationResolution(**values, reason='not_response')
    if mapping.decision_state != 'confirmed':
        return ApplicationResolution(**values, reason=mapping.reason)
    position = session.scalar(select(Position).where(Position.code == mapping.position_code))
    if position is None:
        return ApplicationResolution(**values, reason='position_not_found')
    values.update(position_id=position.id, position_code=position.code)
    profile = repo.get_approved_profile(session, position.id, synthetic=candidate.is_synthetic)
    if profile is None:
        return ApplicationResolution(**values, reason='no_approved_profile')
    return ApplicationResolution(**values, profile_id=profile.id, profile_version=profile.version,
                                 ready=True, reason='ready')


def compatibility_applicability(resolution, imported_position_code=None, *, comparison_target=None):
    """Legacy field adapter; new decision_state remains a separate three-state model."""
    from app.assessment.applicability import Applicability
    mapping = resolution.mapping
    considered = comparison_target or imported_position_code
    different = (comparison_target is not None and mapping.decision_state == 'confirmed'
                 and mapping.position_code != comparison_target)
    mismatch = different or mapping.decision_state == 'no_matching_position' or (
        considered is not None and considered in mapping.excluded_position_codes)
    status = 'mismatch' if mismatch else ('confirmed' if mapping.decision_state == 'confirmed' else 'unresolved')
    return Applicability(status=status, reason='different_target' if different else resolution.reason,
        explanation='Повторное рассмотрение по другой должности.' if different else mapping.explanation,
        policy_version=mapping.registry_version, policy_hash=mapping.registry_hash,
        input_hash=mapping.input_hash, snapshot=mapping.model_dump(mode='json'))


def resolved_state(session, resolution, *, imported_position_code=None):
    from app.assessment.state import AssessmentState, AssessmentStatus, resolve_states
    if not resolution.ready:
        legacy = compatibility_applicability(resolution, imported_position_code)
        if legacy.status == 'mismatch' or resolution.reason == 'not_response':
            status = AssessmentStatus.NOT_APPLICABLE
        elif resolution.reason == 'no_approved_profile':
            status = AssessmentStatus.NO_APPROVED_PROFILE
        else:
            status = AssessmentStatus.MAPPING_REQUIRED
        return AssessmentState(status)
    from app.db.models import RequirementProfile
    return resolve_states(session, [resolution.candidate_id], session.get(RequirementProfile, resolution.profile_id),
                          resolution.position_id, resolution.is_training)[resolution.candidate_id]


def _hash(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def create_snapshot(session, application_ids, *, registry=None, actor_id=None):
    registry = registry or get_default_registry()
    ids = sorted({uuid.UUID(str(value)) for value in application_ids}, key=str)
    if not ids:
        raise ValueError('snapshot requires at least one response')
    rows = []
    for app_id in ids:
        application = session.get(Application, app_id)
        if application is None or application.source != ApplicationSource.RESPONSE:
            raise ValueError('snapshot accepts existing response applications only')
        resolution = resolve_application(session, app_id, registry=registry)
        text = repo.get_current_text(session, application.candidate_id)
        state = resolved_state(session, resolution)
        sources = session.scalars(select(ApplicationPostingSource).where(
            ApplicationPostingSource.application_id == app_id).order_by(ApplicationPostingSource.id)).all()
        rows.append(dict(application_id=str(app_id), candidate_id=str(application.candidate_id),
            imported_vacancy_id=str(application.vacancy_id) if application.vacancy_id else None,
            posting_title=application.posting_title, source=str(application.source),
            resolution=resolution.model_dump(mode='json'),
            candidate_text_id=str(text.id) if text else None, candidate_text_version=text.version if text else None,
            assessment_status=str(state.status),
            assessment_id=str(state.assessment.id) if state.assessment else None,
            assessment_version=state.assessment.version if state.assessment else None,
            provenance=[dict(id=str(s.id),dataset_id=s.dataset_id,dataset_sha256=s.dataset_sha256,
                channel=s.channel,source_folder=s.source_folder,source_sha256=s.source_sha256,
                source_path_hash=hashlib.sha256(s.source_path.encode('utf-8')).hexdigest()) for s in sources]))
    decision_counts = dict.fromkeys(('confirmed', 'needs_review', 'no_matching_position'), 0)
    decision_counts.update(Counter(row['resolution']['mapping']['decision_state'] for row in rows))
    ready_count = sum(row['resolution']['ready'] for row in rows)
    payload = dict(schema_version='posting-snapshot/1.0', snapshot_id=str(uuid.uuid4()),
        created_at=datetime.now(UTC).isoformat(), registry=registry.model_dump(mode='json'),
        registry_hash=registry.digest(), response_count=len(rows),
        candidate_record_count=len({r['candidate_id'] for r in rows}),
        decision_counts=decision_counts, ready_count=ready_count, blocked_count=len(rows)-ready_count,
        reason_counts=dict(Counter(row['resolution']['reason'] for row in rows)), rows=rows)
    payload['snapshot_hash'] = _hash(payload)
    repo.write_audit(session, action=AuditAction.OTHER, entity_type='posting_snapshot',
                     entity_id=payload['snapshot_id'], details=payload, user_id=actor_id)
    return payload


def read_snapshot(session, snapshot_id):
    snapshot_id = str(uuid.UUID(str(snapshot_id)))
    row = session.scalar(select(AuditLog).where(AuditLog.entity_type == 'posting_snapshot',
                                               AuditLog.entity_id == snapshot_id))
    if row is None:
        raise ValueError('snapshot_not_found')
    payload = dict(row.details)
    checksum = payload.pop('snapshot_hash')
    if _hash(payload) != checksum:
        raise ValueError('snapshot_hash_mismatch')
    return payload | {'snapshot_hash': checksum}
