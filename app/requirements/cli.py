"""Explicit load/approve operations for a trusted DB operator."""
import argparse
import json
from pathlib import Path
import uuid

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db.models import User
from . import RequirementError, approve_profile, load_package, load_profile_draft, validate_draft
from .package import read_json


def profile_summary(profile):
    return {'profile_id': str(profile.id), 'position_id': str(profile.position_id), 'version': profile.version,
            'status': profile.status.value, 'is_synthetic': profile.is_synthetic,
            'formal_requirements': len(profile.formal_requirements), 'competencies': len(profile.competencies),
            'indicators': sum(len(c.indicators) for c in profile.competencies)}


def parser():
    root = argparse.ArgumentParser(prog='python -m app.requirements')
    commands = root.add_subparsers(dest='command', required=True)
    load = commands.add_parser('load', help='создать следующую версию черновика')
    load.add_argument('file', type=Path)
    load.add_argument('--approve', action='store_true')
    load.add_argument('--approver')
    load.add_argument('--basis')
    package = commands.add_parser('load-package', help='импортировать фиксированные версии пакета 0.2')
    package.add_argument('file', type=Path)
    package.add_argument('manifest', type=Path)
    package.add_argument('source_root', type=Path)
    package.add_argument('--synthetic', type=Path)
    approve = commands.add_parser('approve', help='утвердить существующий черновик')
    approve.add_argument('profile_id', type=uuid.UUID)
    approve.add_argument('--approver', required=True)
    approve.add_argument('--basis', required=True)
    for cmd in (load, package):
        cmd.add_argument('--created-by', default='requirements-cli')
    for cmd in (load, package, approve):
        cmd.add_argument('--commit', action='store_true', help='сохранить; без флага изменения откатываются')
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        should_approve = args.command == 'approve' or getattr(args, 'approve', False)
        if should_approve and (not args.approver or not args.basis or not args.basis.strip()):
            raise RequirementError('approval_refused', 'Укажите существующего HR/admin и основание утверждения.')
        if args.command == 'load' and not should_approve and (args.approver or args.basis):
            raise RequirementError('invalid_arguments', 'Автор утверждения и основание требуют --approve.')
        if args.command == 'load':
            data = validate_draft(read_json(args.file))
        elif args.command == 'load-package':
            data, manifest = read_json(args.file), read_json(args.manifest)
            synthetic = read_json(args.synthetic) if args.synthetic else None
            if synthetic is not None and (not isinstance(synthetic, dict) or 'synthetic_profile' not in synthetic):
                raise RequirementError('invalid_package', 'В файле нет synthetic_profile.')
        from app.db.session import SessionLocal
        with SessionLocal() as session:
            try:
                user = None
                if should_approve:
                    user = session.scalar(select(User).where(User.login == args.approver))
                    if user is None:
                        raise RequirementError('approval_refused', 'Утверждающий пользователь не найден.')
                review_fields = {}
                if args.command == 'load':
                    profiles = [load_profile_draft(session, data, created_by=args.created_by)]
                elif args.command == 'load-package':
                    result = load_package(session, data, manifest, args.source_root, created_by=args.created_by,
                                          synthetic_profile=synthetic['synthetic_profile'] if synthetic else None)
                    profiles, review_fields = result.profiles, result.review_fields
                else:
                    profiles = [approve_profile(session, args.profile_id, approved_by_user_id=user.id, approval_basis=args.basis)]
                if args.command == 'load' and should_approve:
                    approve_profile(session, profiles[0].id, approved_by_user_id=user.id, approval_basis=args.basis)
                response = {'status': ('approved' if args.command == 'approve' else 'loaded') if args.commit else 'dry_run',
                            'persisted': bool(args.commit), 'profiles': [profile_summary(p) for p in profiles],
                            'review_fields': review_fields}
                if args.commit:
                    session.commit()
                else:
                    session.rollback()
            except Exception:
                session.rollback()
                raise
        print(json.dumps(response, ensure_ascii=False))
        return 0
    except RequirementError as error:
        print(json.dumps({'status': 'refused', 'error': error.as_dict()}, ensure_ascii=False))
        return 1
    except OperationalError:
        print(json.dumps({'status': 'unavailable', 'error': {'code': 'database_unavailable',
                        'message': 'База данных недоступна.'}}, ensure_ascii=False))
        return 2
