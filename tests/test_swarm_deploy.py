import copy
import datetime
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

class CIRequestTests(unittest.TestCase):
    def test_forced_command_recovers_only_metadata(self):
        command = "PORTFOLIO_DEPLOY_IMAGE='image' PORTFOLIO_DEPLOY_REVISION='revision' PORTFOLIO_REGISTRY_USER='actor' bash /opt/portfolio/portfolio_redeploy.sh"
        self.assertEqual(swarm.ci_request({'SSH_ORIGINAL_COMMAND': command}), ('image', 'revision', 'actor'))
        for bad in (command + '; id', command.replace('bash /opt', 'sh /opt'),
                    command.replace("='image'", "=''"), command.replace('PORTFOLIO_REGISTRY_USER=', 'OTHER=')):
            with self.assertRaises(RuntimeError):
                swarm.ci_request({'SSH_ORIGINAL_COMMAND': bad})

    def test_direct_environment_and_manual_fallback(self):
        self.assertEqual(swarm.ci_request({'PORTFOLIO_DEPLOY_IMAGE': 'image', 'PORTFOLIO_DEPLOY_REVISION': 'rev', 'PORTFOLIO_REGISTRY_USER': 'user'}), ('image', 'rev', 'user'))
        self.assertEqual(swarm.ci_request({'SSH_ORIGINAL_COMMAND': 'bash /opt/portfolio/portfolio_redeploy.sh'}), ('', '', ''))


class SwarmConfigurationTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "Real catalog uses Linux host paths; run this integration fixture on Linux")
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
            (root / '.secrets').mkdir()
            (root / '.secrets/kuma-oidc.cfg').write_text('test fixture')
            catalog = swarm.load_catalog(Path(__file__).resolve().parents[1])
            for definition in catalog['secrets'].values():
                path = root / definition['file']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('private fixture')
            (root / 'scripts').mkdir()
            for definition in catalog['configs'].values():
                path = root / definition['file']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# fixture')
            settings = json.loads((Path(__file__).resolve().parents[1] / 'deploy/swarm.json').read_text())
            result = swarm.render(compose, settings, 'app:release', {name: name + '@sha256:pinned' for name in swarm.CORE + ['agent'] + list(catalog['services'])}, 'private$secret', root, root, catalog=catalog)
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
            self.assertNotIn('node2', result['services'])
            self.assertNotIn('swarm_node2', result['networks'])
            self.assertEqual(result['services']['uptime_kuma']['deploy']['placement']['constraints'], ['node.id == kxm75m17suc2o1hp0s4ikyhri'])
            self.assertTrue(all(port['mode'] == 'host' for port in result['services']['caddy']['ports']))
            self.assertEqual(len(result['configs']), 3 + len(catalog['configs']))
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

    def test_worker_storage_is_scoped_to_exact_node_and_service_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog()
            service = catalog['services']['demo']
            service['deploy']['replicas'] = 1
            service['deploy']['placement']['constraints'] = ['node.id == worker-id']
            data = root / 'storage'
            service['volumes'] = [{'type': 'bind', 'source': str(data / 'demo' / 'db'), 'target': '/data'}]
            approved = {'worker': {'node_id': 'worker-id', 'root': str(data)}}
            def render():
                swarm.add_catalog(self.base(), catalog, {'demo': 'image'}, root, root, 'node.labels.portfolio.data == true', approved)
            render()
            for source in [str(data), str(data / 'another' / 'db'), str(data / 'demo' / '..' / 'another')]:
                service['volumes'][0]['source'] = source
                with self.assertRaisesRegex(RuntimeError, 'Writable storage'): render()
            service['volumes'][0]['source'] = str(data / 'demo')
            service['deploy']['placement']['constraints'] = ['node.role == worker']
            with self.assertRaisesRegex(RuntimeError, 'Writable storage'): render()

    def test_external_secret_and_no_eligible_global_target(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = self.catalog(); deploy = catalog['services']['demo']['deploy']
            deploy.pop('replicas'); deploy['mode'] = 'global'
            catalog['secrets'] = {'token': {'external': True, 'name': 'demo_token_v1'}}
            catalog['services']['demo']['secrets'] = ['token']
            result = self.add(catalog, Path(directory))
            self.assertEqual(result['secrets']['extra_token']['name'], 'demo_token_v1')
            self.assertFalse(swarm.service_counts_match({'demo': result['services']['demo']}, [{'Name': 'portfolio_demo', 'Mode': 'global', 'Replicas': '0/0'}]))


class WorkerImageTests(unittest.TestCase):
    def test_exact_worker_digest_does_not_use_manager_image_store(self):
        settings = {'storage_nodes': {'worker': {'node_id': 'worker-id'}}}
        service = {'image': 'example/kuma@sha256:' + 'a' * 64, 'deploy': {'placement': {'constraints': ['node.id == worker-id']}}}
        with patch.object(swarm, 'image', side_effect=AssertionError('Manager pull attempted')):
            self.assertEqual(swarm.catalog_image(service, settings), service['image'])
            service['image'] = 'example/kuma:latest'
            with self.assertRaisesRegex(RuntimeError, 'immutable'): swarm.catalog_image(service, settings)
        service['deploy']['placement']['constraints'] = ['node.role == manager']
        with patch.object(swarm, 'image', return_value='resolved') as pull:
            self.assertEqual(swarm.catalog_image(service, settings), 'resolved')
            pull.assert_called_once_with(service['image'])

    def test_scratch_mount_survives_render_and_invalid_scratch_is_rejected(self):
        case = CatalogTests(); catalog = case.catalog()
        catalog['services']['demo']['volumes'] = [{'type': 'tmpfs', 'target': '/tmp', 'tmpfs': {'size': 33554432}}]
        with tempfile.TemporaryDirectory() as directory:
            result = case.add(catalog, Path(directory))
            self.assertEqual(result['services']['demo']['volumes'], catalog['services']['demo']['volumes'])
            for invalid in [{'size': -1}, {'size': '32m'}, {'size': 32, 'mode': 99999}]:
                catalog['services']['demo']['volumes'][0]['tmpfs'] = invalid
                with self.assertRaisesRegex(RuntimeError, 'Tmpfs'): case.add(catalog, Path(directory))


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


class CIImageTests(unittest.TestCase):
    reference = 'ghcr.io/rithvikrs/portfolio-website@sha256:' + 'a' * 64
    revision = 'b' * 40

    def test_pull_verifies_labels_and_deletes_credentials(self):
        commands = []
        def run(args, **kwargs):
            commands.append((args, kwargs))
            if args[0] == 'git': return self.revision
            if 'login' in args:
                folder = Path(args[args.index('--config') + 1])
                (folder / 'config.json').write_text('private-token')
            return ''
        info = [{'Id': 'sha256:local', 'Config': {'Labels': {'org.opencontainers.image.revision': self.revision,
                  'io.github.rithvikrs.portfolio.site-url': 'https://example.com/'}}}]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'run', side_effect=run), patch.object(swarm, 'docker', return_value=json.dumps(info)):
                self.assertEqual(swarm.pull_ci_image(self.reference, self.revision, 'user', 'private-token', 'example.com'), 'sha256:local')
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertFalse(any('private-token' in arg for args, _ in commands for arg in args))
        self.assertIn('--password-stdin', commands[1][0])
        self.assertEqual(commands[1][1]['data'], 'private-token\n')
        self.assertIn('--platform', commands[2][0])

    def test_reject_wrong_registry_tag_or_revision_before_login(self):
        for ref, revision in [(self.reference.replace('rithvikrs', 'other'), self.revision),
                              ('ghcr.io/rithvikrs/portfolio-website:latest', self.revision),
                              (self.reference, 'c' * 40)]:
            with self.subTest(ref=ref, revision=revision), patch.object(swarm, 'run', return_value=self.revision) as run:
                with self.assertRaises(RuntimeError): swarm.pull_ci_image(ref, revision, 'user', 'token', 'example.com')
                self.assertFalse(any('login' in call.args[0] for call in run.call_args_list))

    def test_failed_pull_cleans_credentials(self):
        def run(args, **kwargs):
            if args[0] == 'git': return self.revision
            folder = Path(args[args.index('--config') + 1])
            (folder / 'config.json').write_text('private-token')
            if 'pull' in args: raise RuntimeError('pull failed')
            return ''
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'run', side_effect=run):
                with self.assertRaisesRegex(RuntimeError, 'pull failed'):
                    swarm.pull_ci_image(self.reference, self.revision, 'user', 'private-token', 'example.com')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_wrong_image_labels_fail_after_pull(self):
        for labels in ({}, {'org.opencontainers.image.revision': self.revision, 'io.github.rithvikrs.portfolio.site-url': 'https://wrong/'}):
            with tempfile.TemporaryDirectory() as directory:
                with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'run', return_value=self.revision), patch.object(swarm, 'docker', return_value=json.dumps([{'Id': 'sha256:local', 'Config': {'Labels': labels}}])):
                    with self.assertRaisesRegex(RuntimeError, 'revision or site URL'):
                        swarm.pull_ci_image(self.reference, self.revision, 'user', 'token', 'example.com')


