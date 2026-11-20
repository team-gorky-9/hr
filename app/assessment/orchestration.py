"""Application context around reusable candidate/profile assessments.

Transaction ownership stays with caller. A skipped application is an audited result,
never a negative candidate assessment. Explicit comparison never creates an application.
"""
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select

from app.assessment.applicability import Policy, resolve_applicability
from app.assessment.errors import AssessmentDomainError
from app.assessment.prompts import ASSESS_PROMPT_VERSION
from app.assessment.rules import parse_rule
from app.assessment.counters import validate_groups
from app.assessment.service import assess_candidate, _check_mode, _AS_OF
from app.assessment.version import ALGORITHM_VERSION
from app.db import repository as repo
from app.db.enums import AuditAction
from app.db.models import Application, Assessment, Candidate, CandidateCard, Position, RequirementProfile, Vacancy

Purpose = Literal['primary', 'comparison']


def preflight_application(application, *, candidate_id, position_code,
                          application_position_id, target_position_id, purpose: Purpose,
                          policy: Policy | None = None):
    if purpose not in ('primary', 'comparison'):
        raise AssessmentDomainError('bad_purpose', 'неизвестная цель оценки')
    if application is not None and application.candidate_id != candidate_id:
        raise AssessmentDomainError('application_owner', 'отклик принадлежит другому кандидату')
    if purpose == 'primary':
        if application is None or application.source == 'history' or application_position_id != target_position_id:
            raise AssessmentDomainError('not_primary_application', 'нужен прямой отклик на целевую должность')
    return resolve_applicability(position_code, application.posting_title if application else None, policy=policy)


def assess_in_context(session, *, candidate_id, llm, profile_id=None, mode='operational',
                      purpose: Purpose = 'primary', application_id=None, as_of=None, policy=None, registry=None,
                      expected_position_code=None):
    from app.postings import service as postings
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise AssessmentDomainError('not_found', 'кандидат не найден')
    if purpose not in ('primary', 'comparison'):
        raise AssessmentDomainError('bad_purpose', 'неизвестная цель оценки')
    if policy is not None:
        raise AssessmentDomainError('legacy_policy', 'Для основного отбора нужен справочник с контекстом происхождения')
    as_of = as_of or datetime.now(UTC).strftime('%Y-%m')
    if not _AS_OF.fullmatch(as_of):
        raise AssessmentDomainError('bad_as_of', 'as_of должен быть ГГГГ-ММ')
    application = session.get(Application, application_id) if application_id else None
    if application_id and application is None:
        raise AssessmentDomainError('application_not_found', 'отклик не найден')
    if application is not None and application.candidate_id != candidate_id:
        raise AssessmentDomainError('application_owner', 'отклик принадлежит другому кандидату')
    vacancy = session.get(Vacancy, application.vacancy_id) if application and application.vacancy_id else None
    resolution = None
    registry_snapshot = None
    if purpose == 'primary':
        if application is None or application.source != 'response':
            raise AssessmentDomainError('not_primary_application', 'нужен прямой отклик')
        registry = registry or postings.get_default_registry()
        registry_snapshot = registry.model_dump(mode='json')
        resolution = postings.resolve_application(session, application.id, registry=registry)
        if (resolution.position_code is not None and expected_position_code is not None
                and resolution.position_code != expected_position_code):
            raise AssessmentDomainError('position_mapping_mismatch', 'должность не соответствует решению о публикации')
        if resolution.ready and profile_id is not None and profile_id != resolution.profile_id:
            raise AssessmentDomainError('profile_mapping_mismatch', 'профиль не соответствует решению о публикации')
        profile_id = resolution.profile_id
    profile = session.get(RequirementProfile, profile_id) if profile_id else None
    if purpose == 'comparison' and profile is None:
        raise AssessmentDomainError('not_found', 'для повторного рассмотрения нужен профиль')
    if mode not in ('technical', 'operational'):
        raise AssessmentDomainError('bad_mode', 'неизвестный режим оценки')
    if mode == 'technical' and not candidate.is_synthetic:
        raise AssessmentDomainError('technical_mode_real_candidate', 'технический режим только для учебных кандидатов')
    if mode == 'operational' and candidate.is_synthetic:
        raise AssessmentDomainError('training_candidate', 'рабочий режим требует реального кандидата')
    if profile is not None:
        _check_mode(profile, mode, candidate=candidate)
        validate_groups(profile.competencies)
        for row in profile.formal_requirements:
            parse_rule(row.key, row.kind, row.params, row.verification)
    position = session.get(Position, profile.position_id) if profile else None
    applicability = postings.compatibility_applicability(resolution) if resolution else None
    text = repo.get_current_text(session, candidate_id)
    manifest = dict(schema_version='1.1', run_id=str(uuid.uuid4()), candidate_id=str(candidate_id),
        application_id=str(application_id) if application_id else None,
        application_source=str(application.source) if application else None,
        vacancy_id=str(vacancy.id) if vacancy else None,
        profile_id=str(profile.id) if profile else None, profile_version=profile.version if profile else None,
        position_code=resolution.position_code if resolution else position.code,
        posting_resolution=resolution.model_dump(mode='json') if resolution else None,
        registry_snapshot=registry_snapshot,
        candidate_text_id=str(text.id) if text else None, candidate_text_version=text.version if text else None,
        purpose=purpose, mode=mode, as_of=as_of, algorithm_version=ALGORITHM_VERSION,
        prompt_version=ASSESS_PROMPT_VERSION,
        applicability=applicability.model_dump(mode='json') if applicability else None)
    if purpose == 'primary' and not resolution.ready:
        manifest.update(status='skipped', reason=resolution.reason, assessment_id=None)
    else:
        cached = session.scalar(select(Assessment).join(CandidateCard, CandidateCard.id == Assessment.card_id).where(
            Assessment.candidate_id == candidate_id, Assessment.profile_id == profile.id,
            Assessment.is_current, Assessment.algorithm_version == ALGORITHM_VERSION,
            Assessment.prompt_version == ASSESS_PROMPT_VERSION, Assessment.calculation_as_of == as_of,
            CandidateCard.candidate_text_id == (text.id if text else None))) if text else None
        if cached is None:
            assessment_id = assess_candidate(session, candidate_id=candidate_id, profile_id=profile_id,
                llm=llm, mode=mode, as_of=as_of)
            cached = session.get(Assessment, assessment_id)
            reused = False
        else:
            reused = True
        card = session.get(CandidateCard, cached.card_id)
        manifest.update(status='ok', assessment_id=str(cached.id), assessment_version=cached.version,
                        card_id=str(cached.card_id), card_version=card.version, reused=reused,
                        formal_result=cached.formal_result.value)
    repo.write_audit(session, action=AuditAction.OTHER, entity_type='assessment_run',
                     entity_id=manifest['run_id'], details=manifest)
    return manifest
