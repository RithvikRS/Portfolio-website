"""Exercise the workflow's actual PR gate with fake GitHub responses."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

WORKFLOW = (Path(__file__).resolve().parents[1] / '.github/workflows/deploy.yml').read_text()
CHECK = textwrap.dedent(WORKFLOW.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])
PR = {'merged_at': '2026-10-19T00:00:00Z', 'merge_commit_sha': 'abc123',
      'base': {'ref': 'main', 'repo': {'full_name': 'owner/repo'}}}


class MergedPRGate(unittest.TestCase):
    def gate(self, responses):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'output'
            env = {'GITHUB_SHA': 'abc123', 'GITHUB_REPOSITORY': 'owner/repo',
                   'GITHUB_API_URL': 'https://api.github.test', 'GH_TOKEN': 'fixture-token',
                   'GITHUB_OUTPUT': str(output)}
            def response(request, **kwargs):
                # This contract includes merge_commit_sha; the 2026 API omits it.
                self.assertEqual(request.get_header('X-github-api-version'), '2022-11-28')
                value = next(responses)
                if isinstance(value, Exception):
                    raise value
                return io.BytesIO(json.dumps(value).encode())
            with patch.dict(os.environ, env), patch('urllib.request.urlopen', side_effect=response), \
                    patch('time.sleep'), patch('builtins.print'):
                exec(compile(CHECK, 'workflow-pr-gate', 'exec'), {})
            return output.read_text()

    def test_merged_main_pr_passes(self):
        self.assertEqual(self.gate(iter([[PR]])), 'eligible=true\n')

    def test_direct_push_has_no_merged_pr_and_skips(self):
        self.assertEqual(self.gate(iter([[], [], []])), 'eligible=false\n')

    def test_missing_merge_sha_fails_instead_of_silently_skipping(self):
        pr = copy.deepcopy(PR)
        del pr['merge_commit_sha']
        with self.assertRaisesRegex(RuntimeError, 'omitted merge_commit_sha'):
            self.gate(iter([[pr]]))

    def test_open_closed_unmerged_wrong_branch_repo_or_sha_skip(self):
        variants = []
        for key, value in [('merged_at', None), ('merge_commit_sha', 'different')]:
            pr = copy.deepcopy(PR)
            pr[key] = value
            variants.append(pr)
        pr = copy.deepcopy(PR)
        pr['base']['ref'] = 'V2'
        variants.append(pr)
        pr = copy.deepcopy(PR)
        pr['base']['repo']['full_name'] = 'someone/fork'
        variants.append(pr)
        self.assertEqual(self.gate(iter([variants] * 3)), 'eligible=false\n')

    def test_retries_eventual_merge_metadata(self):
        self.assertEqual(self.gate(iter([[], [PR]])), 'eligible=true\n')

    def test_follows_next_page(self):
        self.assertEqual(self.gate(iter([[{}] * 100, [PR]])), 'eligible=true\n')

    def test_api_failure_does_not_allow_deployment(self):
        with self.assertRaises(OSError):
            self.gate(iter([OSError('API unavailable')]))

    def test_production_job_keeps_gate_and_main_context(self):
        self.assertIn('  push:\n    branches: [main]', WORKFLOW)
        self.assertNotIn('  pull_request_target:', WORKFLOW)
        self.assertIn("if: needs.merged-pr.outputs.eligible == 'true'", WORKFLOW)
        self.assertIn('environment: production', WORKFLOW)
        self.assertIn('permissions: {}', WORKFLOW)
        self.assertIn('persist-credentials: false', WORKFLOW)
        self.assertIn('needs: [merged-pr, build]', WORKFLOW)


    def test_docs_filter_cannot_skip_runtime_configuration(self):
        import re
        block = WORKFLOW.split('    paths-ignore:\n', 1)[1].split('\n\n', 1)[0]
        rules = [line.strip()[2:] for line in block.splitlines()]
        self.assertEqual(set(rules), {'README.md', 'deploy/**/*.md', 'LICENSE'})
        def ignored(path):
            return path in ('README.md', 'LICENSE') or bool(re.fullmatch(r'deploy/(?:.*/)?[^/]+\.md', path))
        for path in ('README.md', 'deploy/SWARM.md', 'deploy/nested/guide.md'):
            self.assertTrue(ignored(path))
        for path in ('Dockerfile', '.dockerignore', '.github/workflows/deploy.yml', 'deploy/swarm.json',
                     'deploy/swarm-services.json', 'deploy/Caddyfile.swarm', 'deploy/authelia/configuration.yml',
                     'scripts/swarm-deploy.py', 'server/notes.mjs', 'data/portfolio.json', 'documents/Rithvik_CV.pdf'):
            self.assertFalse(ignored(path))

    def test_registry_credentials_are_read_only_for_deploy_and_passed_on_stdin(self):
        build = WORKFLOW.split('  build:\n', 1)[1].split('  deploy:\n', 1)[0]
        deploy = WORKFLOW.split('  deploy:\n', 1)[1]
        self.assertIn('packages: write', build)
        self.assertIn('packages: read', deploy)
        self.assertNotIn('packages: write', deploy)
        self.assertIn("printf '%s' \"$REGISTRY_TOKEN\" | ssh -T", deploy)
        self.assertIn('cancel-in-progress: false', WORKFLOW)
        self.assertIn('platforms: linux/amd64,linux/arm64', build)


if __name__ == '__main__':
    unittest.main()
