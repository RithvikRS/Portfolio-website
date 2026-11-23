"""Host-free regression coverage for bounded-home maintenance and rollback."""
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('homes_migration', Path(__file__).parents[1] / 'scripts/migrate-rakazo-homes.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class MigrationTests(unittest.TestCase):
    def test_dependencies_preserve_settings(self):
        old = f'[Unit]\nAfter=network.target\nRequiresMountsFor=/other {m.HOMES}/pilot-owner\n[Service]\nDelegate=cpu memory\nCPUQuota=75%\n'
        new = m.update_dependencies(old)
        self.assertIn('After=network.target', new)
        self.assertIn('Delegate=cpu memory\nCPUQuota=75%', new)
        self.assertIn('/other', new)
        self.assertNotIn(str(m.HOMES / 'pilot-owner'), new)
        self.assertEqual(new, m.update_dependencies(new))

    def test_mount_identity_rejects_same_device_wrong_directory(self):
        with patch.object(m.os.path, 'ismount', return_value=True), patch.object(m.os, 'stat', side_effect=[SimpleNamespace(st_dev=1, st_ino=2), SimpleNamespace(st_dev=1, st_ino=3)]):
            with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
                m.assert_homes_mount()
        with patch.object(m.os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                m.assert_homes_mount()

    def exercise(self, fail=None, rollback=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            homes, cache, units, runtime = [root / p for p in ['homes', 'cache', 'units', 'runtime']]
            for p in [homes / 'pilot-owner', cache / 'pilot-home', units, runtime]:
                p.mkdir(parents=True)
            (homes / 'pilot-owner/note.txt').write_text('existing private data')
            dropin = units / 'delegation.conf'; original = '[Unit]\nAfter=custom.target\n[Service]\nDelegate=cpu memory\n'; dropin.write_text(original)
            old_unit = units / 'old.mount'; old_unit.write_text('old mount config')
            for name in ['bridge.mjs', 'native-agent-bridge.mjs']:
                (runtime / name).write_text('previous code')
            bounded = cache / 'family-homes'
            mounts = {str(homes / 'pilot-owner')}
            calls = []
            failed = False
            def run(*args):
                nonlocal failed
                calls.append(args)
                if args[0] == 'du': return '20 homes'
                if args[0] == 'cp':
                    if fail == 'before-bind' and not failed:
                        failed = True; raise RuntimeError('injected')
                    shutil.copytree(homes, bounded, dirs_exist_ok=True)
                if args[0] == 'umount': mounts.discard(args[1])
                if args[:2] == ('mount', '--bind'): mounts.add(args[-1])
                if args == ('systemctl', 'start', 'new.mount'):
                    mounts.add(str(homes))
                    if fail == 'after-bind' and not failed:
                        failed = True; raise RuntimeError('injected')
                if args[:2] == ('userctl', 'start') and fail == 'service-start' and not failed:
                    failed = True; raise RuntimeError('injected')
                return ''
            def verify():
                if str(homes) not in mounts: raise RuntimeError('Missing mount')
            with patch.multiple(m, BASE=root, CACHE=cache, HOMES=homes, BOUNDED=bounded, STATE=root/'state.json', UNITS=units, RUNTIME=runtime, DROPIN=dropin, PREFIX=['userctl']), \
                 patch.object(m, 'preflight'), patch.object(m, 'unit', side_effect=lambda p: 'new.mount' if p == homes else 'old.mount'), \
                 patch.object(m, 'run', side_effect=run), patch.object(m, 'assert_homes_mount', side_effect=verify), \
                 patch.object(m.os.path, 'ismount', side_effect=lambda p: str(p) in mounts), \
                 patch.object(m.os, 'chown', create=True), patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=10**10)), \
                 patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), patch.object(sys, 'argv', ['migration', '--apply']):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'injected'): m.main()
                else:
                    m.main()
                    self.assertIn(str(homes), mounts)
                    self.assertIn('After=custom.target', dropin.read_text())
                    if rollback:
                        (runtime/'bridge.mjs').write_text('new mount-dependent code')
                        with patch.object(sys, 'argv', ['migration', '--rollback']): m.main()
                if fail or rollback:
                    self.assertNotIn(str(homes), mounts)
                    self.assertIn(str(homes/'pilot-owner'), mounts)
                    self.assertEqual(dropin.read_text(), original)
                    self.assertEqual(old_unit.read_text(), 'old mount config')
                    self.assertFalse((units/'new.mount').exists())
                    self.assertEqual((runtime/'bridge.mjs').read_text(), 'previous code')
                    self.assertEqual(calls[-1], ('userctl', 'start', 'rakazo-engine', 'rakazo-controller', 'rakazo-bridge'))
                self.assertEqual((homes/'pilot-owner/note.txt').read_text(), 'existing private data')

    def test_failure_before_bind(self): self.exercise('before-bind')
    def test_failure_after_bind(self): self.exercise('after-bind')
    def test_partial_service_start_failure(self): self.exercise('service-start')
    def test_apply_and_explicit_rollback_restore_code_and_mounts(self): self.exercise(rollback=True)

if __name__ == '__main__': unittest.main()
