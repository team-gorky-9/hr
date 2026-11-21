"""Focused checks for privileged static-release archive handling and rollback."""
import io
import json
from pathlib import Path
import runpy
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('frontend-receive.py').read_text(encoding='utf-8')
SHA = 'a' * 40


def archive(name='index.html', content=b'<html>ok</html>', link=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        member = tarfile.TarInfo(name)
        if link:
            member.type = tarfile.SYMTYPE
            member.linkname = '/etc/passwd'
        else:
            member.size = len(content)
        tar.addfile(member, None if link else io.BytesIO(content))
    return buffer.getvalue()


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'www').mkdir()
        self.script = self.root / 'receiver.py'
        self.script.write_text(SOURCE.replace('/opt/hr/frontend', (self.root / 'releases').as_posix())
                               .replace('/var/www', (self.root / 'www').as_posix())
                               .replace('/run/lock/hr-frontend.lock', (self.root / 'lock').as_posix()), encoding='utf-8')

    def receive(self, payload, public_sha=SHA):
        response = io.BytesIO(json.dumps({'sha': public_sha}).encode())
        fake_lock = types.SimpleNamespace(LOCK_EX=1, flock=lambda *args: None)
        with patch.object(sys, 'argv', [str(self.script), SHA]), \
             patch.object(sys, 'stdin', io.TextIOWrapper(io.BytesIO(payload))), \
             patch.dict(sys.modules, {'fcntl': fake_lock}), \
             patch('urllib.request.urlopen', return_value=response):
            runpy.run_path(str(self.script), run_name='__main__')

    def test_publish_and_identical_retry(self):
        self.receive(archive())
        self.receive(archive())
        self.assertEqual((self.root / 'www/hr-frontend').resolve(), self.root / 'releases' / SHA)
        self.assertEqual((self.root / 'www/hr-frontend/index.html').read_bytes(), b'<html>ok</html>')

    def test_reject_traversal_and_symlink(self):
        for payload in [archive('../../outside'), archive('index.html', link=True)]:
            with self.subTest(payload=payload[:8]), self.assertRaises(ValueError):
                self.receive(payload)
        self.assertFalse((self.root / 'outside').exists())
        self.assertFalse((self.root / 'www/hr-frontend').exists())

    def test_existing_release_cannot_be_overwritten(self):
        self.receive(archive())
        with self.assertRaises(ValueError):
            self.receive(archive(content=b'changed'))
        self.assertEqual((self.root / 'www/hr-frontend/index.html').read_bytes(), b'<html>ok</html>')

    def test_failed_probe_restores_previous_release(self):
        old = self.root / 'old'
        old.mkdir()
        (self.root / 'www/hr-frontend').symlink_to(old, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.receive(archive(), public_sha='old')
        self.assertEqual((self.root / 'www/hr-frontend').resolve(), old)


if __name__ == '__main__':
    unittest.main()
