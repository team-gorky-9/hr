"""Public requirements boundary: real schemas, files, transactions and PostgreSQL.

These catch silent version replacement, lost provenance, implicit approval,
partial writes, leaked errors and accidental dependency on the evaluator.
"""
from contextlib import nullcontext
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import func, select

from app.db.enums import RequirementStatus, UserRole
from app.db.models import RequirementProfile, SourceDocument, User
from tests import factories as f

ROOT = Path(__file__).resolve().parents[1]


def public():
    assert importlib.util.find_spec('app.requirements') is not None, 'public requirements module is missing'
    from app import requirements
    return requirements


def draft():
    return {
        'schema_version': 'requirement-draft/1.0', 'position_code': 'python-dev', 'is_synthetic': True,
        'formal_requirements': [{'key': 'demo.experience', 'kind': 'experience', 'description': '24 months',
            'params': {'schema_version': '0.1', 'scope': 'total_commercial', 'minimum_defined': True, 'min_months': 24},
            'is_mandatory': True, 'verification': 'resume', 'origin': 'team', 'note': 'synthetic rule'}],
        'competencies': [{'key': 'demo.testing', 'code': 'TEST', 'name': 'API tests', 'origin': 'team',
            'note': 'synthetic indicator', 'indicators': [{'key': 'demo.api', 'text': 'Писал API-тесты',
                'verification': 'resume', 'origin': 'team', 'note': 'synthetic indicator'}]}],
    }


def test_draft_rejects_fixed_version_and_unknown_rule_without_echoing_values():
    api = public()
    data = draft()
    data['version'] = 5
    with pytest.raises(api.RequirementError) as caught:
        api.validate_draft(data)
    assert caught.value.code == 'invalid_profile'
    data = draft()
    data['formal_requirements'][0]['params']['SECRET_VALUE'] = 'PRIVATE_CONTENT'
    with pytest.raises(api.RequirementError) as caught:
        api.validate_draft(data)
    assert 'PRIVATE_CONTENT' not in str(caught.value)
    assert 'SECRET_VALUE' not in str(caught.value)


def test_draft_checks_nested_fields_and_types():
    api = public()
    for mutate in [
        lambda d: d.update(is_synthetic='false'),
        lambda d: d['formal_requirements'][0].update(is_mandatory='false'),
        lambda d: d['competencies'][0].update(target_level_min=90, target_level_max=80),
        lambda d: d['competencies'][0]['indicators'][0].update(typo=True),
        lambda d: d['competencies'].append(deepcopy(d['competencies'][0])),
    ]:
        data = draft()
        mutate(data)
        with pytest.raises(api.RequirementError):
            api.validate_draft(data)


