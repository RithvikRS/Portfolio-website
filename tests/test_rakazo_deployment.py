import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if sys.platform == 'win32':
    sys.modules.setdefault('fcntl', types.SimpleNamespace())
spec = importlib.util.spec_from_file_location('rakazo_swarm', ROOT / 'scripts/swarm-deploy.py')
swarm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swarm)
setup_spec = importlib.util.spec_from_file_location('rakazo_setup', ROOT / 'scripts/setup-rakazo-app.py')
setup = importlib.util.module_from_spec(setup_spec)
setup_spec.loader.exec_module(setup)


class RakazoDeploymentTests(unittest.TestCase):
    def test_oidc_alias_is_scoped_to_internal_ingress(self):
        catalog = {'networks': {'swarm_workspace': {'internal': True}},
                   'caddy_networks': ['swarm_workspace'],
                   'caddy_network_aliases': {'swarm_workspace': ['identity.example.test']}}
        def render(value):
            result = {'services': {'caddy': {'networks': ['swarm_backend']}},
                      'networks': {'swarm_backend': {}}, 'volumes': {}, 'configs': {}}
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                swarm.add_catalog(result, value, {}, root, root, 'data')
            return result
        result = render(catalog)
        self.assertEqual(result['services']['caddy']['networks'], {
            'swarm_backend': {}, 'swarm_workspace': {'aliases': ['identity.example.test']}})
        self.assertIsInstance(catalog['caddy_networks'], list)
        invalid = copy.deepcopy(catalog)
        invalid['networks']['swarm_workspace']['internal'] = False
        with self.assertRaises(RuntimeError): render(invalid)
        for names in [['https://identity.example.test'], ['bad host'], ['a..test'], ['same.test', 'same.test'], [None], []]:
            invalid = copy.deepcopy(catalog)
            invalid['caddy_network_aliases']['swarm_workspace'] = names
            with self.assertRaises(RuntimeError): render(invalid)
        invalid = copy.deepcopy(catalog)
        invalid['caddy_network_aliases'] = {'swarm_backend': ['identity.example.test']}
        with self.assertRaises(RuntimeError): render(invalid)

    def test_workspace_services_have_no_external_network_or_runtime_socket(self):
        catalog = json.loads((ROOT / 'deploy/swarm-services.json').read_text())
        for name in ['rakazo_api', 'rakazo_web', 'rakazo_db']:
            service = catalog['services'][name]
            self.assertNotIn('ports', service)
            for network in service['networks']:
                self.assertTrue(catalog['networks'][network]['internal'])
                self.assertFalse(catalog['networks'][network]['attachable'])
            for mount in service.get('volumes', []):
                if mount['type'] == 'bind':
                    self.assertTrue(mount['source'].startswith('/srv/swarm/' + name))
                    self.assertNotIn('docker.sock', mount['source'])
        api = catalog['services']['rakazo_api']
        self.assertEqual(api['environment']['WORKSPACE_ONLY'], 'true')
        self.assertEqual(api['environment']['SANDBOX_PROVIDER'], 'none')
        self.assertEqual(api['environment']['AUTH_PASSWORD_ENABLED'], 'false')
        self.assertNotIn('rakazo_database_owner_password', api['secrets'])
        self.assertNotIn('DATABASE_MIGRATION_URL', api['environment'])
        self.assertEqual(catalog['caddy_network_aliases'], {'swarm_rakazo_app': ['rithvik.ddns.net']})


class RakazoBootstrapTests(unittest.TestCase):
    def test_private_install_is_idempotent_and_never_replaces_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'key'
            setup.install(target, 'original')
            setup.install(target, 'original')
            with self.assertRaises(RuntimeError): setup.install(target, 'replacement')
            self.assertEqual(target.read_text(), 'original')

    def test_manager_reuses_one_recovery_set_and_keeps_migration_password_out_of_api_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); auth = root / 'auth'; private = root / 'private'
            (auth / 'directory').mkdir(parents=True)
            (auth / 'directory/users.yml').write_text(json.dumps({'users': {'rithvik': {'groups': ['admins'], 'email': 'owner@example.test'}}}))
            client = Mock(return_value={'password': 'example-oidc-secret', 'digest': 'example-client-hash'})
            helper = types.SimpleNamespace(AUTH=auth, new_client=client)
            fake_spec = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda _: None))
            with patch.object(setup, 'PRIVATE', private), patch.object(setup, 'docker', return_value='auth-task'), \
                 patch.object(setup.importlib.util, 'spec_from_file_location', return_value=fake_spec), \
                 patch.object(setup.importlib.util, 'module_from_spec', return_value=helper):
                setup.manager()
                before = (private / 'recovery.json').read_bytes()
                setup.manager()
            self.assertEqual(before, (private / 'recovery.json').read_bytes())
            self.assertEqual(client.call_count, 1)
            keys = json.loads(before)
            self.assertIn(keys['database_app_password'], (private / 'database_url').read_text())
            self.assertNotIn(keys['database_owner_password'], (private / 'database_url').read_text())
            self.assertEqual((private / 'owner_email').read_text(), 'owner@example.test')
            self.assertEqual((auth / 'rakazo-client-hash').read_text(), 'example-client-hash\n')

    def test_worker_refuses_mutable_image_and_running_production_before_reading_secrets(self):
        with patch.object(setup, 'docker') as docker:
            with self.assertRaises(RuntimeError): setup.worker('app:latest')
            docker.assert_not_called()
        with patch.object(setup, 'docker', side_effect=[setup.NODE, 'running-task']), \
             patch.object(setup.os.path, 'ismount', return_value=True), \
             patch.object(Path, 'read_text', return_value=setup.NODE), patch.object(setup.json, 'load') as private:
            with self.assertRaisesRegex(RuntimeError, 'production'): setup.worker('example/app@sha256:' + 'a' * 64)
            private.assert_not_called()


if __name__ == '__main__':
    unittest.main()
