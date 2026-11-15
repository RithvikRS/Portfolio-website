import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('workspace_verify', ROOT/'scripts/verify-rakazo-workspace.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)
IMAGE = 'sha256:'+'a'*64


def candidate():
    inputs = {'build-rakazo-app.py': (ROOT/'scripts/build-rakazo-app.py').read_bytes()}
    inputs.update({name:(ROOT/'deploy/rakazo'/name).read_bytes() for name in verify.build.PATCH_NAMES})
    fingerprint, _ = verify.build.input_fingerprint(inputs)
    return {'Architecture':'arm64', 'Os':'linux', 'Config': {
        'User':'node', 'WorkingDir':'/app', 'Entrypoint':['docker-entrypoint.sh'],
        'Cmd':['pnpm', '--filter', '@rakazo/api', 'start'],
        'Labels':{'portfolio.rakazo.inputs':fingerprint, 'portfolio.rakazo.upstream':verify.build.UPSTREAM_SHA},
        'Env':['WORKSPACE_ONLY=true', 'NODE_ENV=production', 'SANDBOX_PROVIDER=none',
               'CLOUD_AGENT_PROVIDER=none', 'AUTH_PASSWORD_ENABLED=false', 'USER_DEVICES_ENABLED=false'],
    }}


class FakeDocker:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail
        self.created = 0
        self.waited = 0

    def call(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ('context','inspect'):
            return json.dumps([{'Endpoints':{'docker':{'Host':'unix:///var/run/docker.sock'}}}])
        if args[0] == 'info':
            return json.dumps({'OSType':'linux', 'Architecture':'aarch64', 'MemTotal':8*1024**3,
                               'NCPU':4, 'Swarm':{'LocalNodeState':'inactive'}})
        if args[:2] == ('image','inspect'):
            return json.dumps([candidate() if args[2] == IMAGE else {'Architecture':'arm64','Os':'linux'}])
        if args[:2] == ('network','create'): return 'network-id'
        if args[0] == 'create':
            self.created += 1
            return 'container-'+str(self.created)
        if args[0] == 'wait':
            self.waited += 1
            return '1' if self.fail == self.waited else '0'
        if args[0] == 'cp' and self.fail == 'copy': raise RuntimeError('copy failed')
        if args[:2] == ('rm','-f') and self.fail == 'cleanup': raise RuntimeError('remove failed')
        return ''


class ImageVerificationTests(unittest.TestCase):
    def test_cached_and_fresh_images_must_preserve_runtime_guards(self):
        image = candidate()
        fingerprint = image['Config']['Labels']['portfolio.rakazo.inputs']
        verify.build.verify_image(image, fingerprint)
        mutations = [
            ('User','root'), ('WorkingDir','/tmp'), ('Cmd',['sh']), ('Entrypoint',['sh']),
            ('Env',['WORKSPACE_ONLY=false']), ('Labels',{'portfolio.rakazo.inputs':fingerprint}),
        ]
        for key,value in mutations:
            with self.subTest(key=key):
                invalid=copy.deepcopy(image); invalid['Config'][key]=value
                with self.assertRaises(RuntimeError): verify.build.verify_image(invalid,fingerprint)
        for env in ['NODE_OPTIONS=--inspect=0.0.0.0', 'CI=true', 'SANDBOX_PROVIDER=docker', 'AUTH_PASSWORD_ENABLED=true']:
            invalid=copy.deepcopy(image); invalid['Config']['Env'].append(env)
            with self.assertRaises(RuntimeError): verify.build.verify_image(invalid,fingerprint)
        for key,value in [('Architecture','amd64'),('Os','windows')]:
            invalid=copy.deepcopy(image); invalid[key]=value
            with self.assertRaises(RuntimeError): verify.build.verify_image(invalid,fingerprint)


class DisposableRunnerTests(unittest.TestCase):
    def test_refuses_production_remote_small_and_nonlinux_engines(self):
        info={'OSType':'linux','NCPU':2,'MemTotal':4*1024**3,'Swarm':{'LocalNodeState':'inactive'}}
        verify.validate_host(info,'unix:///var/run/docker.sock')
        for key,value in [('Swarm',{'LocalNodeState':'active'}),('Swarm',{}),('OSType','windows'),('MemTotal',1),('NCPU',1)]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                verify.validate_host({**info,key:value},'unix:///var/run/docker.sock')
        for endpoint in ['ssh://production','tcp://host:2376','']:
            with self.assertRaises(RuntimeError): verify.validate_host(info,endpoint)

    def test_ampere_optin_accepts_only_exact_worker_and_never_manager(self):
        info={'OSType':'linux','NCPU':4,'MemTotal':24*1024**3,
              'Swarm':{'LocalNodeState':'active','NodeID':verify.build.AMPERE_NODE,'ControlAvailable':False}}
        with self.assertRaises(RuntimeError): verify.validate_host(info,'unix:///var/run/docker.sock')
        verify.validate_host(info,'unix:///var/run/docker.sock',True)
        for changes in [{'NodeID':'other'}, {'ControlAvailable':True}, {'LocalNodeState':'inactive'}]:
            invalid=copy.deepcopy(info); invalid['Swarm'].update(changes)
            with self.assertRaises(RuntimeError): verify.validate_host(invalid,'unix:///var/run/docker.sock',True)

    def test_requires_immutable_cached_image_before_any_docker_call(self):
        for value in ['app:latest','app@sha256:bad','', 'sha256:'+'A'*64]:
            docker=FakeDocker()
            with self.assertRaises(RuntimeError): verify.verify(value,docker=docker)
            self.assertEqual(docker.calls,[])

    def test_preflight_performs_no_mutations(self):
        docker=FakeDocker()
        with patch.dict(verify.os.environ,{},clear=True): verify.verify(IMAGE,True,docker)
        self.assertTrue(all(call[0] in ('context','info','image') for call in docker.calls))

    def test_resource_boundaries_and_success_cleanup(self):
        docker=FakeDocker()
        with patch.dict(verify.os.environ,{},clear=True): verify.verify(IMAGE,docker=docker)
        creates=[call for call in docker.calls if call[0]=='create']
        self.assertEqual(len(creates),4)
        self.assertIn(('network','create','--internal',next(c[3] for c in docker.calls if c[:2]==('network','create'))),docker.calls)
        for command in creates:
            self.assertFalse(set(command)&{'--privileged','--mount','--volume','-v','-p','--publish','--env-file'})
            self.assertIn('--memory',command)
            self.assertIn('--cap-drop',command)
        self.assertIn('--read-only',creates[0])
        readiness=next(c for c in docker.calls if c[0]=='exec')
        self.assertEqual(readiness[2:5],('pg_isready','-h','127.0.0.1'))
        self.assertIn('POSTGRES_DB=rakazo_workspace_verify_', ' '.join(creates[0]))
        self.assertEqual(docker.calls[-1],('network','rm','network-id'))
        self.assertIn(('rm','-v','container-2'),docker.calls)
        self.assertIn(('rm','-f','-v','container-1'),docker.calls)
        self.assertIn(('rm','-v','container-3'),docker.calls)
        self.assertIn(('rm','-f','-v','container-4'),docker.calls)
        self.assertIn('--read-only',creates[3])
        self.assertEqual(creates[3][creates[3].index('--network')+1],'none')
        self.assertFalse(any(c[0] in ('pull','push','service','stack','volume','build') for c in docker.calls))

    def test_cleanup_runs_after_migration_test_and_copy_failure(self):
        for failure in [1,2,'copy']:
            with self.subTest(failure=failure):
                docker=FakeDocker(failure)
                with patch.dict(verify.os.environ,{},clear=True), self.assertRaises(RuntimeError):
                    verify.verify(IMAGE,docker=docker)
                self.assertEqual(docker.calls[-1],('network','rm','network-id'))
                self.assertIn(('rm','-f','-v','container-1'),docker.calls)

    def test_cleanup_failure_is_reported_and_other_cleanup_still_attempted(self):
        docker=FakeDocker('cleanup')
        with patch.dict(verify.os.environ,{},clear=True), self.assertRaisesRegex(RuntimeError,'cleanup incomplete'):
            verify.verify(IMAGE,docker=docker)
        self.assertEqual(docker.calls[-1],('network','rm','network-id'))


if __name__ == '__main__': unittest.main()