def test_cli_help_and_bad_json_work_without_database(tmp_path):
    public()
    result = subprocess.run([sys.executable, '-m', 'app.requirements', '--help'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0
    bad = tmp_path / 'bad.json'
    bad.write_text('{"position_code":"x","position_code":"y"}', encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'app.requirements', 'load', str(bad)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['error']['code'] == 'invalid_json'
    assert 'Traceback' not in result.stderr


def test_invalid_source_path_is_domain_error_without_database(tmp_path):
    api = public()
    from app.requirements.package import validate_sources
    manifest = {'documents': [{'id': 'di', 'path': 'bad\u0000.txt', 'sha256': '0' * 64,
                               'kind': 'job_description', 'paragraphs': {}}]}
    with pytest.raises(api.RequirementError):
        validate_sources(manifest, tmp_path)


def test_lifecycle_keeps_contours_and_caller_transaction(session):
    api = public()
    user = f.make_user(session)
    working = f.make_profile(session, 'python-dev', is_synthetic=False)
    f.approve(session, working, user)
    first = api.load_profile_draft(session, draft(), created_by='tester')
    assert first.version == 1 and first.status == RequirementStatus.DRAFT
    api.approve_profile(session, first.id, approved_by_user_id=user.id, approval_basis='test')
    second = api.load_profile_draft(session, draft(), created_by='tester')
    assert second.version == 2 and second.status == RequirementStatus.DRAFT
    assert api.get_approved_profile(session, first.position_id, synthetic=True).id == first.id
    api.approve_profile(session, second.id, approved_by_user_id=user.id, approval_basis='new test')
    session.refresh(first)
    assert first.status == RequirementStatus.ARCHIVED
    assert api.get_approved_profile(session, second.position_id).id == working.id
    assert api.get_approved_profile(session, second.position_id, synthetic=True).id == second.id
    with pytest.raises(api.RequirementError) as caught:
        api.approve_profile(session, first.id, approved_by_user_id=user.id, approval_basis='again')
    assert caught.value.code == 'approval_refused'
    session.rollback()
    assert session.scalar(select(func.count()).select_from(RequirementProfile)) == 0


def test_unknown_position_is_domain_error_and_session_survives(session):
    api = public()
    data = draft()
    data['position_code'] = 'missing'
    with pytest.raises(api.RequirementError) as caught:
        api.load_profile_draft(session, data, created_by='test')
    assert caught.value.code == 'position_not_found'
    assert api.load_profile_draft(session, draft(), created_by='test').version == 1


@pytest.mark.parametrize('commit,approve,role,want', [
    (False, False, UserRole.HR, 'dry_run'),
    (True, False, UserRole.HR, 'loaded'),
    (True, True, UserRole.HR, 'loaded'),
    (True, True, UserRole.DEPARTMENT, 'refused'),
])
def test_cli_load_is_atomic_and_explicit(session, monkeypatch, tmp_path, capsys, commit, approve, role, want):
    public()
    from app.requirements.cli import main
    from app.db import session as db_session
    user = f.make_user(session, role=role)
    session.commit()
    def user_snapshot():
        return set(session.execute(select(User.id, User.login, User.role, User.is_active, User.full_name)).all())
    users_before = user_snapshot()
    monkeypatch.setattr(db_session, 'SessionLocal', lambda: nullcontext(session))
    path = tmp_path / 'draft.json'
    path.write_text(json.dumps(draft()), encoding='utf-8')
    args = ['load', str(path)]
    if commit:
        args.append('--commit')
    if approve:
        args += ['--approve', '--approver', user.login, '--basis', 'test']
    assert main(args) == (1 if want == 'refused' else 0)
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == want
    rows = session.scalars(select(RequirementProfile)).all()
    assert len(rows) == (1 if want == 'loaded' else 0)
    if rows:
        assert rows[0].status == (RequirementStatus.APPROVED if approve else RequirementStatus.DRAFT)
    assert user_snapshot() == users_before


def package_inputs(tmp_path):
    import hashlib
    body = 'Высшее образование'
    (tmp_path / 'source.txt').write_bytes(body.encode('utf-8'))
    sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
    source = {'id': 'di', 'path': 'source.txt', 'sha256': sha, 'kind': 'job_description',
              'revision': None, 'paragraphs': {'L1': body}}
    profile = {'key': 'hr', 'position_code': 'hr-consultant', 'version': 4, 'status': 'draft',
        'is_synthetic': False, 'sources': [{'source_id': 'di', 'role': 'job_description', 'revision': None}],
        'formal_requirements': [{'key': 'hr.education', 'text': body, 'kind': 'education_level',
            'params': {'schema_version': '0.1', 'alternatives': [{'key': 'higher', 'level': 'высшее'}]},
            'is_mandatory': True, 'verification': 'documents', 'check_stage': 'screening', 'origin': 'source',
            'source_refs': [{'source_id': 'di', 'sha256': sha, 'address': 'L1', 'paragraph_ids': ['L1'], 'quote': body}]}],
        'competencies': []}
    return {'package_schema': 'requirement-profile-review/0.2', 'profiles': [profile]}, {'documents': [source]}


def test_package_keeps_version_and_provenance_and_rejects_repeat(session, tmp_path):
    api = public()
    package, manifest = package_inputs(tmp_path)
    result = api.load_package(session, package, manifest, tmp_path, created_by='test')
    first = result.profiles[0]
    assert first.version == 4 and not first.is_synthetic and first.status == RequirementStatus.DRAFT
    assert first.formal_requirements[0].source_refs[0]['quote'] == 'Высшее образование'
    with pytest.raises(api.RequirementError) as caught:
        api.load_package(session, package, manifest, tmp_path, created_by='test')
    assert caught.value.code == 'version_conflict'
    assert session.scalar(select(func.count()).select_from(RequirementProfile)) == 1
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 1


def test_package_preserves_quote_from_several_nonadjacent_paragraphs(session, tmp_path):
    import hashlib
    api = public()
    package, manifest = package_inputs(tmp_path)
    content = 'Высшее образование\nДругой пункт\nПереподготовка'.encode('utf-8')
    (tmp_path / 'source.txt').write_bytes(content)
    source = manifest['documents'][0]
    source['sha256'] = hashlib.sha256(content).hexdigest()
    source['paragraphs'] = {'L1': 'Высшее образование', 'L2': 'Другой пункт', 'L3': 'Переподготовка'}
    ref = package['profiles'][0]['formal_requirements'][0]['source_refs'][0]
    ref.update(sha256=source['sha256'], paragraph_ids=['L1', 'L3'], quote='Высшее образование\nПереподготовка')
    result = api.load_package(session, package, manifest, tmp_path, created_by='test')
    assert result.profiles[0].formal_requirements[0].source_refs[0]['quote'] == ref['quote']


def test_invalid_second_profile_rolls_back_whole_package_only(session, tmp_path):
    api = public()
    existing = api.load_profile_draft(session, draft(), created_by='test')
    package, manifest = package_inputs(tmp_path)
    second = deepcopy(package['profiles'][0])
    second['position_code'] = 'missing'
    package['profiles'].append(second)
    with pytest.raises(api.RequirementError):
        api.load_package(session, package, manifest, tmp_path, created_by='test')
    assert session.scalars(select(RequirementProfile.id)).all() == [existing.id]
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 0


@pytest.mark.parametrize('damage', ['hash', 'quote', 'path', 'unknown', 'paragraph'])
def test_package_rejects_invalid_sources_before_persisting(session, tmp_path, damage):
    api = public()
    package, manifest = package_inputs(tmp_path)
    if damage == 'hash':
        (tmp_path / 'source.txt').write_text('changed', encoding='utf-8')
    elif damage == 'quote':
        package['profiles'][0]['formal_requirements'][0]['source_refs'][0]['quote'] = 'invented'
    elif damage == 'path':
        manifest['documents'][0]['path'] = '../outside.txt'
    elif damage == 'paragraph':
        manifest['documents'][0]['paragraphs']['L1'] = 'forged manifest text'
    else:
        package['profiles'][0]['formal_requirements'][0]['typo'] = True
    with pytest.raises(api.RequirementError):
        api.load_package(session, package, manifest, tmp_path, created_by='test')
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 0


@pytest.mark.parametrize('damage', ['kind_list', 'notes_null', 'notes_string', 'note_unknown', 'mandatory_missing'])
def test_malformed_package_has_domain_error(session, tmp_path, damage):
    api = public()
    package, manifest = package_inputs(tmp_path)
    profile = package['profiles'][0]
    if damage == 'kind_list':
        manifest['documents'][0]['kind'] = []
    elif damage == 'notes_null':
        profile['source_notes'] = None
    elif damage == 'notes_string':
        profile['source_notes'] = ['wrong']
    elif damage == 'note_unknown':
        profile['source_notes'] = [{'source_refs': [], 'unknown_executable_rule': True}]
    else:
        del profile['formal_requirements'][0]['is_mandatory']
    with pytest.raises(api.RequirementError):
        api.load_package(session, package, manifest, tmp_path, created_by='test')
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 0


def test_concurrent_loads_and_approvals_serialize_and_cli_persists(engine, database_url, tmp_path):
    """Separate connections/process see committed results, not mocks or SAVEPOINT-local rows."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import os
    import uuid
    from sqlalchemy import delete
    from sqlalchemy.orm import Session
    from app.db.models import Position
    api = public()
    code = 'requirements-test-' + uuid.uuid4().hex[:12]
    with Session(engine) as db:
        position = Position(code=code, title='test', employer='test', is_municipal_service=False)
        db.add(position)
        user = f.make_user(db, login=code)
        position_id, user_id = position.id, user.id
        db.commit()
    data = draft()
    data['position_code'] = code
    gate = Barrier(2)
    def create(_):
        with Session(engine) as db:
            gate.wait(timeout=10)
            profile = api.load_profile_draft(db, data, created_by='parallel-test')
            result = profile.id, profile.version
            db.commit()
            return result
    def approve(profile_id):
        with Session(engine) as db:
            gate.wait(timeout=10)
            api.approve_profile(db, profile_id, approved_by_user_id=user_id, approval_basis='concurrent test')
            db.commit()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, range(2)))
        assert sorted(version for _, version in results) == [1, 2]
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(approve, [profile_id for profile_id, _ in results]))
        with Session(engine) as db:
            statuses = db.scalars(select(RequirementProfile.status).where(RequirementProfile.position_id == position_id)).all()
            assert sorted(s.value for s in statuses) == ['approved', 'archived']
        path = tmp_path / 'cli.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        env = {**os.environ, 'DATABASE_URL': database_url, 'PYTHONIOENCODING': 'utf-8'}
        for commit in (False, True):
            result = subprocess.run([sys.executable, '-m', 'app.requirements', 'load', str(path),
                                     *(['--commit'] if commit else [])], cwd=ROOT, env=env,
                                    capture_output=True, text=True, encoding='utf-8', timeout=20)
            assert result.returncode == 0, result.stderr
            response = json.loads(result.stdout)
            assert response['persisted'] == commit and response['profiles'][0]['version'] == 3
            with Session(engine) as db:
                count = db.scalar(select(func.count()).select_from(RequirementProfile).where(RequirementProfile.position_id == position_id))
                assert count == (3 if commit else 2)
    finally:
        with Session(engine) as db:
            db.execute(delete(RequirementProfile).where(RequirementProfile.position_id == position_id))
            db.execute(delete(Position).where(Position.id == position_id))
            db.execute(delete(User).where(User.id == user_id))
            db.commit()


def test_new_loader_does_not_import_assessment_when_creating_profile(session):
    api = public()
    import builtins
    real_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith('app.assessment'), 'requirements loading depends on assessment'
        return real_import(name, *args, **kwargs)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builtins, '__import__', guarded)
        assert api.load_profile_draft(session, draft(), created_by='test').version == 1


def test_standalone_fixture_matches_py9001_and_reaches_assessment_api(session):
    from app.assessment.fixtures import create_fixture_profile, load
    from app.assessment.service import assess_candidate
    from app.ai.fake import FakeLLMClient
    from app.api.services import get_comparison
    from app.db import repository as repo
    from app.db.enums import ApplicationSource
    from app.db.models import Assessment
    api = public()
    data = json.loads((ROOT / 'fixtures/requirement_profiles/py-9001.draft.json').read_text(encoding='utf-8'))
    legacy = create_fixture_profile(session, load(ROOT / 'fixtures/assessment/py-9001.json'))
    profile = api.load_profile_draft(session, data, created_by='test')
    assert profile.formal_requirements[0].params == legacy.formal_requirements[0].params
    assert profile.competencies[0].indicators[0].key == legacy.competencies[0].indicators[0].key
    user = f.make_user(session)
    api.approve_profile(session, profile.id, approved_by_user_id=user.id, approval_basis='synthetic test')
    quote = 'Написал API-тесты для сервиса заявок.'
    candidate = f.make_candidate(session, 'py-9001', text=quote, is_synthetic=True)
    def answer(role, schema, system, prompt):
        if schema == 'CompetencyExtraction':
            return {'indicators': [{'indicator_key': profile.competencies[0].indicators[0].key,
                                   'status': 'confirmed', 'quote': quote}]}
        return {}
    assessment_id = assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id,
                                     llm=FakeLLMClient(answer), mode='technical', as_of='2026-11')
    assessment = session.get(Assessment, assessment_id)
    assert assessment.formal_checks[0].result.value == 'unknown'
    assert assessment.competency_scores[0].level is None
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                          vacancy_id=f.vacancy(session).id)
    result = get_comparison(session, application.id, profile.id)
    assert result.assessment.profile_id == profile.id
    assert result.assessment.profile_version == profile.version
    assert result.assessment.is_training
    evidence = result.assessment.competency_scores[0].details.indicators[0].evidence
    assert evidence[0].quote == quote
    assert candidate.is_synthetic and profile.is_synthetic
    from fastapi.testclient import TestClient
    from app.db.session import get_session
    from app.main import create_app
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        response = client.get(f'/api/v1/applications/{application.id}/comparison', params={'profile_id': str(profile.id)})
        assert response.status_code == 200
        body = response.json()['assessment']
        assert body['profile_id'] == str(profile.id) and body['profile_version'] == profile.version
        assert body['is_training'] and body['formal_result'] == 'unknown'
        assert body['competency_scores'][0]['level'] is None
        assert body['competency_scores'][0]['details']['indicators'][0]['evidence'][0]['quote'] == quote
