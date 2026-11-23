#!/usr/bin/env python3
"""Test a cached Rakazo image with disposable, resource-limited containers."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
POSTGRES = 'postgres:18-alpine@sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395'
SPEC = importlib.util.spec_from_file_location('rakazo_build', ROOT/'scripts/build-rakazo-app.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def validate_host(info, endpoint, ampere_pilot=False):
    if not endpoint.startswith(('unix://', 'npipe://')):
        raise RuntimeError('Use a local disposable Docker engine, not a remote endpoint.')
    swarm = info.get('Swarm', {})
    approved_worker = (ampere_pilot and swarm.get('NodeID') == build.AMPERE_NODE
                       and swarm.get('LocalNodeState') == 'active'
                       and swarm.get('ControlAvailable') is False)
    if ampere_pilot and not approved_worker:
        raise RuntimeError('Ampere pilot requires the exact approved worker, never a manager.')
    if info.get('OSType') != 'linux' or (not approved_worker and swarm.get('LocalNodeState') not in ('inactive', 'disabled')):
        raise RuntimeError('Refusing a Swarm or non-Linux engine without the exact Ampere pilot opt-in.')
    if int(info.get('MemTotal', 0)) < 4*1024**3 or int(info.get('NCPU', 0)) < 2:
        raise RuntimeError('Provide at least 4 GiB RAM and two CPUs to the disposable engine.')


def validate_reference(image):
    if not re.fullmatch(r'(?:sha256:|[^\s@]+@sha256:)[0-9a-f]{64}', image):
        raise RuntimeError('Supply a cached image ID or immutable registry digest, not a tag.')


def limits(memory, cpus="1.5"):
    return ['--memory', memory, '--memory-swap', memory, '--cpus', cpus,
            '--pids-limit', '256', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges']


def database_args(name, network, database, password):
    return ['create', '--name', name, '--network', network, '--network-alias', 'verify-db',
            *limits('1g', '0.5'), '--user', '70:70', '--read-only',
            '--tmpfs', '/var/lib/postgresql:rw,nosuid,nodev,size=1073741824,mode=0700,uid=70,gid=70',
            '--tmpfs', '/var/run/postgresql:rw,nosuid,nodev,size=16777216,mode=1777',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=67108864,mode=1777',
            '-e', 'POSTGRES_USER=verify_owner', '-e', 'POSTGRES_DB='+database,
            '-e', 'POSTGRES_PASSWORD='+password, POSTGRES]


def application_args(name, network, image, environment, command, workdir):
    result = ['create', '--name', name, '--network', network, *limits('2g'),
              '--user', 'node', '--workdir', workdir,
              '--tmpfs', '/app/node_modules/.vite-temp:rw,noexec,nosuid,nodev,size=67108864,mode=0700,uid=1000,gid=1000',
              '--entrypoint', command[0]]
    for key, value in environment.items():
        result += ['-e', key+'='+value]
    return result + [image, *command[1:]]


def web_args(name, image):
    # Match the planned web service's read-only root, writable tmpfs and resource limit.
    return ['create', '--name', name, '--network', 'none', *limits('512m', '0.5'),
            '--user', '1000:1000', '--read-only', '--workdir', '/app/apps/web',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=67108864,mode=1777',
            '--tmpfs', '/app/apps/web/asset-archive:rw,nosuid,nodev,size=134217728,mode=1777',
            '--tmpfs', '/app/apps/web/node_modules/.vite-temp:rw,nosuid,nodev,size=67108864,mode=1777',
            '-e', 'NODE_ENV=production', '-e', 'WORKSPACE_ONLY=true',
            '-e', 'NODE_OPTIONS=--max-old-space-size=320',
            '-e', 'RAKAZO_HOST=rakazo.example.test', '-e', 'RAKAZO_ALLOWED_HOSTS=localhost,127.0.0.1',
            '-e', 'WEB_ORIGIN=https://rakazo.example.test', '-e', 'API_PROXY_TARGET=http://127.0.0.1:3100',
            '-e', 'SCREEN_PROXY_SECRET='+secrets.token_hex(32),
            '--entrypoint', 'node', image, 'node_modules/vite/bin/vite.js',
            'preview', '--host', '0.0.0.0', '--port', '5173']


class Docker:
    def __init__(self, sudo=False):
        self.prefix = (['sudo', '-n'] if sudo else []) + ['docker']

    def call(self, *args, timeout=120):
        try:
            result = subprocess.run([*self.prefix, *args], capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('Docker operation unavailable or timed out: '+args[0]) from None
        if result.returncode:
            # Never emit command arguments, database URLs or container logs.
            raise RuntimeError('Docker operation failed: '+args[0]+'. No credentials or container logs printed.')
        return (result.stdout + (result.stderr if args[0] == 'logs' else '')).strip()


def verify(image, check_only=False, docker=None, ampere_pilot=False, diagnostics_dir=None):
    validate_reference(image)
    docker = docker or Docker()
    context = json.loads(docker.call('context', 'inspect'))[0]
    endpoint = os.environ.get('DOCKER_HOST') or context['Endpoints']['docker']['Host']
    info = json.loads(docker.call('info', '--format', '{{json .}}'))
    validate_host(info, endpoint, ampere_pilot)
    if ampere_pilot:
        available = next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        if available < 6*1024**3 or shutil.disk_usage(info['DockerRootDir']).free < 3*1024**3:
            raise RuntimeError('Ampere must retain at least 6 GiB available RAM and 3 GiB Docker disk before tests.')
    inputs = {'build-rakazo-app.py': (ROOT/'scripts/build-rakazo-app.py').read_bytes()}
    for name in build.PATCH_NAMES:
        inputs[name] = (ROOT/'deploy/rakazo'/name).read_bytes()
        build.validate_patch(inputs[name])
    fingerprint, _ = build.input_fingerprint(inputs)
    app = json.loads(docker.call('image', 'inspect', image))[0]
    build.verify_image(app, fingerprint)
    pg = json.loads(docker.call('image', 'inspect', POSTGRES))[0]
    arch = {'aarch64':'arm64', 'x86_64':'amd64'}.get(info.get('Architecture'), info.get('Architecture'))
    if app['Architecture'] != arch or pg['Architecture'] != arch or pg['Os'] != 'linux':
        raise RuntimeError('Use native matching images on a disposable ARM64 engine; emulation is not a release check.')
    if check_only:
        print('Disposable-engine preflight passed. No resources created.')
        return
    suffix = uuid.uuid4().hex[:12]
    prefix = 'rakazo-verify-'+suffix
    database = 'rakazo_workspace_verify_'+suffix
    owner_password, app_password = secrets.token_hex(32), secrets.token_hex(32)
    environment = {
        'DATABASE_URL': f'postgres://rakazo_app:{app_password}@verify-db:5432/{database}',
        'DATABASE_MIGRATION_URL': f'postgres://verify_owner:{owner_password}@verify-db:5432/{database}',
        'WORKSPACE_ONLY':'true', 'SANDBOX_PROVIDER':'none', 'CLOUD_AGENT_PROVIDER':'none',
        'AUTH_PASSWORD_ENABLED':'false', 'USER_DEVICES_ENABLED':'false',
        'VERIFY_RAKAZO_DISPOSABLE':'1', 'VERIFY_DATABASE':'1', 'NODE_ENV':'test',
        'NODE_OPTIONS':'--max-old-space-size=1536', 'CI':'true',
    }
    network = None
    containers = []
    phase = 'creating disposable resources'
    cleanup_errors = []
    def create(args):
        identifier = docker.call(*args)
        containers.append(identifier)
        return identifier
    def execute(identifier):
        docker.call('start', identifier)
        if docker.call('wait', identifier, timeout=600) != '0':
            raise RuntimeError('Container exited unsuccessfully. No test logs printed because they may contain disposable credentials.')
    try:
        network = docker.call('network', 'create', '--internal', prefix)
        db = create(database_args(prefix+'-db', network, database, owner_password))
        docker.call('start', db)
        phase = 'waiting for the disposable database'
        for _ in range(60):
            try:
                docker.call('exec', db, 'pg_isready', '-h', '127.0.0.1', '-U', 'verify_owner', '-d', database, timeout=10)
                break
            except RuntimeError:
                time.sleep(1)
        else:
            raise RuntimeError('Disposable PostgreSQL did not become ready.')
        phase = 'migrating the disposable database'
        migrate = create(application_args(prefix+'-migrate', network, image, environment,
                         ['node', 'dist/cli/migrate-database.js'], '/app/apps/api'))
        execute(migrate)
        # Free the migration container's writable layer before the API fixture.
        docker.call('rm', '-v', migrate)
        containers.remove(migrate)
        phase = 'running granted-user OIDC, isolation, revocation and execution-denial checks'
        test = create(application_args(prefix+'-test', network, image, environment,
                      ['pnpm', 'exec', 'vitest', 'run', 'apps/api/src/verify-workspace.postgres.test.ts', '--maxWorkers=1'], '/app'))
        docker.call('cp', str(ROOT/'deploy/rakazo/verify-workspace.postgres.test.ts'),
                    test+':/app/apps/api/src/verify-workspace.postgres.test.ts')
        execute(test)
        docker.call('rm', '-v', test)
        containers.remove(test)
        phase = 'checking read-only web startup without network access'
        web = create(web_args(prefix+'-web', image))
        docker.call('start', web)
        for _ in range(45):
            try:
                docker.call('exec', web, 'node', '-e',
                            "fetch('http://127.0.0.1:5173/').then(async r=>process.exit(r.ok&&(await r.text()).includes('<html')?0:1)).catch(()=>process.exit(1))", timeout=10)
                break
            except RuntimeError:
                time.sleep(1)
        else:
            raise RuntimeError('Read-only web service did not serve its HTML.')
        print('Disposable database/OIDC fixture and networkless read-only web startup passed; no production data or provider keys were used.')
    except RuntimeError as error:
        if diagnostics_dir is not None:
            private = Path(diagnostics_dir)/prefix
            private.mkdir(parents=True, mode=0o700)
            private.chmod(0o700)
            for index, identifier in enumerate(containers):
                try:
                    logs = docker.call('logs', identifier)
                except RuntimeError:
                    logs = 'Container logs unavailable.'
                for password in (owner_password, app_password):
                    logs = logs.replace(password, '[redacted]')
                target = private/('container-'+str(index)+'.log')
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w') as stream:
                    stream.write(logs)
            print('Private failure diagnostics saved outside container output: '+str(private), file=sys.stderr)
        raise RuntimeError('Verification stopped while '+phase+': '+str(error)) from None
    finally:
        for identifier in reversed(containers):
            try:
                docker.call('rm', '-f', '-v', identifier)
            except RuntimeError:
                cleanup_errors.append(identifier)
        if network:
            try:
                docker.call('network', 'rm', network)
            except RuntimeError:
                cleanup_errors.append(network)
        if cleanup_errors:
            raise RuntimeError('Disposable cleanup incomplete; inspect only these resource IDs: '+', '.join(cleanup_errors))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Cached derived image ID/digest; no pull is performed.')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--sudo', action='store_true', help='Use sudo -n for local Docker.')
    parser.add_argument('--ampere-pilot', action='store_true', help='Explicitly allow only the approved Ampere worker for disposable tests.')
    parser.add_argument('--diagnostics-dir', help='Private directory outside Git for failure logs; never publish these files.')
    args = parser.parse_args()
    try:
        verify(args.image, args.check_only, Docker(args.sudo), args.ampere_pilot, args.diagnostics_dir)
    except (RuntimeError, KeyError, ValueError) as error:
        print(str(error) if isinstance(error, RuntimeError) else 'Invalid Docker metadata; verification stopped.', file=sys.stderr)
        sys.exit(1)