class CancellationRecoveryTests(unittest.TestCase):
    def fixture(self):
        image = 'sha256:' + 'a' * 64
        service = {'Spec': {'Name': 'portfolio_app', 'Mode': {'Replicated': {'Replicas': 1}},
                           'TaskTemplate': {'ContainerSpec': {'Image': image}}},
                   'UpdateStatus': {'State': 'paused', 'StartedAt': '2026-11-05T13:00:00Z'}}
        task = {'CreatedAt': '2026-11-05T13:00:01Z', 'Spec': {'ContainerSpec': {'Image': image}},
                'DesiredState': 'shutdown', 'Status': {'State': 'rejected', 'Err': 'Canceled: context canceled'}}
        running = copy.deepcopy(task)
        running.update(DesiredState='running', Status={'State': 'running', 'ContainerStatus': {'ContainerID': 'cid'}})
        info = {'Id': 'cid', 'Config': {'Image': image}, 'State': {'Running': True, 'OOMKilled': False,
                'StartedAt': '2026-11-05T13:00:10Z', 'Health': {'Status': 'healthy', 'FailingStreak': 0,
                'Log': [{'ExitCode': 0}] * 3}}}
        return service, [task, running], info, image, datetime.datetime.fromisoformat('2026-11-05T13:02:00+00:00')

    def test_only_known_cancellation_with_healthy_exact_target_can_resume(self):
        for error in swarm.CANCEL_ERRORS:
            args = self.fixture(); args[1][0]['Status']['Err'] = error
            self.assertTrue(swarm.can_resume_app(*args))

    def test_unhealthy_wrong_image_old_failure_and_real_failures_are_rejected(self):
        def mutate(case, args):
            service, tasks, info, image, now = args
            if case == 'unhealthy': info['State']['Health']['Status'] = 'unhealthy'
            if case == 'oom': info['State']['OOMKilled'] = True
            if case == 'probe': info['State']['Health']['Log'] = [{'ExitCode': 0}, {'ExitCode': 1}, {'ExitCode': 0}]
            if case == 'old': tasks[0]['CreatedAt'] = '2026-11-04T13:00:01Z'
            if case == 'error': tasks[0]['Status']['Err'] = 'permission denied'
            if case == 'failed': tasks[0]['Status']['State'] = 'failed'
            if case == 'wrong-image': info['Config']['Image'] = 'app:old'
            if case == 'wrong-task': tasks[1]['Status']['ContainerStatus']['ContainerID'] = 'other'
            if case == 'too-young': info['State']['StartedAt'] = '2026-11-05T13:01:59Z'
            if case == 'replicas': service['Spec']['Mode']['Replicated']['Replicas'] = 2
            if case == 'missing': info.clear()
        for case in ('unhealthy', 'oom', 'probe', 'old', 'error', 'failed', 'wrong-image', 'wrong-task', 'too-young', 'replicas', 'missing'):
            with self.subTest(case=case):
                args = self.fixture(); mutate(case, args)
                self.assertFalse(swarm.can_resume_app(*args))

    def test_resume_is_no_force_and_diagnostics_precede_update(self):
        service, tasks, info, image, now = self.fixture()
        calls = []
        def docker(*args):
            calls.append(args)
            if args[:2] == ('service', 'ps'): return 't1 t2'
            if args == ('inspect', 't1', 't2'): return json.dumps(tasks)
            if args == ('inspect', 'cid'): return json.dumps([info])
            if args[:2] == ('service', 'update'): raise RuntimeError('daemon unavailable')
            raise AssertionError(args)
        with patch.object(swarm, 'docker', side_effect=docker), patch.object(swarm, 'container', return_value='cid'), patch.object(swarm, 'can_resume_app', return_value=True), patch.object(swarm, 'report_failed_tasks', side_effect=lambda: calls.append(('snapshot',))), patch('builtins.print'):
            self.assertTrue(swarm.resume_canceled_app({'app': {'image': image}}, [service]))
        self.assertEqual(calls[-2], ('snapshot',))
        self.assertEqual(calls[-1], ('service', 'update', '--detach', '--no-resolve-image', 'portfolio_app'))

    def test_wait_attempts_resume_only_once_and_still_requires_completion(self):
        rows = [json.dumps({'Name': 'portfolio_app', 'Mode': 'replicated', 'Replicas': '1/1'})]
        def docker(*args):
            if args[:2] == ('service', 'ls'): return '\n'.join(rows)
            if args[:2] == ('service', 'inspect'): return json.dumps([{'UpdateStatus': {'State': 'paused'}}])
            if args[:2] == ('service', 'ps'): return 't'
            return json.dumps([{'Status': {'State': 'running'}}])
        with patch.object(swarm, 'release_stack', return_value={'services': {'app': {}}}), patch.object(swarm, 'CORE', []), patch.object(swarm, 'docker', side_effect=docker), patch.object(swarm, 'resume_canceled_app', return_value=True) as resume, patch.object(swarm.time, 'monotonic', side_effect=[0, 0, 1, 301]), patch.object(swarm.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'did not converge'): swarm.wait_ready('candidate', recover_app=True)
            resume.assert_called_once()


