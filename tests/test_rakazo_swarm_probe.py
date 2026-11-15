import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rakazo_scratch_probe', ROOT / 'scripts/verify-rakazo-swarm.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeBoundaries(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'deploy/swarm-services.json').read_text())

    def test_only_private_bounded_nonroot_worker_without_credentials(self):
        result = probe.probe_spec('sha256:' + 'a' * 64, self.catalog)
        service = result['services']['web']
        self.assertFalse({'ports', 'configs', 'secrets', 'privileged'} & service.keys())
        self.assertEqual(service['user'], '1000:1000')
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertEqual(service['deploy']['placement']['constraints'], ['node.id == ' + probe.NODE])
        self.assertEqual(result['networks'], {'isolated': {'driver': 'overlay', 'internal': True, 'attachable': False}})
        self.assertGreaterEqual(len(service['environment']['SCREEN_PROXY_SECRET']), 32)
        self.assertEqual(service['environment']['API_PROXY_TARGET'], 'http://127.0.0.1:9')

    def test_host_data_unbounded_scratch_and_mutable_images_fail_closed(self):
        with self.assertRaises(ValueError): probe.probe_spec('app:latest', self.catalog)
        for replacement in [
            {'type': 'bind', 'source': '/srv/swarm', 'target': '/tmp'},
            {'type': 'tmpfs', 'target': '/tmp', 'tmpfs': {'size': 0}},
            {'type': 'tmpfs', 'target': '/tmp', 'tmpfs': {'size': 2**30}},
            {'type': 'tmpfs', 'target': '/', 'tmpfs': {'size': 1024}},
        ]:
            catalog = copy.deepcopy(self.catalog)
            catalog['services']['rakazo_web']['volumes'][0] = replacement
            with self.assertRaises(ValueError): probe.probe_spec('sha256:' + 'a' * 64, catalog)


if __name__ == '__main__':
    unittest.main()
