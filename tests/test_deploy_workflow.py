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
        self.assertNotIn('uses: actions/checkout', WORKFLOW)


if __name__ == '__main__':
    unittest.main()
