"""Inspect mapping and freeze/retrieve a reproducible response selection; no LLM calls."""
import argparse
import json
import os
from pathlib import Path
import uuid

from app.postings.registry import RegistryStore
from app.postings.service import create_snapshot, read_snapshot, resolve_application


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m app.postings')
    parser.add_argument('--registry-dir', type=Path,
        default=Path(os.environ.get('POSTING_REGISTRY_DIR', Path(__file__).with_name('data'))))
    parser.add_argument('--registry-version', help='pin an existing immutable registry version')
    sub = parser.add_subparsers(dest='command', required=True)
    one = sub.add_parser('resolve')
    one.add_argument('--application-id', type=uuid.UUID, required=True)
    freeze = sub.add_parser('snapshot')
    freeze.add_argument('--application-id', type=uuid.UUID, action='append', required=True)
    replay = sub.add_parser('read-snapshot')
    replay.add_argument('--snapshot-id', type=uuid.UUID, required=True)
    args = parser.parse_args(argv)
    from app.db.session import SessionLocal
    try:
        with SessionLocal() as session:
            if args.command == 'read-snapshot':
                result = read_snapshot(session, args.snapshot_id)
            else:
                registry = RegistryStore(args.registry_dir).load(args.registry_version)
                if args.command == 'resolve':
                    result = resolve_application(session, args.application_id, registry=registry).model_dump(mode='json')
                else:
                    result = create_snapshot(session, args.application_id, registry=registry)
                    session.commit()
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f'{error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
