"""Exercise notification policy without contacting ntfy or Oracle."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import os
import subprocess
import sys

spec = importlib.util.spec_from_file_location('ntfy_notify', Path(__file__).resolve().parents[1] / 'scripts/ntfy-notify.py')
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


class Notifications(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'state.json'
        self.sent = []

    def event(self, kind, detail='', now=100000):
        return notify.notify(kind, detail, self.path, lambda *args: self.sent.append(args), now)

    def test_capacity_is_quiet(self):
        for message in ['Out of host capacity.', 'Out of capacity']:
            self.event('error', message)
        self.assertEqual(self.sent, [])

    def test_only_same_error_is_suppressed_for_24_hours(self):
        self.event('error', 'Invalid ssh public key type')
        self.event('error', 'Invalid ssh public key type', 100100)
        self.assertEqual(len(self.sent), 1)
        self.event('error', 'NotAuthenticated', 100200)
        self.assertEqual(len(self.sent), 2)
        self.event('error', 'NotAuthenticated', 186601)
        self.assertEqual(len(self.sent), 3)

    def test_capacity_clears_an_old_error(self):
        self.event('error', 'NotAuthenticated')
        self.event('clear')
        self.event('error', 'NotAuthenticated')
        self.assertEqual(len(self.sent), 2)

    def test_success_is_sent_once(self):
        self.event('success', 'PROVISIONING')
        self.event('success', 'RUNNING')
        self.assertEqual(len(self.sent), 1)
        self.assertIn('provisioning', self.sent[0][1])

    def test_failed_delivery_is_retried(self):
        def fail(*args):
            raise OSError('offline')
        with self.assertRaises(OSError):
            notify.notify('success', 'RUNNING', self.path, fail)
        self.assertFalse(self.path.exists())
        self.event('success', 'RUNNING')
        self.assertEqual(len(self.sent), 1)

    def test_private_oci_details_never_enter_notification(self):
        self.event('error', 'secret-value ocid1.instance.secret NotAuthenticated')
        self.assertNotIn('secret-value', str(self.sent))
        self.assertNotIn('ocid1', str(self.sent))


@unittest.skipUnless(sys.platform.startswith('linux'), 'ARM cron runs in Linux Bash')
class Provisioning(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        # Replace every operational path before executing the script. No real OCI calls.
        script = (Path(__file__).resolve().parents[1] / 'deploy/arm/apply-stack.sh').read_text()
        script = script.replace('/home/opc', str(self.root)).replace('/opt/portfolio/scripts', str(self.root))
        script = script.replace('/tmp/ampere-launch.lock', str(self.root / 'launch.lock')).replace('sleep 2', 'sleep 0')
        (self.root / 'apply-stack.sh').write_text(script)
        (self.root / 'ampere-env.sh').write_text('COMPARTMENT_ID=test\nAD=test\nSUBNET_ID=test\nIMAGE_ID=test\n')
        (self.root / 'ampere-a1.pub').write_text('test public key')
        (self.root / 'bin').mkdir()
        (self.root / 'bin/oci').write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
Path(os.environ['FIXTURE']+'/calls').open('a').write(' '.join(sys.argv[1:])+'\\n')
if 'list' in sys.argv:
 print(os.environ.get('LIST_STATE','null'))
 sys.exit(int(os.environ.get('LIST_EXIT','0')))
print(os.environ.get('LAUNCH_RESULT','Out of host capacity'))
sys.exit(int(os.environ.get('LAUNCH_EXIT','1')))
''')
        (self.root / 'ntfy-notify.py').write_text('''import os,sys
from pathlib import Path
Path(os.environ['FIXTURE']+'/events').open('a').write(sys.argv[1]+'\\n')
sys.exit(int(os.environ.get('NOTIFY_EXIT','0')))
''')
        (self.root / 'bin/crontab').write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
if '-l' in sys.argv: print('*/5 * * * * /home/opc/apply-stack.sh')
else: Path(os.environ['FIXTURE']+'/cron-updated').write_text(sys.stdin.read())
''')
        for name in ['bin/oci', 'bin/crontab']:
            (self.root / name).chmod(0o700)
        self.env = dict(os.environ, FIXTURE=str(self.root), PATH=str(self.root / 'bin') + ':' + os.environ['PATH'])

    def run_script(self, **extra):
        return subprocess.run(['bash', str(self.root / 'apply-stack.sh')], env=dict(self.env, **extra), capture_output=True)

    def test_list_failure_does_not_launch(self):
        self.assertNotEqual(self.run_script(LIST_EXIT='1', LIST_STATE='NotAuthenticated').returncode, 0)
        self.assertNotIn('launch', (self.root / 'calls').read_text())
        self.assertEqual((self.root / 'events').read_text(), 'error\n')

    def test_capacity_checks_three_domains_without_alert(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual((self.root / 'calls').read_text().count('instance launch'), 3)
        self.assertEqual((self.root / 'events').read_text(), 'clear\n')
        self.assertFalse((self.root / 'cron-updated').exists())

    def test_existing_instance_never_launches_and_stops_cron(self):
        self.assertEqual(self.run_script(LIST_STATE='PROVISIONING').returncode, 0)
        self.assertNotIn('launch', (self.root / 'calls').read_text())
        self.assertEqual((self.root / 'cron-updated').read_text(), '')

    def test_failed_success_notification_keeps_cron_for_retry(self):
        self.run_script(LIST_STATE='RUNNING', NOTIFY_EXIT='1')
        self.assertFalse((self.root / 'cron-updated').exists())
        self.assertNotIn('launch', (self.root / 'calls').read_text())

    def test_successful_launch_stops_after_first_domain(self):
        result = self.run_script(LAUNCH_EXIT='0', LAUNCH_RESULT='{"data":{"lifecycle-state":"PROVISIONING"}}')
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.root / 'calls').read_text().count('instance launch'), 1)
        self.assertEqual((self.root / 'events').read_text(), 'success\n')

    def test_actionable_failure_does_not_retry_other_domains(self):
        self.run_script(LAUNCH_RESULT='Invalid ssh public key')
        self.assertEqual((self.root / 'calls').read_text().count('instance launch'), 1)
        self.assertEqual((self.root / 'events').read_text(), 'error\n')


if __name__ == '__main__':
    unittest.main()
