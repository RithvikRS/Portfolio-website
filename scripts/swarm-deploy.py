#!/usr/bin/env python3
"""Deploy the two-node Swarm; keep all persistent state on the labeled data node."""
import argparse
import copy
import fcntl
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / '.swarm'
DOCKER = ['sudo', '-n', 'docker']
CORE = ['app', 'auth', 'ntfy', 'portainer', 'caddy']
ALL = CORE + ['agent', 'node2']


def run(args, timeout=180, data=None):
    result = subprocess.run(args, input=data, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        PRIVATE.mkdir(mode=0o700, exist_ok=True)
        (PRIVATE / 'last-command-error.txt').write_text(result.stderr, encoding='utf-8')
        raise RuntimeError('Command failed; read the private .swarm/last-command-error.txt on the manager.')
    return result.stdout.strip()


def docker(*args, **kwargs):
    return run(DOCKER + list(args), **kwargs)


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def escape(value):
    # stack deploy interpolates JSON strings too. Preserve literal password dollars.
    if isinstance(value, str):
        return value.replace('$', '$$')
    if isinstance(value, list):
        return [escape(v) for v in value]
    if isinstance(value, dict):
        return {k: escape(v) for k, v in value.items()}
    return value


def image(reference):
    try:
        info = json.loads(docker('image', 'inspect', reference))[0]
    except RuntimeError:
        print('Pulling required image ' + reference, flush=True)
        docker('pull', reference, timeout=600)
        info = json.loads(docker('image', 'inspect', reference))[0]
    if info.get('RepoDigests'):
        return info['RepoDigests'][0]
    raise RuntimeError('A service image has no immutable registry digest: ' + reference)


def render(compose, settings, app_image, pins, secret, release, root=ROOT):
    network = ipaddress.ip_network(settings['backend_subnet'])
    if network.version != 4 or network.prefixlen != 24 or not network.is_private:
        raise RuntimeError('Use a dedicated private IPv4 /24 for the proxy network.')
    result = {'version': '3.8', 'services': {}, 'networks': {}, 'volumes': {}, 'configs': {}}
    keep = ['command', 'entrypoint', 'user', 'environment', 'read_only', 'healthcheck', 'stop_grace_period', 'logging', 'cap_drop', 'cap_add', 'tmpfs']
    for name in CORE:
        source = compose['services'][name]
        service = {k: copy.deepcopy(source[k]) for k in keep if k in source and source[k] is not None}
        service['image'] = app_image if name == 'app' else pins[name]
        service['networks'] = ['swarm_' + n for n in source['networks']]
        service['volumes'] = []
        for mount in source.get('volumes', []):
            if mount['type'] == 'bind' and Path(mount['source']).is_relative_to(root / 'deploy'):
                continue
            clean = {k: v for k, v in mount.items() if k in ('type', 'source', 'target', 'read_only')}
            if clean['type'] == 'volume':
                volume = clean['source']
                result['volumes'][volume] = {'external': True, 'name': 'portfolio_' + volume}
            service['volumes'].append(clean)
        limits = {'memory': str(source.get('mem_limit', 256 * 1024 * 1024))}
        service['deploy'] = {'replicas': 1, 'placement': {'constraints': [settings['data_constraint']]},
            'resources': {'limits': limits}, 'restart_policy': {'condition': 'any', 'delay': '5s'},
            'update_config': {'parallelism': 1, 'order': 'stop-first', 'failure_action': 'pause', 'monitor': '45s'},
            'rollback_config': {'parallelism': 1, 'order': 'stop-first', 'monitor': '45s'}}
        if name == 'app':
            service['environment']['TRUSTED_PROXY_IPS'] = str(network)
        if name == 'caddy':
            service['networks'].append('swarm_node2')
            service['ports'] = [{'target': p, 'published': p, 'protocol': proto, 'mode': 'host'} for p, proto in [(80, 'tcp'), (443, 'tcp'), (443, 'udp')]]
        if name == 'portainer':
            service['networks'].append('swarm_agent')
            service.setdefault('environment', {})['AGENT_SECRET'] = secret
        result['services'][name] = service
    for service, source, target in [
        ('caddy', 'deploy/Caddyfile.swarm', '/etc/caddy/site/Caddyfile.docker'),
        ('auth', 'deploy/authelia/configuration.yml', '/etc/authelia/configuration.yml'),
        ('ntfy', 'deploy/ntfy/server.yml', '/etc/ntfy/server.yml')]:
        raw = (root / source).read_bytes()
        suffix = hashlib.sha256(raw).hexdigest()[:16]
        name = service + '_' + suffix
        path = release / (name + '.conf')
        path.write_bytes(raw)
        result['configs'][name] = {'file': str(path)}
        result['services'][service]['configs'] = [{'source': name, 'target': target, 'mode': 292}]
    agent = {'image': pins['agent'], 'environment': {'AGENT_CLUSTER_ADDR': 'tasks.agent', 'AGENT_SECRET': secret},
        'volumes': [{'type': 'bind', 'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'},
                    {'type': 'bind', 'source': '/var/lib/docker/volumes', 'target': '/var/lib/docker/volumes'}],
        'networks': ['swarm_agent'], 'deploy': {'mode': 'global', 'placement': {'constraints': ['node.platform.os == linux']},
        'resources': {'limits': {'memory': '128M'}}, 'restart_policy': {'condition': 'any', 'delay': '5s'}}}
    result['services']['agent'] = agent
    result['services']['node2'] = {'image': pins['node2'], 'networks': ['swarm_node2'],
        'deploy': {'replicas': 1, 'placement': {'constraints': [settings['worker_constraint']]},
        'resources': {'limits': {'memory': '64M'}}, 'restart_policy': {'condition': 'any', 'delay': '5s'}},
        'read_only': True, 'cap_drop': ['ALL']}
    for service in result['services'].values():
        for name in service['networks']:
            result['networks'][name] = {'driver': 'overlay', 'attachable': False}
    result['networks']['swarm_backend']['ipam'] = {'config': [{'subnet': str(network)}]}
    return result


def prepare(reuse_image=None):
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    print(run(['python3', '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']), flush=True)
    settings = json.loads((ROOT / 'deploy/swarm.json').read_text())
    compose = json.loads(docker('compose', '--env-file', '.env.production', '-f', 'compose.production.yaml', 'config', '--format', 'json'))
    nodes = json.loads(docker('node', 'inspect', *docker('node', 'ls', '-q').split()))
    data_nodes = [n for n in nodes if n['Spec'].get('Labels', {}).get('portfolio.data') == 'true']
    if len(data_nodes) != 1 or data_nodes[0]['ID'] != json.loads(docker('info', '--format', '{{json .Swarm}}'))['NodeID']:
        raise RuntimeError('Run on the sole labeled data-node manager.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3)
    release = PRIVATE / 'releases' / stamp
    release.mkdir(parents=True, mode=0o700)
    app_image = 'rithvik-portfolio:swarm-' + stamp.lower()
    domain = compose['services']['auth']['environment']['DOMAIN']
    revision = run(['git', 'rev-parse', 'HEAD'])
    if reuse_image:
        docker('image', 'inspect', reuse_image)
        app_image = reuse_image
    else:
        print('Building and testing the portfolio image before changing running services...', flush=True)
        docker('build', '--build-arg', 'SITE_URL=https://' + domain + '/', '--build-arg', 'VCS_REF=' + revision,
               '-t', app_image, '.', timeout=1500)
    pins = {name: image(compose['services'][name]['image']) for name in CORE if name != 'app'}
    pins.update({name: image(settings[name + '_image']) for name in ['agent', 'node2']})
    docker('image', 'tag', pins['node2'], 'portfolio-node2:current')
    secret_path = ROOT / '.portainer/agent-secret'
    if not secret_path.exists():
        secret_path.write_text(secrets.token_urlsafe(40) + '\n')
        secret_path.chmod(0o600)
    stack = render(compose, settings, app_image, pins, secret_path.read_text().strip(), release)
    write(release / 'stack.json', escape(stack))
    docker('stack', 'config', '-c', str(release / 'stack.json'))
    # Keep validation output private; rendered configuration contains credentials.
    auth = compose['services']['auth']
    docker('compose', '--env-file', '.env.production', '-f', 'compose.production.yaml', 'run', '--rm', '--no-deps', '-T',
           'auth', 'config', 'validate', '--config', '/etc/authelia/configuration.yml', '--config.experimental.filters', 'template')
    docker('run', '--rm', '--network', 'none', '-e', 'DOMAIN=' + domain,
           '-e', 'NTFY_DOMAIN=' + compose['services']['caddy']['environment']['NTFY_DOMAIN'],
           '-v', str(ROOT / 'deploy') + ':/etc/caddy/site:ro', pins['caddy'], 'caddy', 'validate',
           '--config', '/etc/caddy/site/Caddyfile.swarm', '--adapter', 'caddyfile')
    write(PRIVATE / 'candidate.json', {'file': str(release / 'stack.json'), 'image': app_image, 'revision': revision, 'release': stamp})
    print('Prepared and validated release ' + stamp, flush=True)


def container(service):
    ids = docker('ps', '-q', '--filter', 'label=com.docker.swarm.service.name=portfolio_' + service).split()
    if len(ids) != 1:
        raise RuntimeError('Expected one local task for ' + service)
    return ids[0]


def wait_ready(timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = True
        for name in ALL:
            try:
                tasks = docker('service', 'ps', '--filter', 'desired-state=running', '-q', 'portfolio_' + name).split()
                details = json.loads(docker('inspect', *tasks)) if tasks else []
                wanted = 2 if name == 'agent' else 1
                if len(details) != wanted or any(t['Status']['State'] != 'running' for t in details):
                    ready = False
            except RuntimeError:
                ready = False
        if ready:
            for name in CORE:
                info = json.loads(docker('inspect', container(name)))[0]
                if not info['State']['Running'] or info['State'].get('Health', {}).get('Status', 'healthy') != 'healthy':
                    ready = False
        if ready:
            return
        time.sleep(5)
    raise RuntimeError('Swarm tasks did not converge; inspect docker service ps before retrying.')


def check():
    wait_ready()
    info = json.loads(docker('inspect', container('caddy')))[0]
    env = dict(v.split('=', 1) for v in info['Config']['Env'] if '=' in v)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    checks = [(f'https://{env["DOMAIN"]}{p}', (200,)) for p in ['/', '/api/contact', '/auth/api/health', '/blog/', '/learn/']]
    checks += [(f'https://{env["DOMAIN"]}{p}', (302, 303, 401)) for p in ['/admin/', '/admin/notes/api/export', '/portainer/', '/node2/']]
    checks += [(f'https://{env["NTFY_DOMAIN"]}/v1/health', (200,))]
    for url, expected in checks:
        request = urllib.request.Request(url, headers={'Remote-User': 'rithvik', 'Remote-Groups': 'admins'})
        try:
            with opener.open(request, timeout=20) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        if status not in expected:
            raise RuntimeError('HTTP validation failed for ' + url + ': ' + str(status))
    docker('exec', container('caddy'), 'wget', '-q', '-T', '10', '-O', '-', 'http://node2:80')
    docker('exec', container('caddy'), 'wget', '-q', '-T', '10', '-O', '-', 'http://portainer:9000/api/status')
    run(['python3', 'scripts/setup-ntfy.py', 'check'])
    print('All seven services converged; HTTPS, protected routes, node 2, Portainer and ntfy access checks passed.', flush=True)


def apply():
    candidate = json.loads((PRIVATE / 'candidate.json').read_text())
    old = json.loads((PRIVATE / 'current.json').read_text()) if (PRIVATE / 'current.json').exists() else None
    try:
        print('Applying Swarm release; persistent services update one at a time per service.', flush=True)
        docker('stack', 'deploy', '--resolve-image', 'never', '-c', candidate['file'], 'portfolio')
        check()
        print(run(['python3', 'scripts/setup-portainer.py', '--configure', '--swarm']), flush=True)
        print(run(['python3', 'scripts/swarm-portainer.py']), flush=True)
    except Exception:
        if old:
            print('Validation failed; restoring the last successful Swarm specification.', flush=True)
            docker('stack', 'deploy', '--resolve-image', 'never', '-c', old['file'], 'portfolio')
            check()
        raise
    if old and old['file'] != candidate['file']:
        write(PRIVATE / 'previous.json', old)
    write(PRIVATE / 'current.json', candidate)
    (PRIVATE / 'enabled').touch(mode=0o600)
    docker('image', 'tag', candidate['image'], 'rithvik-portfolio:production')
    print(run(['python3', 'scripts/deploy-images.py', '--sudo', '--swarm', 'complete'], timeout=300), flush=True)
    print('Swarm deployment completed.', flush=True)


def rollback():
    if not (PRIVATE / 'previous.json').exists():
        raise RuntimeError('No previous Swarm release exists yet. Follow deploy/SWARM.md for initial migration recovery.')
    previous = json.loads((PRIVATE / 'previous.json').read_text())
    current = json.loads((PRIVATE / 'current.json').read_text())
    docker('stack', 'deploy', '--resolve-image', 'never', '-c', previous['file'], 'portfolio')
    check()
    write(PRIVATE / 'current.json', previous)
    write(PRIVATE / 'previous.json', current)
    docker('image', 'tag', previous['image'], 'rithvik-portfolio:production')
    print(run(['python3', 'scripts/deploy-images.py', '--sudo', '--swarm', 'complete'], timeout=300), flush=True)
    print('Restored the previous successful Swarm release.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'apply', 'deploy', 'check', 'rollback'])
    parser.add_argument('--reuse-image', help='Render using an existing local app image; skip the build.')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    lock = None
    if args.action != 'check' and os.environ.get('PORTFOLIO_DEPLOY_LOCK_HELD') != '1':
        lock = open(ROOT / '.git/portfolio-deploy.lock', 'a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.action in ['prepare', 'deploy']:
        prepare(args.reuse_image)
    if args.action in ['apply', 'deploy']:
        apply()
    if args.action == 'check':
        check()
    if args.action == 'rollback':
        rollback()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        sys.exit('Swarm operation stopped: ' + str(error))
