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
            catalog = swarm.load_catalog(Path(__file__).resolve().parents[1])
            settings = {'backend_subnet': '10.42.0.0/24', 'data_constraint': 'node.labels.portfolio.data == true'}
            result = swarm.render(compose, settings, 'app:release', {name: name + '@sha256:pinned' for name in swarm.CORE + ['agent', 'node2']}, 'private$secret', root, root, catalog=catalog)
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
            self.assertEqual(result['services']['node2']['deploy']['placement']['constraints'], ['node.labels.portfolio.worker == true'])
            self.assertTrue(all(port['mode'] == 'host' for port in result['services']['caddy']['ports']))
            self.assertEqual(len(result['configs']), 3)
            self.assertEqual(swarm.escape(result)['services']['agent']['environment']['AGENT_SECRET'], 'private$$secret')

    def test_escape_preserves_literal_secret_dollars(self):
        self.assertEqual(swarm.escape({'environment': {'VALUE': '${UNSET}$hash$$'}}), {'environment': {'VALUE': '$${UNSET}$$hash$$$$'}})

class CatalogTests(unittest.TestCase):
    def base(self):
        return {'services': {'caddy': {'networks': ['swarm_backend']}}, 'networks': {'swarm_backend': {}}, 'volumes': {}, 'configs': {}}

    def catalog(self):
        return {'services': {'demo': {'image': 'example/demo:v1', 'networks': ['swarm_demo'], 'deploy': {'replicas': 3, 'placement': {'constraints': ['node.role == worker']}, 'resources': {'limits': {'memory': '64M'}}}}}, 'networks': {'swarm_demo': {}}, 'caddy_networks': ['swarm_demo']}

    def add(self, catalog, root, result=None):
        result = self.base() if result is None else result
        swarm.add_catalog(result, catalog, {'demo': 'example/demo@sha256:test'}, root, root, 'node.labels.portfolio.data == true')
        return result

    def test_replicated_service_and_private_env_are_rendered_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / '.swarm').mkdir()
            (root / '.swarm/services.private.json').write_text('{"demo":{"TOKEN":"secret$literal"}}')
            catalog = self.catalog(); result = self.add(catalog, root)
            self.assertEqual(result['services']['demo']['deploy']['replicas'], 3)
            self.assertEqual(result['services']['demo']['environment']['TOKEN'], 'secret$literal')
            self.assertNotIn('environment', catalog['services']['demo'])
            self.assertEqual(result['services']['caddy']['networks'], ['swarm_backend', 'swarm_demo'])

    def test_config_and_secret_rotation_preserves_target_and_saved_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'settings.txt').write_text('first')
            catalog = self.catalog()
            catalog['configs'] = {'settings': {'file': 'settings.txt'}}
            catalog['secrets'] = {'password': {'file': 'settings.txt'}}
            catalog['services']['demo'].update(configs=[{'source': 'settings', 'target': '/etc/demo.conf'}], secrets=['password'])
            first = self.add(catalog, root)
            config = first['services']['demo']['configs'][0]
            self.assertEqual(config['target'], '/etc/demo.conf')
            self.assertEqual(first['services']['demo']['secrets'][0]['target'], 'password')
            (root / 'settings.txt').write_text('second')
            second = self.add(catalog, root)
            self.assertNotEqual(config['source'], second['services']['demo']['configs'][0]['source'])
            self.assertEqual(Path(first['configs'][config['source']]['file']).read_text(), 'first')

    def test_reject_core_network_access_published_ports_and_unknown_fields(self):
        for change in [{'networks': ['swarm_backend']}, {'ports': ['8080:80']}, {'build': '.'}]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                catalog = self.catalog(); catalog['services']['demo'].update(change)
                with self.assertRaises(RuntimeError): self.add(catalog, Path(directory))

    def test_writable_data_requires_single_replica_pinned_to_data_node(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog()
            service = catalog['services']['demo']
            service['volumes'] = [{'type': 'bind', 'source': str(root / 'data'), 'target': '/data'}]
            with self.assertRaisesRegex(RuntimeError, 'Writable storage'): self.add(catalog, root)
            service['deploy']['replicas'] = 1
            service['deploy']['placement']['constraints'] = ['node.labels.portfolio.data == true']
            result = self.add(catalog, root)
            self.assertEqual(result['services']['demo']['deploy']['update_config']['order'], 'stop-first')

    def test_external_secret_and_no_eligible_global_target(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = self.catalog(); deploy = catalog['services']['demo']['deploy']
            deploy.pop('replicas'); deploy['mode'] = 'global'
            catalog['secrets'] = {'token': {'external': True, 'name': 'demo_token_v1'}}
            catalog['services']['demo']['secrets'] = ['token']
            result = self.add(catalog, Path(directory))
            self.assertEqual(result['secrets']['extra_token']['name'], 'demo_token_v1')
            self.assertFalse(swarm.service_counts_match({'demo': result['services']['demo']}, [{'Name': 'portfolio_demo', 'Mode': 'global', 'Replicas': '0/0'}]))


class DynamicCountTests(unittest.TestCase):
    def test_three_nodes_multiple_replicas_and_intentional_scale_zero(self):
        services = {'agent': {'deploy': {'mode': 'global'}}, 'web': {'deploy': {'replicas': 4}}, 'disabled': {'deploy': {'replicas': 0}}}
        rows = [{'Name': 'portfolio_agent', 'Mode': 'global', 'Replicas': '3/3'}, {'Name': 'portfolio_web', 'Mode': 'replicated', 'Replicas': '4/4'}, {'Name': 'portfolio_disabled', 'Mode': 'replicated', 'Replicas': '0/0'}]
        self.assertTrue(swarm.service_counts_match(services, rows))
        rows[0]['Replicas'] = '2/3'
        self.assertFalse(swarm.service_counts_match(services, rows))
        rows[0]['Replicas'] = '2/2'  # One node drained; use the scheduler's desired total.
        self.assertTrue(swarm.service_counts_match(services, rows))
        rows[1]['Replicas'] = '2/2'  # Manual scaling differs from the saved release.
        self.assertFalse(swarm.service_counts_match(services, rows))

    def test_removed_or_missing_service_is_not_ready(self):
        service = {'web': {}}
        row = {'Name': 'portfolio_web', 'Mode': 'replicated', 'Replicas': '1/1'}
        self.assertFalse(swarm.service_counts_match(service, []))
        self.assertFalse(swarm.service_counts_match(service, [row, dict(row, Name='portfolio_retired')]))


class ConvergenceTests(unittest.TestCase):
    def test_running_old_tasks_do_not_pass_during_update(self):
        expected = {name: {} for name in swarm.CORE}
        rows = [{'Name': 'portfolio_' + name, 'Mode': 'replicated', 'Replicas': '1/1'} for name in swarm.CORE]
        def docker(*args):
            if args[:2] == ('service', 'ls'):
                return '\n'.join(json.dumps(row) for row in rows)
            if args[:2] == ('service', 'inspect'):
                return json.dumps([{'UpdateStatus': {'State': 'updating'}}])
            if args[:2] == ('service', 'ps'): return 'task'
            if args == ('inspect', 'task'): return json.dumps([{'Status': {'State': 'running'}}])
            return json.dumps([{'State': {'Running': True, 'Health': {'Status': 'healthy'}}}])
        with patch.object(swarm, 'release_stack', return_value={'services': expected}), patch.object(swarm, 'docker', side_effect=docker), patch.object(swarm, 'container', return_value='container'), patch.object(swarm.time, 'monotonic', side_effect=[0, 0, 301]), patch.object(swarm.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'did not converge'): swarm.wait_ready('candidate.json')


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
                self.assertIn('--prune', docker.call_args_list[1].args)
                self.assertEqual(swarm.check.call_args_list[1].args, (old['file'],))
                self.assertEqual(json.loads((private / 'current.json').read_text()), old)
                self.assertFalse((private / 'previous.json').exists())
                run.assert_not_called()
                report.assert_called_once()

    def test_manual_rollback_failure_restores_current_release(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            current = {'file': '/private/current.json', 'image': 'app:current'}
            previous = {'file': '/private/previous.json', 'image': 'app:previous'}
            (private / 'current.json').write_text(json.dumps(current))
            (private / 'previous.json').write_text(json.dumps(previous))
            with patch.object(swarm, 'PRIVATE', private), patch.object(swarm, 'docker') as docker, patch.object(swarm, 'check', side_effect=[RuntimeError('bad rollback'), None]) as check, patch.object(swarm, 'report_failed_tasks'):
                with self.assertRaisesRegex(RuntimeError, 'bad rollback'): swarm.rollback()
                self.assertEqual(check.call_args_list[1].args, (current['file'],))
                self.assertEqual(docker.call_args_list[1].args[-2], current['file'])
                self.assertIn('--prune', docker.call_args_list[1].args)
                self.assertEqual(json.loads((private / 'current.json').read_text()), current)

    def test_initial_rollback_has_clear_error_without_docker_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'docker') as docker:
                with self.assertRaisesRegex(RuntimeError, 'No previous Swarm release'):
                    swarm.rollback()
                docker.assert_not_called()

class PortainerInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('swarm_portainer_test', Path(__file__).resolve().parents[1] / 'scripts/swarm-portainer.py')
        cls.portainer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.portainer)

    def test_three_nodes_with_drained_node(self):
        nodes = [{'ID': str(i), 'Spec': {'Availability': 'active'}, 'Status': {'State': 'ready'}} for i in range(3)]
        self.portainer.validate_nodes(nodes, nodes)
        nodes[2]['Spec']['Availability'] = 'drain'
        nodes[2]['Status']['State'] = 'down'
        self.portainer.validate_nodes(nodes, nodes)
        with self.assertRaises(RuntimeError): self.portainer.validate_nodes(nodes, nodes[:2])
        nodes[2]['Spec']['Availability'] = 'active'
        with self.assertRaises(RuntimeError): self.portainer.validate_nodes(nodes, nodes)


if __name__ == '__main__':
    unittest.main()
