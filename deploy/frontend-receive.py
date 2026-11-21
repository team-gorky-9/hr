#!/usr/bin/env python3
"""Root-owned receiver. The dedicated SSH key can only publish static frontend files."""
import fcntl
import io
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request

sha = sys.argv[1] if len(sys.argv) == 2 else ''
if not re.fullmatch(r'[a-f0-9]{40}', sha):
    raise SystemExit('Expected a full commit SHA')
root = Path('/opt/hr/frontend')
root.mkdir(parents=True, exist_ok=True)
with open('/run/lock/hr-frontend.lock', 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    payload = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    if len(payload) > 32 * 1024 * 1024:
        raise SystemExit('Archive exceeds 32 MiB')
    staging = Path(tempfile.mkdtemp(prefix='.incoming-', dir=root))
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
            members = archive.getmembers()
            if sum(m.size for m in members) > 128 * 1024 * 1024:
                raise ValueError('Expanded archive exceeds limit')
            for member in members:
                target = staging / member.name
                if not target.resolve().is_relative_to(staging.resolve()) or not (member.isfile() or member.isdir()):
                    raise ValueError('Unsafe archive member')
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, target.open('wb') as dest:
                        shutil.copyfileobj(source, dest)
                    target.chmod(0o644)
        if not (staging / 'index.html').is_file():
            raise ValueError('Missing index.html')
        (staging / 'version.json').write_text('{"sha":"' + sha + '"}\n')
        for directory, _, _ in os.walk(staging):
            Path(directory).chmod(0o755)
        release = root / sha
        if release.exists():
            raise ValueError('Release already exists; do not overwrite immutable assets')
        staging.rename(release)
        live = Path('/var/www/hr-frontend')
        previous = os.readlink(live) if live.is_symlink() else None
        temporary = Path('/var/www/.hr-frontend-next')
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(release)
        temporary.replace(live)
        try:
            with urllib.request.urlopen('https://gorky.bond/version.json', timeout=20) as response:
                if sha not in response.read().decode():
                    raise ValueError('Published version mismatch')
        except Exception:
            if previous:
                temporary.symlink_to(previous)
                temporary.replace(live)
            raise
        print('Published frontend ' + sha)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
