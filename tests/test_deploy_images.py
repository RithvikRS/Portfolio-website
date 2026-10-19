"""Exercise retention across success, failed deployment, retries and cleanup errors."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'deploy_images', Path(__file__).resolve().parents[1] / 'scripts' / 'deploy-images.py',
)
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)


class FakeDocker:
    def __init__(self, tags=None, running='A', healthy=True):
        self.tags = dict(tags or {})
        self.running = running
        self.healthy = healthy
        self.calls = []
        self.fail = set()
        self.deleted = []
        self.labelled = set()
        self.digests = {}
        self.extra_users = set()
        self.disk_total = 10 * 1024 ** 3
        self.disk_used = 5 * 1024 ** 3
        self.disk_changes = {}
        self.disk_reads = 0
        self.disk_errors = {}
        self.manifests = {}
        self.platform = {'os': 'linux', 'architecture': 'amd64'}
        self.missing_manifest = False

    def manifest_id(self, reference):
        return self.manifests.get(reference, 'sha256:' + hashlib.sha256(reference.encode()).hexdigest())

    def disk_usage(self, path):
        self.calls.append(('filesystem', 'usage', path))
        self.disk_reads += 1
        if self.disk_reads in self.disk_errors:
            raise self.disk_errors[self.disk_reads]
        return images.DiskUsage(self.disk_total, self.disk_used, self.disk_total - self.disk_used)

    def run(self, *args, capture=False):
        self.calls.append(args)
        if args in self.fail:
            raise subprocess.CalledProcessError(1, args)
        if args == ('info', '--format', '{{.DockerRootDir}}'):
            return '/var/lib/docker'
        if args[:2] == ('image', 'ls'):
            return self.tags.get(args[-1], '')
        if args[0] == 'ps':
            return 'app-container' if self.running else ''
        if args[:2] == ('container', 'inspect'):
            descriptor = None if self.missing_manifest else {
                'mediaType': 'application/vnd.oci.image.manifest.v1+json',
                'digest': self.manifest_id(self.running), 'platform': self.platform,
            }
            return self.running + (' true healthy' if self.healthy else ' true unhealthy') + '|' + json.dumps(descriptor)
        if args[:2] == ('image', 'tag'):
            self.tags[args[3]] = args[2]
        elif args[:2] == ('image', 'inspect'):
            if args[2] == '--platform':
                return self.manifest_id(args[-1])
            aliases = [tag for tag, image in self.tags.items() if image == args[-1]]
            return json.dumps(aliases) + '|' + json.dumps(self.digests.get(args[-1], []))
        elif args[:2] == ('image', 'rm'):
            image = args[-1]
            if image in self.tags.values() or image == self.running or image in self.extra_users:
                raise subprocess.CalledProcessError(1, args)
            self.deleted.append(image)
        elif args[:2] == ('image', 'prune'):
            # The fake honors only the safe command: no global/tagged image pruning.
            if args != ('image', 'prune', '--force', '--filter', 'label=' + images.APP_LABEL):
                raise AssertionError('Unsafe image prune: ' + repr(args))
            self.deleted.extend(sorted(
                self.labelled - set(self.tags.values()) - {self.running} - self.extra_users,
            ))
        elif args[:2] == ('buildx', 'prune'):
            if args != ('buildx', 'prune', '--builder', 'default', '--all', '--force', '--max-used-space', '256MB'):
                raise AssertionError('Unexpected cache policy: ' + repr(args))
        else:
            raise AssertionError('Unexpected Docker command: ' + repr(args))
        self.disk_used += self.disk_changes.get(args[:2], 0)


class ImageRetentionTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        redirects = contextlib.ExitStack()
        self.addCleanup(redirects.close)
        redirects.enter_context(contextlib.redirect_stdout(self.output))
        redirects.enter_context(contextlib.redirect_stderr(self.output))

    def assert_no_cleanup(self, docker):
        self.assertFalse(any(call[1] in ('prune', 'rm') for call in docker.calls if len(call) > 1))

    def test_bootstrap_uses_running_image_not_overwritten_build_tag(self):
        docker = FakeDocker({images.PRODUCTION: 'failed-build'}, running='A')
        images.prepare(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'A')
        self.assert_no_cleanup(docker)

    def test_bootstrap_refuses_unhealthy_container(self):
        docker = FakeDocker({images.PRODUCTION: 'A'}, healthy=False)
        with self.assertRaises(RuntimeError):
            images.prepare(docker)
        self.assertNotIn(images.CURRENT, docker.tags)
        self.assert_no_cleanup(docker)

    def test_fresh_install_has_no_previous_image(self):
        docker = FakeDocker(running=None)
        images.prepare(docker)
        self.assertEqual(docker.tags, {})
        docker.running = 'A'
        docker.tags[images.PRODUCTION] = 'A'
        images.complete(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'A')
        self.assertNotIn(images.PREVIOUS, docker.tags)

    def test_success_rotates_and_only_removes_retired_or_labelled_images(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='B')
        docker.labelled = {'A', 'B', 'failed-build'}
        images.complete(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'B')
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')
        self.assertEqual(set(docker.deleted), {'older', 'failed-build'})
        first_cleanup = next(i for i, call in enumerate(docker.calls) if call[1] in ('rm', 'prune'))
        self.assertLess(docker.calls.index(('image', 'tag', 'A', images.PREVIOUS)), first_cleanup)
        self.assertLess(docker.calls.index(('image', 'tag', 'B', images.CURRENT)), first_cleanup)

    def test_retry_after_failed_deployment_preserves_last_success(self):
        docker = FakeDocker({images.PRODUCTION: 'failed-B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='failed-B', healthy=False)
        images.prepare(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'A')
        self.assert_no_cleanup(docker)
        docker.tags[images.PRODUCTION] = 'C'
        docker.running, docker.healthy = 'C', True
        docker.labelled = {'failed-B'}
        images.complete(docker)
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')
        self.assertEqual(docker.tags[images.CURRENT], 'C')
        self.assertIn('failed-B', docker.deleted)

    def test_same_image_redeploy_keeps_distinct_rollback(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'B', images.PREVIOUS: 'A'}, running='B')
        images.complete(docker)
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')
        self.assertFalse(any(call[:2] == ('image', 'tag') for call in docker.calls))
        self.assertNotIn('A', docker.deleted)

    def test_rebuilt_attestations_with_unchanged_container_allow_cleanup(self):
        docker = FakeDocker({images.PRODUCTION: 'B-rebuilt', images.CURRENT: 'B', images.PREVIOUS: 'A'}, running='B')
        docker.manifests['B-rebuilt'] = docker.manifest_id('B')
        images.complete(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'B')
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')
        self.assertNotIn('A', docker.deleted)
        self.assertIn('executable manifest matches', self.output.getvalue())
        self.assertTrue(any(call[:2] == ('buildx', 'prune') for call in docker.calls))

    def test_equivalent_recreated_container_keeps_distinct_rollback(self):
        docker = FakeDocker({images.PRODUCTION: 'B-rebuilt', images.CURRENT: 'B', images.PREVIOUS: 'A'}, running='B-rebuilt')
        docker.manifests['B-rebuilt'] = docker.manifest_id('B')
        images.complete(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'B-rebuilt')
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')
        self.assertNotIn('A', docker.deleted)

    def test_manifest_lookup_uses_actual_container_platform_and_variant(self):
        docker = FakeDocker({images.PRODUCTION: 'B-new-index', images.CURRENT: 'B'}, running='B')
        docker.platform = {'os': 'linux', 'architecture': 'arm64', 'variant': 'v8'}
        docker.manifests['B-new-index'] = docker.manifest_id('B')
        images.complete(docker)
        self.assertIn(('image', 'inspect', '--platform', 'linux/arm64/v8', '--format', '{{.Id}}', 'B-new-index'), docker.calls)

    def test_missing_or_invalid_identity_metadata_never_rotates_or_prunes(self):
        for invalid in ('descriptor', 'platform', 'digest', 'lookup'):
            with self.subTest(invalid=invalid):
                docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='A')
                if invalid == 'descriptor':
                    docker.missing_manifest = True
                elif invalid == 'platform':
                    docker.platform = {'os': 'linux'}
                elif invalid == 'digest':
                    docker.manifests['A'] = ''
                else:
                    docker.manifests['B'] = ''
                before = docker.tags.copy()
                with self.assertRaises(RuntimeError):
                    images.complete(docker)
                self.assertEqual(docker.tags, before)
                self.assert_no_cleanup(docker)

    def test_failed_platform_inspection_keeps_tags_and_skips_cleanup(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A'}, running='A')
        docker.fail.add(('image', 'inspect', '--platform', 'linux/amd64', '--format', '{{.Id}}', 'B'))
        before = docker.tags.copy()
        with self.assertRaises(subprocess.CalledProcessError):
            images.complete(docker)
        self.assertEqual(docker.tags, before)
        self.assert_no_cleanup(docker)

    def test_unhealthy_result_never_rotates_or_prunes(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='B', healthy=False)
        before = docker.tags.copy()
        with self.assertRaises(RuntimeError):
            images.complete(docker)
        self.assertEqual(docker.tags, before)
        self.assert_no_cleanup(docker)

    def test_stale_container_never_rotates_or_prunes(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A'}, running='A')
        with self.assertRaises(RuntimeError):
            images.complete(docker)
        self.assert_no_cleanup(docker)

    def test_failed_tagging_prevents_cleanup_and_keeps_recovery_image(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A'}, running='B')
        docker.fail.add(('image', 'tag', 'B', images.CURRENT))
        with self.assertRaises(subprocess.CalledProcessError):
            images.complete(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'A')
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')
        self.assert_no_cleanup(docker)
        docker.fail.clear()
        images.complete(docker)
        self.assertEqual(docker.tags[images.CURRENT], 'B')
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')

    def test_manual_backup_alias_is_preserved(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older', 'rithvik-portfolio:manual-backup': 'older'}, running='B')
        docker.labelled = {'older'}
        images.complete(docker)
        self.assertNotIn('older', docker.deleted)
        self.assertEqual(docker.tags['rithvik-portfolio:manual-backup'], 'older')

    def test_digest_and_container_references_are_preserved(self):
        for reference in ('digest', 'container'):
            with self.subTest(reference=reference):
                docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='B')
                if reference == 'digest':
                    docker.digests['older'] = ['registry.example/app@sha256:example']
                else:
                    docker.extra_users.add('older')
                images.complete(docker)
                self.assertNotIn('older', docker.deleted)
                self.assertTrue(any(call[:2] == ('buildx', 'prune') for call in docker.calls))

    def test_cleanup_failure_warns_without_losing_success_or_rollback(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A'}, running='B')
        docker.fail.add(('image', 'prune', '--force', '--filter', 'label=' + images.APP_LABEL))
        images.complete(docker)
        self.assertIn('WARNING:', self.output.getvalue())
        self.assertEqual(docker.tags[images.CURRENT], 'B')
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')
        self.assertTrue(any(call[:2] == ('buildx', 'prune') for call in docker.calls))

    def test_disk_measurements_include_retirement_and_both_prune_steps(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='B')
        docker.disk_changes = {
            ('image', 'rm'): -8 * 1024 ** 2,
            ('image', 'prune'): -4 * 1024 ** 2,
            ('buildx', 'prune'): -2 * 1024 ** 2,
        }
        images.complete(docker)
        readings = [i for i, call in enumerate(docker.calls) if call[:2] == ('filesystem', 'usage')]
        cleanup = [i for i, call in enumerate(docker.calls) if call[1] in ('rm', 'prune')]
        self.assertEqual(len(readings), 2)
        self.assertLess(readings[0], min(cleanup))
        self.assertGreater(readings[1], max(cleanup))
        output = self.output.getvalue()
        self.assertIn('Cleanup disk usage before (/var/lib/docker filesystem)', output)
        self.assertIn('Cleanup disk usage after (/var/lib/docker filesystem)', output)
        self.assertIn('Net disk space freed during cleanup: 14.00 MiB (14,680,064 bytes)', output)
        self.assertIn('available: 5.01 GiB (5,383,389,184 bytes)', output)
        self.assertEqual(docker.tags[images.PREVIOUS], 'A')

    def test_disk_summary_reports_zero_and_growth_without_claiming_savings(self):
        for change, expected in (
            (0, 'Net disk space freed during cleanup: 0.00 B (0 bytes)'),
            (4096, 'Net disk usage increased during cleanup: 4.00 KiB (4,096 bytes)'),
        ):
            with self.subTest(change=change):
                self.output.truncate(0)
                self.output.seek(0)
                docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'B', images.PREVIOUS: 'A'}, running='B')
                docker.disk_changes[('buildx', 'prune')] = change
                images.complete(docker)
                self.assertIn(expected, self.output.getvalue())
                if change:
                    self.assertNotIn('Net disk space freed', self.output.getvalue())

    def test_missing_measurements_do_not_block_cleanup_or_report_zero(self):
        for failed_read in ('location', 1, 2):
            with self.subTest(failed_read=failed_read):
                self.output.truncate(0)
                self.output.seek(0)
                docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='B')
                if failed_read == 'location':
                    docker.fail.add(('info', '--format', '{{.DockerRootDir}}'))
                else:
                    docker.disk_errors[failed_read] = OSError('Cannot read filesystem usage')
                images.complete(docker)
                self.assertIn('older', docker.deleted)
                self.assertTrue(any(call[:2] == ('buildx', 'prune') for call in docker.calls))
                self.assertEqual(docker.tags[images.CURRENT], 'B')
                self.assertEqual(docker.tags[images.PREVIOUS], 'A')
                self.assertIn('WARNING:', self.output.getvalue())
                self.assertIn('Cleanup disk summary unavailable', self.output.getvalue())
                self.assertNotIn('Net disk space freed', self.output.getvalue())

    def test_cleanup_errors_still_report_the_observed_disk_change(self):
        docker = FakeDocker({images.PRODUCTION: 'B', images.CURRENT: 'A', images.PREVIOUS: 'older'}, running='B')
        docker.disk_changes[('image', 'rm')] = -4096
        docker.fail.add(('image', 'prune', '--force', '--filter', 'label=' + images.APP_LABEL))
        images.complete(docker)
        self.assertIn('portfolio image cleanup failed', self.output.getvalue())
        self.assertIn('Net disk space freed during cleanup: 4.00 KiB (4,096 bytes)', self.output.getvalue())

    def test_capacity_change_does_not_produce_a_misleading_savings_total(self):
        images.report_cleanup_disk_change(
            images.DiskUsage(10000, 5000, 5000), images.DiskUsage(20000, 4000, 16000),
        )
        self.assertIn('filesystem capacity changed', self.output.getvalue())
        self.assertNotIn('Net disk space freed', self.output.getvalue())


class DiskUsageTests(unittest.TestCase):
    def test_read_exact_used_and_available_bytes_with_reserved_space(self):
        # Available space can exclude filesystem-reserved blocks. Do not infer
        # it by subtracting used from total or parse rounded human-readable units.
        result = subprocess.CompletedProcess([], 0, stdout='  1B-blocks        Used       Avail\n10737418240 5368709120 4831838208\n')
        with patch.object(images.subprocess, 'run', return_value=result) as run:
            usage = images.Docker(sudo=True).disk_usage('/docker data')
        self.assertEqual(usage, images.DiskUsage(10737418240, 5368709120, 4831838208))
        self.assertEqual(run.call_args.args[0], [
            'sudo', '-n', 'df', '--block-size=1', '--output=size,used,avail', '--', '/docker data',
        ])

    def test_reject_invalid_disk_measurements(self):
        for output in ('', 'filesystem unavailable', 'Size Used Avail\n1 2', 'Size Used Avail\n0 0 0', 'Size Used Avail\n1024 -1 512'):
            with self.subTest(output=output):
                result = subprocess.CompletedProcess([], 0, stdout=output)
                with patch.object(images.subprocess, 'run', return_value=result):
                    with self.assertRaises(ValueError):
                        images.Docker().disk_usage('/var/lib/docker')


if __name__ == '__main__':
    unittest.main()
