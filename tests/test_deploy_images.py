"""Exercise retention across success, failed deployment, retries and cleanup errors."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest

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

    def run(self, *args, capture=False):
        self.calls.append(args)
        if args in self.fail:
            raise subprocess.CalledProcessError(1, args)
        if args[:2] == ('image', 'ls'):
            return self.tags.get(args[-1], '')
        if args[0] == 'ps':
            return 'app-container' if self.running else ''
        if args[:2] == ('container', 'inspect'):
            return self.running + (' true healthy' if self.healthy else ' true unhealthy')
        if args[:2] == ('image', 'tag'):
            self.tags[args[3]] = args[2]
        elif args[:2] == ('image', 'inspect'):
            import json
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


if __name__ == '__main__':
    unittest.main()
