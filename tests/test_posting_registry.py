"""Pure routing must never infer a confirmed role from a title outside its context."""
import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError


def api():
    try:
        return importlib.import_module('app.postings.registry')
    except ModuleNotFoundError:
        pytest.fail('The context-aware posting registry is not implemented')


def context(**changes):
    return dict(dataset_id='archive-a', dataset_sha256='a' * 64, channel='hh_ru',
                source_folder='department-a', is_synthetic=False) | changes


def rule(**changes):
    return dict(id='staffing', context=context(), match_kind='posting_title',
                posting_title='Консультант отдела', decision_state='confirmed',
                position_code='hr-consultant', decision_author='HR owner',
                decision_date='2026-11-20', decision_basis='decision://mapping/1',
                evidence_refs=['di://staffing/P102']) | changes


def registry(*rules, version='v1'):
    return api().Registry.model_validate(dict(schema_version='posting-register/1.0',
                                              version=version, rules=list(rules)))


def resolve(register, title='Консультант отдела', contexts=None, synthetic=False):
    module = api()
    contexts = [context()] if contexts is None else contexts
    return module.resolve_posting(register, posting_title=title,
        contexts=[module.RegistryContext.model_validate(c) for c in contexts],
        is_synthetic=synthetic)


def test_same_title_only_confirms_inside_the_exact_dataset_context():
    value = registry(rule())
    allowed = resolve(value)
    foreign = resolve(value, contexts=[context(dataset_id='another-employer')])
    assert (allowed.decision_state, allowed.position_code, allowed.decision_id) == (
        'confirmed', 'hr-consultant', 'staffing')
    assert (foreign.decision_state, foreign.position_code, foreign.reason) == (
        'needs_review', None, 'unknown_publication')
    assert allowed.decision_author == 'HR owner'
    assert allowed.decision_date.isoformat() == '2026-11-20'
    assert allowed.decision_basis == 'decision://mapping/1'


@pytest.mark.parametrize('change', [
    {'dataset_sha256': 'b' * 64}, {'channel': 'email'}, {'source_folder': 'other-department'},
])
def test_context_dimensions_are_not_wildcards(change):
    assert resolve(registry(rule()), contexts=[context(**change)]).decision_state == 'needs_review'


def test_context_preserves_exact_folder_name_instead_of_normalizing_it_as_a_title():
    foreign = context(source_folder=' department-a')
    assert api().RegistryContext.model_validate(foreign).source_folder == ' department-a'
    assert resolve(registry(rule()), contexts=[foreign]).reason == 'unknown_publication'


def test_normalization_preserves_input_but_does_not_match_substrings():
    value = registry(rule(posting_title='Консульта́нт  отдела'))
    title = '  КОНСУЛЬТА́НТ\tОТДЕЛА  '
    result = resolve(value, title)
    assert result.decision_state == 'confirmed'
    assert result.posting_title == title
    assert resolve(value, 'Старший Консульта́нт отдела').decision_state == 'needs_review'


@pytest.mark.parametrize('title', [None, '', ' \t\n '])
def test_missing_title_never_uses_a_title_rule(title):
    result = resolve(registry(rule()), title)
    assert (result.decision_state, result.reason, result.position_code) == ('needs_review', 'missing_posting', None)


def test_explicit_folder_rule_can_resolve_titleless_it_response():
    value = registry(rule(match_kind='folder', posting_title='Python-разработчик', position_code='python-dev'))
    result = resolve(value, None)
    assert (result.decision_state, result.position_code, result.source_kind) == ('confirmed', 'python-dev', 'archive_folder')
    assert result.posting_title is None
    assert resolve(value, 'Python-разработчик').decision_state == 'confirmed'
    assert resolve(value, 'QA Manual').reason == 'unknown_publication'


def test_missing_context_does_not_use_a_global_title_rule():
    result = resolve(registry(rule()), contexts=[])
    assert (result.decision_state, result.reason) == ('needs_review', 'missing_context')
    assert resolve(registry(rule()), None, contexts=[]).reason == 'missing_posting'


def test_multiple_provenances_are_ambiguous_even_if_one_is_confirmed():
    value = registry(rule())
    contexts = [context(), context(dataset_id='another-employer')]
    assert resolve(value, contexts=contexts).reason == 'ambiguous_context'
    assert resolve(value, contexts=list(reversed(contexts))).input_hash == resolve(value, contexts=contexts).input_hash
    assert resolve(value, contexts=[context(), context()]).decision_state == 'confirmed'


def test_real_and_training_contexts_never_cross():
    value = registry(rule(context=context(is_synthetic=True)))
    result = resolve(value, contexts=[context(is_synthetic=True)], synthetic=False)
    assert (result.decision_state, result.reason, result.position_code) == ('needs_review', 'contour_mismatch', None)
    assert resolve(value, contexts=[context(is_synthetic=True)], synthetic=True).decision_state == 'confirmed'


