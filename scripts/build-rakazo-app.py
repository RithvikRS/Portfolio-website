#!/usr/bin/env python3
"""Build the workspace image on Ampere without credentials or host mounts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import uuid

BASE_IMAGE = 'ghcr.io/elie222/rakazo/app@sha256:908045c3b393f4d948ea6bed9cd86ab77fd32d467d2fdfa042805b34c5b851ea'
UPSTREAM_SHA = '747ece9641dcc60c95467ffae8ab2311fb1f3f81'
AMPERE_NODE = 'tzqsl1t88r3l1i8zcqvcmredo'
GIB = 1024**3
PATCH_NAMES = ('workspace-only.patch', 'workspace-ui.patch', 'native-assistant.patch')
ARTIFACTS = {
    'api-src': '/app/apps/api/src', 'api-dist': '/app/apps/api/dist',
    'web-src': '/app/apps/web/src', 'web-dist': '/app/apps/web/dist',
    'contracts-src': '/app/packages/contracts/src',
}
PATCH_PREFIXES = ('apps/api/src/', 'apps/web/src/', 'packages/contracts/src/')
BUILD_COMMAND = '''
set -eu
[ "$GIT_SHA" = "747ece9641dcc60c95467ffae8ab2311fb1f3f81" ]
cd /app
git apply --check /tmp/workspace-only.patch
git apply /tmp/workspace-only.patch
git apply --check /tmp/workspace-ui.patch
git apply /tmp/workspace-ui.patch
git apply --check /tmp/native-assistant.patch
git apply /tmp/native-assistant.patch
NODE_ENV=test pnpm exec vitest run apps/api/src/workspace-only.test.ts apps/api/src/native-assistant.test.ts apps/web/src/pages/WorkspaceOnly.test.tsx --maxWorkers=2
pnpm --filter @rakazo/api build
RAKAZO_ALLOW_DEV_SECRETS=1 pnpm --filter @rakazo/web build
'''


def run(args, *, timeout=120, capture=True):
    return subprocess.run(args, check=True, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None).stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_patch(data):
    text = data.decode('utf-8')
    paths = re.findall(r'^\+\+\+ (?:b/)?([^\r\n]+)', text, re.M)
    if not paths or 'GIT binary patch' in text:
        raise RuntimeError('Expected a text-only application patch.')
    for name in paths:
        if name == '/dev/null':
            raise RuntimeError('Deleted source files need explicit image assembly support.')
        if not name.startswith(PATCH_PREFIXES) or '..' in name.split('/'):
            raise RuntimeError('Patch changes an unapproved application path.')
    old = re.findall(r'^--- (?:a/)?([^\r\n]+)', text, re.M)
    for name in old:
        if name != '/dev/null' and (not name.startswith(PATCH_PREFIXES) or '..' in name.split('/')):
            raise RuntimeError('Patch reads an unapproved application path.')


def input_fingerprint(files):
    record = {'source': UPSTREAM_SHA, 'base_image': BASE_IMAGE,
              'assembly': 'stopped-bounded-compiler-commit',
              'files': {name: digest(data) for name, data in sorted(files.items())}}
    return digest(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()), record


def container_args(name):
    # The compiler is the only executable build phase. No BuildKit builder is used:
    # it would unpack a second large base image into an independent cache.
    return ['create', '--name', name, '--network', 'none', '--memory', '3g',
            '--memory-swap', '3g', '--cpus', '2', '--pids-limit', '512',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '0:0',
            '--env', 'NODE_OPTIONS=--max-old-space-size=2048',
            '--env', 'RAYON_NUM_THREADS=2', '--env', 'CI=true',
            BASE_IMAGE, 'sleep', 'infinity']


def commit_args(name, tag, fingerprint):
    # The container has never seen host mounts, sockets, keys or runtime secrets.
    # Restore a non-root production command instead of inheriting the compiler.
    changes = [
        'USER node', 'WORKDIR /app',
        'ENTRYPOINT ["docker-entrypoint.sh"]',
        'CMD ["pnpm", "--filter", "@rakazo/api", "start"]',
        'ENV NODE_ENV=production CI="" NODE_OPTIONS="" RAYON_NUM_THREADS=2',
        'ENV WORKSPACE_ONLY=true SANDBOX_PROVIDER=none CLOUD_AGENT_PROVIDER=none AUTH_PASSWORD_ENABLED=false USER_DEVICES_ENABLED=false',
        'LABEL portfolio.rakazo.inputs='+fingerprint,
        'LABEL portfolio.rakazo.upstream='+UPSTREAM_SHA,
    ]
    result = ['commit', '--pause=false']
    for change in changes:
        result.extend(['--change', change])
    return result+[name, tag]


def verify_image(image, fingerprint):
    """Apply the same checks to a fresh image and a cached checkpoint image."""
    config = image.get('Config') or {}
    env = dict(value.split('=', 1) for value in config.get('Env', []) if '=' in value)
    expected = {
        'WORKSPACE_ONLY': 'true', 'NODE_ENV': 'production',
        'SANDBOX_PROVIDER': 'none', 'CLOUD_AGENT_PROVIDER': 'none',
        'AUTH_PASSWORD_ENABLED': 'false', 'USER_DEVICES_ENABLED': 'false',
    }
    labels = config.get('Labels') or {}
    if (image.get('Architecture') != 'arm64' or image.get('Os') != 'linux'
            or labels.get('portfolio.rakazo.inputs') != fingerprint
            or labels.get('portfolio.rakazo.upstream') != UPSTREAM_SHA
            or config.get('User') != 'node' or config.get('WorkingDir') != '/app'
            or config.get('Entrypoint') != ['docker-entrypoint.sh']
            or config.get('Cmd') != ['pnpm', '--filter', '@rakazo/api', 'start']
            or any(env.get(key) != value for key, value in expected.items())
            or env.get('NODE_OPTIONS') or env.get('CI')):
        raise RuntimeError('Derived image verification failed; do not reuse or promote it.')


def artifact_manifest(context):
    files = {}
    for name in ARTIFACTS:
        for path in sorted((context/name).rglob('*')):
            if path.is_symlink():
                raise RuntimeError('Unexpected symlink in application build artifacts.')
            if path.is_file():
                files[path.relative_to(context).as_posix()] = digest(path.read_bytes())
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sudo', action='store_true', help='Use sudo -n for Docker access.')
    parser.add_argument('--check-only', action='store_true', help='Validate inputs and host without pulling or building.')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise RuntimeError('Build this image on the native ARM64 worker.')
    docker = (['sudo', '-n'] if args.sudo else []) + ['docker']
    def dc(*parts, **kwargs):
        return run(docker + list(parts), **kwargs)
    info = json.loads(dc('info', '--format', '{{json .}}'))
    if info['Swarm']['NodeID'] != AMPERE_NODE or info['Swarm']['ControlAvailable']:
        raise RuntimeError('Expected the existing Ampere worker, not a manager.')
    repo = Path(__file__).resolve().parents[1]
    inputs = {'build-rakazo-app.py': Path(__file__).read_bytes()}
    for name in PATCH_NAMES:
        inputs[name] = (repo/'deploy/rakazo'/name).read_bytes()
        validate_patch(inputs[name])
    fingerprint, record = input_fingerprint(inputs)
    tag = 'portfolio-rakazo:workspace-' + fingerprint[:16]
    root = Path(info['DockerRootDir'])
    free = shutil.disk_usage(root).free
    existing = subprocess.run(docker+['image', 'inspect', tag], capture_output=True, text=True)
    if existing.returncode == 0:
        image = json.loads(existing.stdout)[0]
        verify_image(image, fingerprint)
        print(json.dumps({'image': tag, 'image_id': image['Id'], 'inputs': fingerprint, 'reused': True}))
        return
    base = subprocess.run(docker+['image', 'inspect', BASE_IMAGE], capture_output=True, text=True)
    # Published base is ~1.21 GiB compressed. Allow unpacking, compiler output,
    # copied artifacts, the incremental committed layer and two GiB headroom.
    required = 3*GIB if base.returncode == 0 else 10*GIB
    if free < required:
        raise RuntimeError('Insufficient Docker filesystem headroom; preserve rollback images and free space deliberately.')
    if shutil.disk_usage(tempfile.gettempdir()).free < 3*GIB:
        raise RuntimeError('Insufficient temporary artifact staging space.')
    if args.check_only:
        print(json.dumps({'image': tag, 'inputs': fingerprint, 'preflight': 'passed',
                          'base_present': base.returncode == 0, 'free_bytes': free, 'required_bytes': required}))
        return
    if base.returncode:
        dc('pull', '--platform', 'linux/arm64', BASE_IMAGE, timeout=1200, capture=False)
    image = json.loads(dc('image', 'inspect', BASE_IMAGE))[0]
    if image['Architecture'] != 'arm64' or image['Os'] != 'linux':
        raise RuntimeError('Base image platform mismatch.')
    if image.get('Config', {}).get('Labels', {}).get('org.opencontainers.image.revision') != UPSTREAM_SHA:
        raise RuntimeError('Base image source revision mismatch.')
    if shutil.disk_usage(root).free < 3*GIB:
        raise RuntimeError('Base image leaves insufficient build headroom.')
    name = 'rakazo-workspace-build-' + uuid.uuid4().hex[:12]
    context = Path(tempfile.mkdtemp(prefix='rakazo-app-build-')).resolve()
    created = False
    try:
        for filename in PATCH_NAMES:
            (context/filename).write_bytes(inputs[filename])
        dc(*container_args(name)); created = True
        for filename in PATCH_NAMES:
            dc('cp', str(context/filename), name+':/tmp/'+filename)
        print('Compiling and testing in a networkless container limited to 3 GiB and two CPUs.', flush=True)
        dc('start', name)
        # The upstream scratch directories belong to node. Normalize them as that
        # user, without granting the compiler DAC/FOWNER capabilities. Swarm's
        # zero-mode tmpfs mounts inherit these persisted image permissions.
        dc('exec', '--user', '1000:1000', name, 'chmod', '1777',
           '/app/apps/web/node_modules/.vite-temp', '/app/apps/web/asset-archive')
        dc('exec', '--user', '0:0', name, 'sh', '-ec', BUILD_COMMAND, timeout=1200, capture=False)
        dc('stop', '--time', '10', name)
        container = json.loads(dc('inspect', '--size', name))[0]
        result = container['State']
        if result.get('OOMKilled'):
            raise RuntimeError('Bounded application build failed; no image was promoted.')
        for target, source in ARTIFACTS.items():
            directory = context/target; directory.mkdir()
            dc('cp', name+':'+source+'/.', str(directory), timeout=180)
            if args.sudo:
                run(['sudo', '-n', 'chown', '-R', str(os.getuid())+':'+str(os.getgid()), '--', str(directory)])
        record['inputs_digest'] = fingerprint
        record['artifacts'] = artifact_manifest(context)
        (context/'build-manifest.json').write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
        dc('cp', str(context/'build-manifest.json'), name+':/usr/local/share/rakazo-workspace-build.json')
        delta = int(container.get('SizeRw', -1))
        if delta < 0 or delta > GIB or shutil.disk_usage(root).free < 2*GIB+2*delta:
            raise RuntimeError('Insufficient headroom for the incremental image; no image was promoted.')
        dc(*commit_args(name, tag, fingerprint), timeout=600, capture=False)
        built = json.loads(dc('image', 'inspect', tag))[0]
        verify_image(built, fingerprint)
        print(json.dumps({'image': tag, 'image_id': built['Id'], 'inputs': fingerprint, 'reused': False}))
    finally:
        if created:
            subprocess.run(docker+['rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if context.parent == Path(tempfile.gettempdir()).resolve() and context.name.startswith('rakazo-app-build-'):
            shutil.rmtree(context)


if __name__ == '__main__':
    main()
