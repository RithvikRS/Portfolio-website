"""Exercise notification policy without contacting ntfy or Oracle."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import os
import subprocess
import sys
import json
from unittest.mock import patch

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

    def test_capacity_clears_condition_but_preserves_cooldown(self):
        self.event('error', 'NotAuthenticated')
        self.event('clear')
        self.event('error', 'NotAuthenticated')
        self.assertEqual(len(self.sent), 1)
        self.event('clear')
        self.event('error', 'NotAuthenticated', 186400)
        self.assertEqual(len(self.sent), 2)

    def test_alternating_categories_do_not_bypass_cooldown(self):
        for detail in ['timeout', 'NotAuthenticated', 'timeout', 'NotAuthenticated']:
            self.event('error', detail)
        self.assertEqual(len(self.sent), 2)

    def test_live_connection_capacity_pattern_alerts_once(self):
        for minute in range(0, 120, 5):
            self.event('error', 'TooManyRequests', 100000 + minute * 60)
            self.event('clear', now=100100 + minute * 60)
        self.assertEqual(len(self.sent), 1)

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
        self.assertIn('success', json.loads(self.path.read_text())['pending'])
        self.event('success', 'RUNNING')
        self.assertEqual(len(self.sent), 1)

    def fail_delivery(self, kind='error', detail='NotAuthenticated'):
        def fail(*args):
            # The outbox must be durable before attempting delivery.
            self.assertTrue(json.loads(self.path.read_text())['pending'])
            raise OSError('offline')
        with self.assertRaises(OSError):
            notify.notify(kind, detail, self.path, fail, 100000)

    def test_failed_error_is_retried_by_capacity_cycle_after_restart(self):
        self.fail_delivery()
        # Every invocation reloads the on-disk state; no in-memory queue survives.
        self.event('clear', now=100300)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('Delayed alert', self.sent[0][1])
        state = json.loads(self.path.read_text())
        self.assertEqual(state['pending'], {})
        self.assertNotIn('error', state)
        self.event('error', 'NotAuthenticated', 100600)
        self.assertEqual(len(self.sent), 1)

    def test_changed_category_keeps_undelivered_error(self):
        self.fail_delivery()
        self.event('error', 'Invalid ssh public key', 100300)
        self.assertEqual(len(self.sent), 2)
        self.assertIn('credentials', self.sent[0][1])
        self.assertIn('public key', self.sent[1][1])

    def test_retry_flushes_without_new_oci_result(self):
        self.fail_delivery()
        self.event('retry', now=100300)
        self.event('retry', now=100600)
        self.assertEqual(len(self.sent), 1)

    def test_queue_is_bounded_and_contains_no_raw_details(self):
        for _ in range(3):
            for detail in ['Invalid ssh public key', 'NotAuthenticated', 'QuotaExceeded', 'timeout', 'unexpected']:
                self.fail_delivery(detail=detail + ' secret-value ocid1.secret')
        state = json.loads(self.path.read_text())
        self.assertEqual(len(state['pending']), 5)
        self.assertNotIn('secret-value', self.path.read_text())
        self.assertNotIn('ocid1', self.path.read_text())

    def test_partial_delivery_does_not_repeat_delivered_category(self):
        self.fail_delivery()
        self.fail_delivery(detail='Invalid ssh public key')
        count = 0
        def partial(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('offline')
            self.sent.append(args)
        with self.assertRaises(OSError):
            notify.notify('retry', state_path=self.path, send=partial, now=100300)
        self.event('retry', now=100600)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(json.loads(self.path.read_text())['pending'], {})

    def test_original_state_migration_keeps_delivery_timestamp(self):
        self.path.write_text(json.dumps({'error': {'category': 'connection', 'sent_at': 100000}}))
        self.event('clear', now=100300)
        self.event('error', 'timeout', 100600)
        self.assertEqual(self.sent, [])

    def test_state_write_failure_prevents_network_request(self):
        with patch.object(notify, 'write_private', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.event('error', 'NotAuthenticated')
        self.assertEqual(self.sent, [])

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
        self.assertEqual((self.root / 'events').read_text(), 'retry\nerror\n')

    def test_capacity_checks_three_domains_without_alert(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual((self.root / 'calls').read_text().count('instance launch'), 3)
        self.assertEqual((self.root / 'events').read_text(), 'retry\nclear\n')
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
        self.assertEqual((self.root / 'events').read_text(), 'retry\nsuccess\n')

    def test_actionable_failure_does_not_retry_other_domains(self):
        self.run_script(LAUNCH_RESULT='Invalid ssh public key')
        self.assertEqual((self.root / 'calls').read_text().count('instance launch'), 1)
        self.assertEqual((self.root / 'events').read_text(), 'retry\nerror\n')


if __name__ == '__main__':
    unittest.main()