def test_no_matching_position_is_a_recorded_decision_not_a_negative_pair_hint():
    value = registry(rule(decision_state='no_matching_position', position_code=None))
    result = resolve(value)
    assert (result.decision_state, result.position_code, result.reason) == ('no_matching_position', None, 'no_matching_position')
    assert result.decision_author == 'HR owner'
    pending = registry(rule(decision_state='needs_review', position_code=None, decision_author=None,
                            decision_date=None, decision_basis=None, excluded_position_codes=['hr-consultant']))
    result = resolve(pending)
    assert result.decision_state == 'needs_review'
    assert list(result.excluded_position_codes) == ['hr-consultant']
    assert result.decision_author is None


def test_title_and_folder_rules_with_same_name_do_not_pick_the_first():
    value = registry(rule(), rule(id='folder', match_kind='folder', position_code='python-dev'))
    result = resolve(value)
    assert (result.decision_state, result.reason, result.position_code) == ('needs_review', 'ambiguous_mapping', None)


@pytest.mark.parametrize('field, value', [
    ('decision_author', None), ('decision_author', '  '), ('decision_date', None),
    ('decision_basis', None), ('decision_basis', ''), ('evidence_refs', []),
    ('evidence_refs', [' ']), ('position_code', None), ('position_code', ''),
])
def test_confirmation_requires_the_complete_decision_record(field, value):
    with pytest.raises(ValidationError):
        registry(rule(**{field: value}))


@pytest.mark.parametrize('change', [
    {'decision_state': 'no_matching_position'},
    {'decision_state': 'needs_review', 'position_code': None},
    {'decision_state': 'confirmed', 'excluded_position_codes': ['hr-consultant']},
    {'match_kind': 'posting_title', 'posting_title': None},
    {'match_kind': 'posting_title', 'posting_title': ' '},
])
def test_contradictory_rules_are_rejected_before_any_application_is_resolved(change):
    with pytest.raises(ValidationError):
        registry(rule(**change))


def test_normalized_duplicate_rules_and_duplicate_ids_are_rejected():
    with pytest.raises(ValidationError):
        registry(rule(), rule(id='other', posting_title='  КОНСУЛЬТАНТ\tОТДЕЛА '))
    with pytest.raises(ValidationError):
        registry(rule(), rule(context=context(dataset_id='different')))


def test_unrelated_context_can_have_the_same_title_and_different_target():
    value = registry(rule(), rule(id='other', context=context(dataset_id='different'), position_code='python-dev'))
    assert resolve(value, contexts=[context(dataset_id='different')]).position_code == 'python-dev'


def test_empty_and_invalid_scope_values_are_rejected():
    for change in ({'dataset_id': ''}, {'dataset_sha256': 'not-a-hash'}, {'channel': ' '}, {'source_folder': ''}):
        with pytest.raises(ValidationError):
            registry(rule(context=context(**change)))


def write_store(root, values, current):
    versions = root / 'versions'
    versions.mkdir()
    for value in values:
        (versions / f'{value.version}.json').write_text(value.model_dump_json(), encoding='utf-8')
    (root / 'current.json').write_text(json.dumps({'version': current}), encoding='utf-8')


def test_pinned_version_and_serialized_snapshot_survive_current_version_change(tmp_path):
    module = api()
    old = registry(rule())
    new = registry(rule(decision_state='needs_review', position_code=None, decision_author=None,
                        decision_date=None, decision_basis=None), version='v2')
    write_store(tmp_path, [old, new], 'v1')
    store = module.RegistryStore(tmp_path)
    frozen_json = store.load().model_dump_json()
    frozen_result = resolve(store.load()).model_dump(mode='json')
    (tmp_path / 'current.json').write_text('{"version":"v2"}', encoding='utf-8')
    assert resolve(store.load()).decision_state == 'needs_review'
    assert resolve(store.load('v1')).model_dump(mode='json') == frozen_result
    assert resolve(module.Registry.model_validate_json(frozen_json)).model_dump(mode='json') == frozen_result
    assert store.load().digest() != old.digest()


@pytest.mark.parametrize('version', ['../secret', '..', 'a/../../b', 'C:\\outside', '/tmp/x', '.', '', 'a..b'])
def test_version_input_cannot_escape_store(tmp_path, version):
    with pytest.raises(ValueError):
        api().RegistryStore(tmp_path).load(version)


def test_loader_checks_filename_version_and_default_reloads_current(tmp_path, monkeypatch):
    module = api()
    old, new = registry(rule()), registry(rule(), version='v2')
    write_store(tmp_path, [old, new], 'v1')
    monkeypatch.setenv('POSTING_REGISTRY_DIR', str(tmp_path))
    assert module.get_default_registry().version == 'v1'
    (tmp_path / 'current.json').write_text('{"version":"v2"}', encoding='utf-8')
    assert module.get_default_registry().version == 'v2'
    (tmp_path / 'versions/v1.json').write_text(new.model_dump_json(), encoding='utf-8')
    with pytest.raises(ValueError):
        module.RegistryStore(tmp_path).load('v1')


