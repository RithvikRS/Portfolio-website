#!/usr/bin/env python3
"""Smoke-test the exact web scratch mounts through Swarm, without live data or credentials."""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
NODE = 'tzqsl1t88r3l1i8zcqvcmredo'


def docker(*args, data=None):
    return subprocess.check_output(['sudo', '-n', 'docker', *args], input=data, text=True, timeout=180).strip()


def probe_spec(image, catalog):
    if not re.fullmatch(r'(?:[^\s@]+@)?sha256:[a-f0-9]{64}', image):
        raise ValueError('Use an immutable cached image ID or registry digest.')
    source = catalog['services']['rakazo_web']
    mounts = copy.deepcopy(source['volumes'])
    allowed = {'/tmp', '/app/apps/web/node_modules/.vite-temp', '/app/apps/web/asset-archive'}
    if ({m.get('target') for m in mounts} != allowed or len(mounts) != 3 or
            any(m.get('type') != 'tmpfs' or set(m) != {'type', 'target', 'tmpfs'} or
                set(m.get('tmpfs', {})) != {'size'} or type(m['tmpfs']['size']) is not int or
                not 0 < m['tmpfs']['size'] <= 256 * 1024**2 for m in mounts)):
        raise ValueError('Probe accepts only the three bounded scratch mounts; never host data.')
    targets = ['/app/apps/web/node_modules/.vite-temp', '/app/apps/web/asset-archive']
    health = "const fs=require('fs');for(const d of " + json.dumps(targets) + "){const p=d+'/permission-probe';fs.writeFileSync(p,'ok');fs.unlinkSync(p)}fetch('http://127.0.0.1:5173/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
    return {'version': '3.8', 'services': {'web': {
        'image': image, 'user': '1000:1000', 'working_dir': '/app/apps/web',
        'command': ['node', 'node_modules/vite/bin/vite.js', 'preview', '--host', '0.0.0.0', '--port', '5173'],
        'read_only': True, 'cap_drop': ['ALL'], 'volumes': mounts,
        'environment': {'SCREEN_PROXY_SECRET': 'disposable-permission-test-only-not-a-production-secret', 'NODE_ENV': 'production',
                        'RAKAZO_HOST': 'probe.test', 'RAKAZO_ALLOWED_HOSTS': '127.0.0.1,localhost',
                        'API_PROXY_TARGET': 'http://127.0.0.1:9', 'WEB_ORIGIN': 'https://probe.test'},
        'networks': ['isolated'], 'deploy': {'replicas': 1, 'placement': {'constraints': ['node.id == ' + NODE]},
            'resources': {'limits': {'memory': '512M', 'cpus': '0.5'}}, 'restart_policy': {'condition': 'none'}},
        'healthcheck': {'test': ['CMD', 'node', '-e', health], 'interval': '5s', 'timeout': '3s', 'start_period': '15s', 'retries': 3}
    }}, 'networks': {'isolated': {'driver': 'overlay', 'internal': True, 'attachable': False}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--ampere-pilot', action='store_true', required=True)
    args = parser.parse_args()
    swarm = json.loads(docker('info', '--format', '{{json .Swarm}}'))
    if not swarm.get('ControlAvailable') or swarm.get('NodeID') != 'dwftd8hlsxv1h055jhr20n310':
        raise RuntimeError('Run on the approved manager; only the approved Ampere worker executes the probe.')
    spec = probe_spec(args.image, json.loads((ROOT / 'deploy/swarm-services.json').read_text()))
    stack = 'rakazo-scratch-' + uuid.uuid4().hex[:12]
    try:
        docker('stack', 'deploy', '--resolve-image', 'never', '-c', '-', stack, data=json.dumps(spec))
        stable = None
        end = time.monotonic() + 150
        while time.monotonic() < end:
            ids = docker('service', 'ps', '-q', '--filter', 'desired-state=running', stack + '_web').split()
            tasks = json.loads(docker('inspect', *ids)) if ids else []
            if len(tasks) == 1 and tasks[0]['Status']['State'] == 'running':
                stable = stable or time.monotonic()
                if time.monotonic() - stable >= 30:
                    print('Swarm web startup and repeated scratch-write/HTTP health checks passed.')
                    return
            else:
                stable = None
            all_ids = docker('service', 'ps', '-q', stack + '_web').split()
            if all_ids:
                states = json.loads(docker('inspect', *all_ids))
                if any(t['Status']['State'] in ('failed', 'rejected') for t in states):
                    print(json.dumps([{'state': t['Status']['State'], 'error': t['Status'].get('Err', '')} for t in states]), flush=True)
                    print(docker('service', 'logs', '--tail', '15', stack + '_web'), flush=True)
                    raise RuntimeError('Swarm scratch probe failed.')
            time.sleep(3)
        raise RuntimeError('Swarm probe did not become healthy.')
    finally:
        docker('stack', 'rm', stack)
        for _ in range(30):
            services = docker('service', 'ls', '-q', '--filter', 'label=com.docker.stack.namespace=' + stack)
            networks = docker('network', 'ls', '-q', '--filter', 'label=com.docker.stack.namespace=' + stack)
            if not services and not networks:
                print('Removed the probe service and its isolated overlay.')
                break
            time.sleep(2)
        else:
            raise RuntimeError('Probe cleanup still pending: ' + stack)


if __name__ == '__main__':
    main()