class FailureDiagnosticsTests(unittest.TestCase):
    def test_snapshot_captures_paused_update_and_health_without_secrets(self):
        responses = [
            json.dumps({'ID': 'svc', 'Name': 'portfolio_app', 'Mode': 'replicated', 'Replicas': '1/1'}),
            json.dumps([{'ID': 'svc-full-id-from-inspect', 'UpdateStatus': {'State': 'paused', 'StartedAt': 'start', 'Message': 'secret-value'},
                         'Spec': {'Name': 'portfolio_app', 'Env': ['TOKEN=secret-value']}}]),
            'container',
            json.dumps([{'Id': 'container', 'Config': {'Env': ['TOKEN=secret-value'],
                         'Labels': {'com.docker.swarm.service.name': 'portfolio_app'}},
                         'State': {'Status': 'running', 'Running': True, 'OOMKilled': True, 'ExitCode': 0,
                                   'Health': {'Status': 'unhealthy', 'FailingStreak': 3,
                                              'Log': [{'Start': 'a', 'End': 'b', 'ExitCode': 1,
                                                       'Output': 'secret-value'}]}}}])]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'docker', side_effect=responses) as docker, patch('builtins.print') as output:
                swarm.report_failure_state()
                raw = (Path(directory) / 'last-failed-state.json').read_text(encoding='utf-8')
                data = json.loads(raw)
                self.assertEqual(data['services'][0]['update']['State'], 'paused')
                self.assertEqual(data['services'][0]['Replicas'], '1/1')
                self.assertEqual(data['local_containers'][0]['health']['status'], 'unhealthy')
                self.assertTrue(data['local_containers'][0]['state']['OOMKilled'])
                self.assertEqual(data['local_containers'][0]['health']['recent_checks'][0]['ExitCode'], 1)
                self.assertNotIn('secret-value', raw + str(output.call_args_list))
                self.assertTrue(all(0 < call.kwargs['timeout'] <= 10 for call in docker.call_args_list))

    def test_service_without_update_status_is_reported(self):
        responses = [json.dumps({'ID': 'short', 'Name': 'portfolio_agent', 'Mode': 'global', 'Replicas': '3/3'}),
                     json.dumps([{'ID': 'short-full-id', 'Spec': {'Name': 'portfolio_agent'}, 'UpdateStatus': None}]), '']
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'docker', side_effect=responses), patch('builtins.print'):
                swarm.report_failure_state()
                data = json.loads((Path(directory) / 'last-failed-state.json').read_text())
                self.assertEqual(data['services'][0]['update']['State'], 'not-started')
                self.assertEqual(data['unavailable'], [])

    def test_service_failure_still_collects_local_health(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(swarm, 'PRIVATE', Path(directory)), patch.object(swarm, 'docker', side_effect=[RuntimeError('secret'), '']), patch('builtins.print'):
                swarm.report_failure_state()
                data = json.loads((Path(directory) / 'last-failed-state.json').read_text())
                self.assertEqual(data['unavailable'], ['service update states'])
                self.assertEqual(data['local_containers'], [])

    def test_budget_expiry_and_disk_failure_do_not_raise(self):
        with patch.object(swarm.time, 'monotonic', side_effect=[0, 31, 32]), patch.object(swarm, 'docker') as docker, patch.object(swarm, 'write', side_effect=OSError('disk')), patch('builtins.print') as output:
            swarm.report_failure_state()
            docker.assert_not_called()
            self.assertIn('manager-local container health', str(output.call_args_list))

    def test_diagnostic_failure_does_not_block_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            for name in ('current', 'candidate'):
                (private / (name + '.json')).write_text(json.dumps({'file': name + '.json'}))
            events = []
            def docker(*args, **kwargs):
                events.append(args)
                if args[:2] == ('stack', 'ps'):
                    raise RuntimeError('history unavailable')
                return ''
            def fail_snapshot():
                events.append(('snapshot',))
                raise RuntimeError('snapshot unavailable')
            with patch.object(swarm, 'PRIVATE', private), patch.object(swarm, 'docker', side_effect=docker), patch.object(swarm, 'check', side_effect=[RuntimeError('unhealthy'), None]), patch.object(swarm, 'report_failure_state', side_effect=fail_snapshot), patch('builtins.print'):
                with self.assertRaisesRegex(RuntimeError, 'unhealthy'):
                    swarm.apply()
            self.assertEqual(events[1], ('snapshot',))
            self.assertEqual(events[-1][-2], 'current.json')
            self.assertFalse((private / 'previous.json').exists())


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
