"""Import review/0.2 without silently changing versions or losing source evidence."""
from collections import Counter
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import xml.etree.ElementTree as ET
import zipfile

from app.db import repository as repo
from app.db.enums import Channel, DocumentKind, FileFormat
from .errors import RequirementError
from .schemas import check_scalar_types, validate_draft
from .service import atomic, create_validated, lock_position

PACKAGE_SCHEMA = 'requirement-profile-review/0.2'
FORMAL_FIELDS = set('key text kind params is_mandatory verification check_stage origin source_refs rationale acceptance'.split())
COMPETENCY_FIELDS = set('key text code rank target_level_min target_level_max origin source_refs rationale indicators'.split())
INDICATOR_FIELDS = set('key text is_mandatory verification check_stage origin source_refs rationale acceptance excluded_from_scoring sort_order same_as'.split())
REVIEW_FIELDS = set('evidence_channels mandatory_basis interpretation_status grouping_status collection issues context_note aggregation_method exclude_duplicate_weight duplicates_keys related_indicators split_candidates verification_note acceptance'.split())
PROFILE_FIELDS = set('key position_code version status is_synthetic sources formal_requirements competencies source_notes approved_at approved_by_user_id operational_use_allowed content_approver description reviewers_requested team_review title'.split())
PACKAGE_FIELDS = set('package_schema contract_status base_product_commit compatible_with_db_v1 intended_use agreements profiles open_questions compatibility_gaps supersedes_product_commit compatibility_review'.split())


@dataclass
class PackageResult:
    profiles: list
    review_fields: dict[str, int]


def require(condition, code='invalid_package', path='package'):
    if not condition:
        raise RequirementError(code, 'Проверьте структуру пакета, источники и их соответствие.', path)


def keys(data, allowed, required=(), path='package'):
    require(isinstance(data, dict) and not (set(data) - allowed) and set(required) <= set(data), path=path)


