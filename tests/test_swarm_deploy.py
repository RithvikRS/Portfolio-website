import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

if sys.platform == 'win32':
    sys.modules.setdefault('fcntl', types.SimpleNamespace())
spec = importlib.util.spec_from_file_location('swarm_deploy', Path(__file__).resolve().parents[1] / 'scripts/swarm-deploy.py')
swarm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swarm)

class SwarmConfigurationTests(unittest.TestCase):
    def test_data_stays_pinned_and_proxy_network_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['deploy/Caddyfile.swarm', 'deploy/authelia/configuration.yml', 'deploy/ntfy/server.yml']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('non-secret configuration')
            compose = {'services': {name: {'image': 'example', 'environment': {}, 'networks': {'backend' if name == 'app' else 'identity': {}}, 'volumes': []} for name in swarm.CORE}}
            compose['services']['caddy']['networks'] = {'backend': {}, 'identity': {}, 'management': {}, 'notifications': {}}
            compose['services']['app']['volumes'] = [{'type': 'bind', 'source': str(root / '.notes'), 'target': '/writing'}]
            compose['services']['caddy']['volumes'] = [{'type': 'volume', 'source': 'caddy_data', 'target': '/data'}, {'type': 'bind', 'source': str(root / 'deploy'), 'target': '/etc/caddy/site'}]
            settings = {'backend_subnet': '10.42.0.0/24', 'data_constraint': 'node.labels.portfolio.data == true', 'worker_constraint': 'node.labels.portfolio.worker == true'}
            result = swarm.render(compose, settings, 'app:release', {name: name + '@sha256:pinned' for name in swarm.ALL}, 'private$secret', root, root)
            for name in swarm.CORE:
                service = result['services'][name]
                self.assertEqual(service['deploy']['replicas'], 1)
                self.assertEqual(service['deploy']['placement']['constraints'], [settings['data_constraint']])
                self.assertEqual(service['deploy']['update_config']['order'], 'stop-first')
            self.assertEqual([name for name, service in result['services'].items() if 'swarm_backend' in service['networks']], ['app', 'caddy'])
            self.assertFalse(result['networks']['swarm_backend']['attachable'])
            self.assertEqual(result['volumes']['caddy_data']['name'], 'portfolio_caddy_data')
            self.assertTrue(result['volumes']['caddy_data']['external'])
            self.assertEqual(result['services']['agent']['deploy']['mode'], 'global')
            self.assertNotIn('ports', result['services']['agent'])
            self.assertNotIn('ports', result['services']['ntfy'])
            self.assertEqual(result['services']['node2']['deploy']['placement']['constraints'], [settings['worker_constraint']])
            self.assertTrue(all(port['mode'] == 'host' for port in result['services']['caddy']['ports']))
            self.assertEqual(len(result['configs']), 3)
            self.assertEqual(swarm.escape(result)['services']['agent']['environment']['AGENT_SECRET'], 'private$$secret')

    def test_escape_preserves_literal_secret_dollars(self):
        self.assertEqual(swarm.escape({'environment': {'VALUE': '${UNSET}$hash$$'}}), {'environment': {'VALUE': '$${UNSET}$$hash$$$$'}})

class ImageResolutionTests(unittest.TestCase):
    def test_backup_alias_cannot_replace_worker_registry(self):
        digest = 'sha256:' + 'a' * 64
        reference = 'traefik/whoami@' + digest
        info = [{'RepoDigests': ['portfolio-node2@' + digest, reference]}]
        with patch.object(swarm, 'docker', return_value=json.dumps(info)):
            self.assertEqual(swarm.image(reference), reference)

    def test_tag_resolves_only_the_requested_repository(self):
        digest = 'sha256:' + 'b' * 64
        info = [{'RepoDigests': ['backup@' + digest, 'docker.io/library/caddy@' + digest]}]
        with patch.object(swarm, 'docker', return_value=json.dumps(info)):
            self.assertEqual(swarm.image('caddy:2-alpine'), info[0]['RepoDigests'][1])

    def test_wrong_repository_or_explicit_digest_fails_closed(self):
        for candidates in [['backup@sha256:abc'], ['traefik/whoami@sha256:other']]:
            with self.subTest(candidates=candidates), patch.object(swarm, 'docker', return_value=json.dumps([{'RepoDigests': candidates}])):
                with self.assertRaises(RuntimeError):
                    swarm.image('traefik/whoami@sha256:requested')

    def test_registry_port_is_not_removed_as_an_image_tag(self):
        self.assertEqual(swarm.registry_repository('registry.example:5000/team/app:v1'), 'registry.example:5000/team/app')


class SwarmReleaseTests(unittest.TestCase):
    def test_failed_health_restores_previous_spec_without_rotating_pointers(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            old = {'file': '/private/old.json', 'image': 'app:old'}
            candidate = {'file': '/private/new.json', 'image': 'app:new'}
            (private / 'current.json').write_text(json.dumps(old))
            (private / 'candidate.json').write_text(json.dumps(candidate))
            with patch.object(swarm, 'PRIVATE', private), patch.object(swarm, 'docker') as docker, patch.object(swarm, 'check', side_effect=[RuntimeError('unhealthy'), None]), patch.object(swarm, 'report_failed_tasks') as report, patch.object(swarm, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'unhealthy'):
                    swarm.apply()
                self.assertEqual(docker.call_args_list[0].args[-2], candidate['file'])
                self.assertEqual(docker.call_args_list[1].args[-2], old['file'])
                self.assertEqual(json.loads((private / 'current.json').read_text()), old)
                self.assertFalse((private / 'previous.json').exists())
                run.assert_not_called()
                report.assert_called_once()

    def test_initial_rollback_has_clear_error_without_docker_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'docker') as docker:
                with self.assertRaisesRegex(RuntimeError, 'No previous Swarm release'):
                    swarm.rollback()
                docker.assert_not_called()

if __name__ == '__main__':
    unittest.main()
