"""Check candidate validation isolation and config-only deployment recreation."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ntfy_setup', ROOT / 'scripts/setup-ntfy.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class CandidateValidation(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.config = {'services': {'ntfy': {'image': 'ntfy-fixture', 'user': '1000:1000',
            'environment': {'NTFY_BASE_URL': 'https://example.test', 'GOMEMLIMIT': '64MiB'}}}}

    def command(self, args, data=None):
        self.commands.append(args)
        if 'inspect' in args:
            return 'true'
        if 'exec' in args:
            return '{"healthy":true}'
        return ''

    def test_candidate_never_uses_private_database_or_public_network(self):
        with patch.object(setup, 'run', self.command):
            setup.validate(self.config, ['docker'])
        start = self.commands[0]
        self.assertEqual(start[start.index('--network') + 1], 'none')
        self.assertNotIn('--publish', start)
        self.assertNotIn('-p', start)
        self.assertNotIn('.ntfy', str(start))
        self.assertIn('/var/lib/ntfy:size=16m,mode=0700,uid=1000,gid=1000', start)
        self.assertIn('readonly', start[start.index('--mount') + 1])
        self.assertIn('NTFY_BASE_URL=https://example.test', start)
        self.assertEqual(self.commands[-1][:3], ['docker', 'rm', '--force'])

    def test_invalid_candidate_fails_and_is_removed(self):
        def failed(args, data=None):
            if 'inspect' in args:
                self.commands.append(args)
                return 'false'
            return self.command(args, data)
        with patch.object(setup, 'run', failed):
            with self.assertRaisesRegex(RuntimeError, 'running service was not replaced'):
                setup.validate(self.config, ['docker'])
        self.assertEqual(self.commands[-1][:3], ['docker', 'rm', '--force'])

    def test_health_timeout_fails_and_is_removed(self):
        def unhealthy(args, data=None):
            if 'exec' in args:
                return '{"healthy":false}'
            return self.command(args, data)
        with patch.object(setup, 'run', unhealthy), patch.object(setup.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                setup.validate(self.config, ['docker'])
        self.assertEqual(self.commands[-1][:3], ['docker', 'rm', '--force'])


if __name__ == '__main__':
    unittest.main()