def read_json(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise RequirementError('invalid_json', 'Повторяющийся ключ JSON.')
            out[key] = value
        return out
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite number')))
    except (ValueError, UnicodeError) as error:
        if isinstance(error, RequirementError):
            raise
        raise RequirementError('invalid_json', 'Файл не является корректным JSON.') from error
    except OSError as error:
        raise RequirementError('file_unavailable', 'Не удалось прочитать входной файл.') from error


def paragraphs_from_bytes(path, content):
    try:
        if path.suffix.lower() == '.docx':
            with zipfile.ZipFile(io.BytesIO(content)) as doc:
                w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                body = ET.fromstring(doc.read('word/document.xml')).find(f'{w}body')
                require(body is not None, 'source_mismatch', 'documents')
                return {f'P{i}': text for i, p in enumerate(body.iter(f'{w}p'), 1)
                        if (text := ''.join(t.text or '' for t in p.iter(f'{w}t'))).strip()}
        require(path.suffix.lower() == '.txt', 'unsupported_source', 'documents')
        return {f'L{i}': line for i, line in enumerate(content.decode('utf-8-sig').splitlines(), 1) if line.strip()}
    except (zipfile.BadZipFile, KeyError, ET.ParseError, UnicodeError) as error:
        raise RequirementError('source_mismatch', 'Исходный документ не удалось разобрать.') from error


def validate_sources(manifest, source_root):
    keys(manifest, {'archive', 'locator_convention', 'documents'}, {'documents'}, 'manifest')
    require(isinstance(manifest['documents'], list), path='documents')
    root = Path(source_root).resolve()
    documents = {}
    for item in manifest['documents']:
        keys(item, set('id path sha256 kind version_note paragraphs revision'.split()),
             {'id', 'path', 'sha256', 'kind', 'paragraphs'}, 'documents')
        require(isinstance(item['id'], str) and item['id'] and item['id'] not in documents, path='documents.id')
        require(isinstance(item['path'], str) and '\0' not in item['path']
                and not PureWindowsPath(item['path']).drive, path='documents.path')
        path = (root / item['path']).resolve()
        require(path.is_relative_to(root) and path != root and '..' not in Path(item['path']).parts,
                'source_mismatch', 'documents.path')
        try:
            content = path.read_bytes()
        except OSError as error:
            raise RequirementError('source_unavailable', 'Исходный файл недоступен.', 'documents.path') from error
        require(hashlib.sha256(content).hexdigest() == item['sha256'], 'source_mismatch', 'documents.sha256')
        paragraphs = paragraphs_from_bytes(path, content)
        require(paragraphs == item['paragraphs'], 'source_mismatch', 'documents.paragraphs')
        require(isinstance(item['kind'], str) and item['kind'] in {x.value for x in DocumentKind}, path='documents.kind')
        documents[item['id']] = (item, content, paragraphs)
    return documents


def row_source(row, sources, ids):
    require(isinstance(row.get('source_refs'), list), path='source_refs')
    refs = []
    for ref in row['source_refs']:
        keys(ref, {'source_id', 'sha256', 'address', 'paragraph_ids', 'quote'},
             {'source_id', 'sha256', 'address', 'paragraph_ids', 'quote'}, 'source_refs')
        require(isinstance(ref['source_id'], str) and ref['source_id'] in sources, 'source_mismatch', 'source_refs')
        item, _, paragraphs = sources[ref['source_id']]
        require(ref['sha256'] == item['sha256'], 'source_mismatch', 'source_refs')
        parts = ref['paragraph_ids']
        require(isinstance(parts, list) and parts and all(isinstance(p, str) and p in paragraphs for p in parts),
                'source_mismatch', 'source_refs.paragraph_ids')
        require(isinstance(ref['quote'], str) and ref['quote'] and ref['quote'] in '\n'.join(paragraphs[p] for p in parts),
                'source_mismatch', 'source_refs.quote')
        refs.append({'source_document_id': ids[ref['source_id']], 'address': ref['address'], 'quote': ref['quote']})
    return {'key': row.get('key'), 'origin': row.get('origin'), 'source_refs': refs, 'note': row.get('rationale')}


def convert_profile(profile, sources, ids, skipped):
    keys(profile, PROFILE_FIELDS, {'key', 'position_code', 'version', 'status', 'is_synthetic', 'sources', 'formal_requirements', 'competencies'}, 'profile')
    require(type(profile['version']) is int and profile['version'] > 0, path='version')
    check_scalar_types(profile)
    require(profile['status'] == 'draft' and profile.get('approved_at') is None and
            profile.get('approved_by_user_id') is None and profile.get('operational_use_allowed', False) is False,
            path='status')
    for field in ('sources', 'formal_requirements', 'competencies'):
        require(isinstance(profile[field], list), path=field)
    profile_sources = []
    declared = set()
    for source in profile['sources']:
        keys(source, {'source_id', 'role', 'revision'}, {'source_id', 'role'}, 'sources')
        sid = source['source_id']
        require(isinstance(sid, str) and sid in sources and sid not in declared, 'source_mismatch', 'sources')
        item = sources[sid][0]
        require(source['role'] == item['kind'] and source.get('revision') == item.get('revision'), 'source_mismatch', 'sources')
        declared.add(sid)
        profile_sources.append({'source_document_id': ids[sid], 'role': source['role'],
            'observed_revision': source.get('revision'), 'is_primary': source['role'] == 'job_description'})
    selected = {sid: sources[sid] for sid in declared}
    def convert(row, loaded, target):
        allowed = loaded | REVIEW_FIELDS | ({'score'} if target == 'indicators' else set())
        required = {'key', 'text', 'origin', 'source_refs'}
        if target in ('formal_requirements', 'indicators'):
            required |= {'is_mandatory', 'verification'}
        keys(row, allowed, required, target)
        # Legacy synthetic fixture explicitly says no numeric score; never silently discard a real score.
        require(row.get('score') is None, path='indicators.score')
        skipped.update(set(row) - loaded)
        return row_source(row, selected, ids)
    formal = []
    for row in profile['formal_requirements']:
        base = convert(row, FORMAL_FIELDS, 'formal_requirements')
        formal.append({**base, 'kind': row.get('kind'), 'description': row['text'], 'params': row.get('params', {}),
            **{k: row[k] for k in ('is_mandatory', 'verification', 'check_stage', 'acceptance') if k in row}})
    competencies = []
    for group in profile['competencies']:
        base = convert(group, COMPETENCY_FIELDS, 'competencies')
        require(isinstance(group.get('indicators'), list), path='indicators')
        indicators = []
        for row in group['indicators']:
            origin = convert(row, INDICATOR_FIELDS, 'indicators')
            indicators.append({**origin, 'text': row['text'], **{k: row[k] for k in
                ('is_mandatory', 'verification', 'check_stage', 'acceptance', 'excluded_from_scoring', 'same_as') if k in row}})
        competencies.append({**base, 'name': group['text'], 'code': group.get('code'), 'indicators': indicators,
            **{k: group[k] for k in ('rank', 'target_level_min', 'target_level_max') if k in group}})
    notes = profile.get('source_notes', [])
    require(isinstance(notes, list), path='source_notes')
    for row in notes:
        # Source notes remain in the review package, but their citations must still be genuine.
        keys(row, {'key', 'text', 'origin', 'source_refs', 'rationale', 'excluded_from_scoring'} | REVIEW_FIELDS,
             {'key', 'text', 'origin', 'source_refs'}, 'source_notes')
        row_source(row, selected, ids)
        skipped['source_notes'] += 1
    return validate_draft({'schema_version': 'requirement-draft/1.0', 'position_code': profile['position_code'],
        'is_synthetic': profile['is_synthetic'], 'sources': profile_sources,
        'formal_requirements': formal, 'competencies': competencies, 'note': f"{PACKAGE_SCHEMA}, {profile['key']}"})


def load_package(session, package, manifest, source_root, *, created_by, synthetic_profile=None):
    keys(package, PACKAGE_FIELDS, {'package_schema', 'profiles'})
    require(package['package_schema'] == PACKAGE_SCHEMA, path='package_schema')
    require(isinstance(package['profiles'], list) and package['profiles'], path='profiles')
    profiles = list(package['profiles'])
    if synthetic_profile is not None:
        require(isinstance(synthetic_profile, dict) and synthetic_profile.get('is_synthetic') is True, path='synthetic_profile')
        profiles.append(synthetic_profile)
    sources = validate_sources(manifest, source_root)
    # Validate every row and citation before starting any write. Temporary IDs only bind the input schemas.
    import uuid
    ids = {key: uuid.uuid5(uuid.NAMESPACE_URL, key) for key in sources}
    skipped = Counter()
    for profile in profiles:
        convert_profile(profile, sources, ids, skipped)
    with atomic(session):
        for code in sorted({p['position_code'] for p in profiles}):
            lock_position(session, code=code)
        for sid, (item, content, paragraphs) in sources.items():
            document, _ = repo.add_source_document(session, kind=DocumentKind(item['kind']),
                channel=Channel.HH_RU if item['kind'] == 'vacancy_posting' else Channel.INTERNAL,
                file_format=FileFormat.DOCX if Path(item['path']).suffix.lower() == '.docx' else FileFormat.TXT,
                original_path=item['path'], raw_text='\n'.join(paragraphs.values()), content=content,
                import_batch='requirement-profiles')
            ids[sid] = document.id
        loaded = [create_validated(session, convert_profile(p, sources, ids, Counter()),
                    created_by=created_by, version=p['version']) for p in profiles]
        return PackageResult(loaded, dict(skipped))
