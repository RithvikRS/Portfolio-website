"""Execute the deployment's ntfy Compose command against a disposable process model."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform.startswith('linux'), 'Deployment runs in Linux Bash')
class ConfigRedeployment(unittest.TestCase):
    def test_config_only_change_recreates_process_and_preserves_data(self):
        script = (ROOT / 'portfolio_redeploy.sh').read_text()
        command = next(line.strip() for line in script.splitlines()
                       if line.strip().startswith('"${compose[@]}" up') and line.endswith(' ntfy </dev/null'))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'server.yml').write_text('cache-duration: 168h')
            (root / 'running-config').write_text('cache-duration: 168h')
            (root / 'private-data').write_text('existing credentials and cache')
            (root / 'compose.py').write_text('''import sys
from pathlib import Path
if '--force-recreate' in sys.argv:
    Path('running-config').write_text(Path('server.yml').read_text())
if '--wait' not in sys.argv: sys.exit(1)
''')
            # Compose model/image stay unchanged; only bind-mounted contents change.
            (root / 'server.yml').write_text('cache-duration: 24h')
            result = subprocess.run(['bash', '-c', 'compose=(python3 compose.py)\n' + command],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'running-config').read_text(), 'cache-duration: 24h')
            self.assertEqual((root / 'private-data').read_text(), 'existing credentials and cache')
        self.assertLess(script.index('scripts/setup-ntfy.py validate'), script.index(command))
        self.assertLess(script.index(command), script.index('scripts/setup-ntfy.py check'))
        self.assertLess(script.index('scripts/setup-ntfy.py check'), script.index('"${image_manager[@]}" complete'))


if __name__ == '__main__':
    unittest.main()