def test_snapshot_hash_covers_input_and_decision_and_objects_are_immutable():
    value = registry(rule())
    result = resolve(value)
    assert len(result.registry_hash) == len(result.input_hash) == 64
    assert result.registry_hash == value.digest()
    assert result.input_hash != resolve(value, '  Консультант отдела').input_hash
    assert result.registry_hash != registry(rule(decision_basis='decision://mapping/2')).digest()
    with pytest.raises((ValidationError, AttributeError)):
        value.version = 'rewritten'
    with pytest.raises(AttributeError):
        value.rules.append(rule())


def test_bundled_registry_keeps_real_hr_pending_and_confirms_only_explicit_it_folders():
    value = api().RegistryStore(Path('app/postings/data')).load('v1')
    hr = [r for r in value.rules if not r.context.is_synthetic and r.match_kind == 'posting_title']
    assert len(hr) == 7
    assert all(r.decision_state == 'needs_review' and r.position_code is None for r in hr)
    assert {r.id for r in hr if r.excluded_position_codes} == {'kadry-financial-control', 'kadry-estimator'}
    assert all(r.excluded_position_codes in ((), ('hr-consultant',)) for r in hr)
    real = [r for r in value.rules if not r.context.is_synthetic]
    assert {r.context.dataset_id for r in real} == {'kadry-2026'}
    assert {r.context.dataset_sha256 for r in real} == {'53c7b6d1918b96c106d99371f9e942b2e8720f164ce85cf4fde6fb275c998548'}
    folders = [r for r in real if r.match_kind == 'folder']
    assert {r.position_code for r in folders} == {'python-dev', 'junior-python-dev', 'qa-manual', 'frontend-dev', 'junior-ux-ui'}
    for row in folders:
        result = api().resolve_posting(value, posting_title=None, contexts=[row.context], is_synthetic=False)
        assert result.decision_state == 'confirmed'
        assert result.source_kind == 'archive_folder'
    assert api().resolve_posting(value, posting_title=None, contexts=[hr[0].context], is_synthetic=False).reason == 'missing_posting'


def test_bundled_training_rules_match_actual_fixture_inventory_and_are_isolated():
    from app.ingest.package import InputFile, read_package, load_mapping
    from app.postings.provenance import dataset_fingerprint
    value = api().RegistryStore(Path('app/postings/data')).load()
    root = Path('fixtures/stage_0a')
    files = read_package(root)
    assert len(files) == 4
    assert all(item.source_path != 'mapping.json' for item in files)
    assert any(item.source_path.endswith('py-9002.pdf') and item.extract_error is not None for item in files)
    fingerprint = dataset_fingerprint(files)
    parent_root_fingerprint = dataset_fingerprint([
        InputFile('stage_0a/' + item.source_path, item.content, item.text) for item in files])
    assert parent_root_fingerprint != fingerprint
    mapping = load_mapping(root / 'mapping.json')
    assert mapping.dataset_id == 'stage0a-training'
    rows = [r for r in value.rules if r.context.is_synthetic and r.context.dataset_id == 'stage0a-training']
    assert len(rows) == 2
    for row in rows:
        assert row.context.dataset_sha256 == fingerprint
        assert row.context.dataset_id == mapping.dataset_id
        result = api().resolve_posting(value, posting_title=row.posting_title, contexts=[row.context], is_synthetic=True)
        assert result.decision_state == 'confirmed'
        assert api().resolve_posting(value, posting_title=row.posting_title, contexts=[row.context], is_synthetic=False).reason == 'contour_mismatch'
        parent_context = row.context.model_copy(update={'dataset_sha256': parent_root_fingerprint})
        assert api().resolve_posting(value, posting_title=row.posting_title, contexts=[parent_context], is_synthetic=True).reason == 'unknown_publication'


def test_demo_training_rules_match_fixture_and_leave_v1_unchanged():
    # Учебный набор для демо: по папке подтверждены Python и консультант; отклик на «Сметчика»
    # в той же папке остаётся без решения (серый в светофоре), v1 не переписан.
    from app.ingest.package import load_mapping, read_package
    from app.postings.provenance import dataset_fingerprint
    store = api().RegistryStore(Path('app/postings/data'))
    current, v1 = store.load(), store.load('v1')
    assert current.version == 'v2' and len(v1.rules) == 14
    assert current.rules[:len(v1.rules)] == v1.rules
    root = Path('fixtures/demo_training')
    files = read_package(root)
    assert len(files) == 12
    mapping = load_mapping(root / 'mapping.json')
    rows = [r for r in current.rules if r.context.dataset_id == 'demo-training']
    assert {r.position_code for r in rows} == {'python-dev', 'hr-consultant'}
    for row in rows:
        assert row.context.is_synthetic and row.context.dataset_id == mapping.dataset_id
        assert row.context.dataset_sha256 == dataset_fingerprint(files)
        assert api().resolve_posting(current, posting_title=row.posting_title, contexts=[row.context],
                                     is_synthetic=True).decision_state == 'confirmed'
    consultant = next(r for r in rows if r.position_code == 'hr-consultant')
    estimator = api().resolve_posting(current, posting_title='Сметчик', contexts=[consultant.context], is_synthetic=True)
    assert estimator.decision_state == 'needs_review' and estimator.reason == 'unknown_publication'
