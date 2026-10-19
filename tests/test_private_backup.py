"""Archive disposable state and verify restart-on-failure; never use live Docker."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform.startswith('linux'), 'Backup runs in Linux Bash')
class PrivateBackup(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in ['scripts', '.git', 'bin', '.auth', '.portainer', '.notes', '.ntfy/data']:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.files = ['.env.production', '.auth/key', '.portainer/data.db', '.notes/note.json',
                      '.ntfy/data/auth.db', '.ntfy/data/cache.db', '.ntfy/iphone.json',
                      '.ntfy/publisher.json', '.ntfy/arm-notifications.json']
        for name in self.files:
            path = self.root / name
            path.write_text('fixture: ' + name)
            path.chmod(0o600)
        script = (ROOT / 'scripts/backup-private-state.sh').read_text()
        script = script.replace('/home/opc/.config/portfolio-deploy', str(self.root / 'backups'))
        script = script.replace('/tmp/ampere-launch.lock', str(self.root / 'arm.lock'))
        script = script.replace('flock -w 600', 'flock -w 0').replace('flock -w 60', 'flock -w 0')
        (self.root / 'scripts/backup-private-state.sh').write_text(script)
        stubs = {
            'sudo': '#!/bin/sh\n[ "$1" = -n ] && shift\nexec "$@"\n',
            'git': '#!/bin/sh\nif [ "$2" = --git-path ]; then echo .git/portfolio-deploy.lock; else echo fixture-sha; fi\n',
            'tar': '#!/bin/sh\n[ "${FAIL_TAR:-0}" = 1 ] && exit 2\nexec /usr/bin/tar "$@"\n',
            'docker': '''#!/usr/bin/env python3
import os,sys
from pathlib import Path
args=sys.argv[1:]
Path(os.environ['FIXTURE']+'/docker-calls').open('a').write(' '.join(args)+'\\n')
if 'ps' in args: print('app\\nntfy')
if 'stop' in args and os.environ.get('FAIL_STOP') == '1': sys.exit(2)
''',
        }
        for name, body in stubs.items():
            path = self.root / 'bin' / name
            path.write_text(body)
            path.chmod(0o700)
        self.env = dict(os.environ, FIXTURE=str(self.root), PATH=str(self.root / 'bin') + ':' + os.environ['PATH'])

    def run_backup(self, **extra):
        return subprocess.run(['bash', str(self.root / 'scripts/backup-private-state.sh')],
                              env=dict(self.env, **extra), capture_output=True, text=True, timeout=15)

    def test_archive_inventory_restore_and_modes(self):
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        archive = next((self.root / 'backups').glob('*/private-state.tar.gz'))
        self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(archive.parent.stat().st_mode), 0o700)
        with tarfile.open(archive) as source:
            self.assertTrue(set(self.files).issubset(source.getnames()))
            source.extractall(self.root / 'restored', filter='data')
        for name in self.files:
            restored = self.root / 'restored' / name
            self.assertEqual(restored.read_bytes(), (self.root / name).read_bytes())
            self.assertEqual(stat.S_IMODE(restored.stat().st_mode), 0o600)
        calls = (self.root / 'docker-calls').read_text()
        self.assertIn('stop app auth portainer ntfy', calls)
        self.assertIn('start app ntfy', calls)
        self.assertNotIn('start app auth', calls)

    def test_tar_failure_restarts_original_running_services(self):
        result = self.run_backup(FAIL_TAR='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('start app ntfy', (self.root / 'docker-calls').read_text())
        self.assertIn('incomplete', result.stderr)

    def test_partial_stop_failure_still_restarts(self):
        self.assertNotEqual(self.run_backup(FAIL_STOP='1').returncode, 0)
        self.assertIn('start app ntfy', (self.root / 'docker-calls').read_text())

    def test_active_arm_job_prevents_snapshot(self):
        import fcntl
        with (self.root / 'arm.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertNotEqual(self.run_backup().returncode, 0)
        self.assertFalse((self.root / 'docker-calls').exists())

    def test_active_notifier_prevents_snapshot(self):
        import fcntl
        with (self.root / '.ntfy/notify.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertNotEqual(self.run_backup().returncode, 0)
        self.assertFalse((self.root / 'docker-calls').exists())


if __name__ == '__main__':
    unittest.main()
