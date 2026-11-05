#!/usr/bin/env python3
"""Deploy the Swarm; keep all persistent state on the labeled data node."""
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
import re
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / '.swarm'
DOCKER = ['sudo', '-n', 'docker']
CORE = ['app', 'auth', 'ntfy', 'portainer', 'caddy']
RESERVED = set(CORE + ['agent'])


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


def registry_repository(reference):
    repository = reference.split('@', 1)[0]
    head, slash, tail = repository.rpartition('/')
    if ':' in tail:
        tail = tail.rsplit(':', 1)[0]
    repository = head + slash + tail
    parts = repository.split('/')
    if len(parts) == 1:
        return 'docker.io/library/' + repository
    if '.' not in parts[0] and ':' not in parts[0] and parts[0] != 'localhost':
        return 'docker.io/' + repository
    if parts[0] in ('index.docker.io', 'registry-1.docker.io'):
        parts[0] = 'docker.io'
    if parts[0] == 'docker.io' and len(parts) == 2:
        parts.insert(1, 'library')
    return '/'.join(parts)


def image(reference):
    try:
        info = json.loads(docker('image', 'inspect', reference))[0]
    except RuntimeError:
        print('Pulling required image ' + reference, flush=True)
        docker('pull', reference, timeout=600)
        info = json.loads(docker('image', 'inspect', reference))[0]
    # A local backup tag can become the first RepoDigest. Never change registries
    # or repositories when resolving a configured image for another Swarm node.
    repository = registry_repository(reference)
    requested_digest = reference.split('@', 1)[1] if '@' in reference else None
    for candidate in info.get('RepoDigests', []):
        if '@' not in candidate:
            continue
        digest = candidate.split('@', 1)[1]
        if registry_repository(candidate) == repository and (requested_digest is None or digest == requested_digest):
            return reference if requested_digest else candidate
    raise RuntimeError('No immutable digest matches the configured registry repository: ' + reference)


def load_catalog(root=ROOT):
    catalog = json.loads((root / 'deploy/swarm-services.json').read_text(encoding='utf-8'))
    allowed = {'services', 'networks', 'volumes', 'configs', 'secrets', 'caddy_networks', 'http_checks', 'internal_checks'}
    if set(catalog) - allowed:
        raise RuntimeError('Unknown service catalog keys: ' + ', '.join(sorted(set(catalog) - allowed)))
    return catalog


def add_catalog(result, catalog, pins, release, root, data_constraint):
    services = copy.deepcopy(catalog.get('services', {}))
    networks = copy.deepcopy(catalog.get('networks', {}))
    # Core identity and trusted-proxy networks must remain isolated.
    if set(services) & RESERVED or set(networks) & set(result['networks']):
        raise RuntimeError('The catalog cannot replace core services or networks.')
    for name, network in networks.items():
        if not re.fullmatch(r'swarm_[a-z][a-z0-9_]*', name):
            raise RuntimeError('Catalog networks must use a swarm_ prefix.')
        if network.get('driver', 'overlay') != 'overlay' or network.get('attachable', False) or network.get('external'):
            raise RuntimeError('Catalog networks must be private, non-attachable overlays.')
        network.update(driver='overlay', attachable=False)
    result['networks'].update(networks)
    caddy_networks = catalog.get('caddy_networks', [])
    if not isinstance(caddy_networks, list) or not set(caddy_networks) <= set(networks):
        raise RuntimeError('Caddy can join only networks declared in the catalog.')
    result['services']['caddy']['networks'].extend(caddy_networks)
    for name, volume in catalog.get('volumes', {}).items():
        if name in result['volumes'] or not volume.get('external') or not volume.get('name'):
            raise RuntimeError('Use unique external volumes with explicit names in the catalog.')
        result['volumes'][name] = copy.deepcopy(volume)
    mappings = {}
    for kind in ['configs', 'secrets']:
        mappings[kind] = {}
        for name, definition in catalog.get(kind, {}).items():
            if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
                raise RuntimeError('Use lowercase resource names with underscores.')
            key = 'extra_' + name
            if definition.get('external'):
                if set(definition) != {'external', 'name'} or not definition['name']:
                    raise RuntimeError('External configs/secrets require only external and name.')
                result.setdefault(kind, {})[key] = copy.deepcopy(definition)
            else:
                if set(definition) != {'file'}:
                    raise RuntimeError('Configs/secrets require a file or an external name.')
                path = (root / definition['file']).resolve()
                if not path.is_relative_to(root.resolve()):
                    raise RuntimeError('Config/secret source files must be inside the checkout.')
                raw = path.read_bytes()
                key += '_' + hashlib.sha256(raw).hexdigest()[:16]
                target = release / (kind + '_' + key)
                target.write_bytes(raw)
                target.chmod(0o600)
                result.setdefault(kind, {})[key] = {'file': str(target)}
            mappings[kind][name] = key
    private = root / '.swarm/services.private.json'
    overrides = json.loads(private.read_text(encoding='utf-8')) if private.exists() else {}
    if set(overrides) - set(services):
        raise RuntimeError('Private environment overrides reference an unknown catalog service.')
    allowed = {'image', 'command', 'entrypoint', 'user', 'environment', 'read_only', 'healthcheck',
               'stop_grace_period', 'logging', 'cap_drop', 'cap_add', 'tmpfs', 'deploy', 'networks',
               'volumes', 'configs', 'secrets', 'working_dir', 'hostname', 'dns', 'dns_search', 'extra_hosts'}
    for name, service in services.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', name) or set(service) - allowed:
            raise RuntimeError('Unsupported catalog service name or fields: ' + name)
        if not service.get('image') or not isinstance(service.get('environment', {}), dict):
            raise RuntimeError('Services require an image and mapping-style environment: ' + name)
        if not isinstance(overrides.get(name, {}), dict):
            raise RuntimeError('Private service overrides must be environment dictionaries.')
        service.setdefault('environment', {}).update(overrides.get(name, {}))
        service['image'] = pins[name]
        attached = service.get('networks', [])
        if not attached or not isinstance(attached, list) or not set(attached) <= set(networks):
            raise RuntimeError('Catalog services must join only their declared catalog networks: ' + name)
        deploy = service.setdefault('deploy', {})
        mode = deploy.get('mode', 'replicated')
        if mode not in ('replicated', 'global'):
            raise RuntimeError('Only replicated and global services are supported.')
        if mode == 'replicated':
            count = deploy.setdefault('replicas', 1)
            if type(count) is not int or count < 0:
                raise RuntimeError('Replicas must be a nonnegative integer.')
        elif 'replicas' in deploy:
            raise RuntimeError('Global services cannot specify replicas.')
        if not deploy.get('resources', {}).get('limits', {}).get('memory'):
            raise RuntimeError('Set a memory limit for each catalog service: ' + name)
        constraints = deploy.get('placement', {}).get('constraints', [])
        if not constraints:
            raise RuntimeError('Set explicit placement constraints for ' + name)
        deploy.setdefault('restart_policy', {'condition': 'any', 'delay': '5s'})
        deploy.setdefault('update_config', {'parallelism': 1, 'order': 'stop-first', 'failure_action': 'pause', 'monitor': '45s'})
        deploy.setdefault('rollback_config', {'parallelism': 1, 'order': 'stop-first', 'monitor': '45s'})
        for mount in service.get('volumes', []):
            if not isinstance(mount, dict) or mount.get('type') not in ('bind', 'volume'):
                raise RuntimeError('Use long-syntax bind or volume mounts.')
            if mount['type'] == 'volume' and mount['source'] not in catalog.get('volumes', {}):
                raise RuntimeError('Declare catalog volumes explicitly.')
            if mount['type'] == 'bind' and not Path(mount['source']).is_absolute():
                raise RuntimeError('Bind mounts require absolute server paths.')
            if not mount.get('read_only', False):
                if mode != 'replicated' or deploy['replicas'] != 1 or data_constraint not in constraints or deploy['update_config'].get('order') != 'stop-first' or deploy['rollback_config'].get('order') != 'stop-first':
                    raise RuntimeError('Writable storage requires one stop-first replica pinned to the data node: ' + name)
        for kind in ['configs', 'secrets']:
            resources = []
            for item in service.get(kind, []):
                item = {'source': item} if isinstance(item, str) else copy.deepcopy(item)
                source = item['source']
                if source not in mappings[kind]:
                    raise RuntimeError('Undeclared ' + kind + ' resource: ' + source)
                item['source'] = mappings[kind][source]
                # Keep the mount path stable when the Docker resource name changes.
                item.setdefault('target', '/' + source if kind == 'configs' else source)
                resources.append(item)
            if resources:
                service[kind] = resources
        result['services'][name] = service
    checks = catalog.get('http_checks', [])
    for item in checks:
        if set(item) != {'url', 'statuses'} or not item['url'].startswith('https://') or not item['statuses'] or any(type(n) is not int or not 100 <= n <= 599 for n in item['statuses']):
            raise RuntimeError('HTTP checks require an HTTPS url and status-code list.')
    internal = catalog.get('internal_checks', [])
    if any(not isinstance(url, str) or not url.startswith('http://') for url in internal):
        raise RuntimeError('Internal checks must be HTTP URLs reachable from Caddy.')
    write(release / 'checks.json', {'http': checks, 'internal': internal})


def render(compose, settings, app_image, pins, secret, release, root=ROOT, catalog=None):
    catalog = load_catalog(root) if catalog is None else catalog
    if set(compose['services']) != set(CORE):
        raise RuntimeError('Keep core services in compose.production.yaml; add other services to deploy/swarm-services.json.')
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
    for service in result['services'].values():
        for name in service['networks']:
            result['networks'][name] = {'driver': 'overlay', 'attachable': False}
    result['networks']['swarm_backend']['ipam'] = {'config': [{'subnet': str(network)}]}
    add_catalog(result, catalog, pins, release, root, settings['data_constraint'])
    return result


def pull_ci_image(reference, revision, username, token, domain):
    """Pull the merged commit by digest with job-scoped credentials, then forget them."""
    if not re.fullmatch(r'ghcr\.io/rithvikrs/portfolio-website@sha256:[a-f0-9]{64}', reference):
        raise RuntimeError('CI image must be a digest from the portfolio GHCR repository.')
    if not re.fullmatch(r'[a-f0-9]{40}', revision) or run(['git', 'rev-parse', 'HEAD']) != revision:
        raise RuntimeError('Server revision differs from the CI image revision; deploy the latest merged commit.')
    if not username or not token.strip():
        raise RuntimeError('CI registry credentials are missing.')
    # The parent directory is private and removed after pull, including on failure.
    with tempfile.TemporaryDirectory(prefix='registry-', dir=PRIVATE) as folder:
        command = DOCKER + ['--config', folder]
        run(command + ['login', 'ghcr.io', '-u', username, '--password-stdin'], data=token.strip() + '\n')
        run(command + ['pull', '--platform', 'linux/amd64', reference], timeout=600)
    info = json.loads(docker('image', 'inspect', reference))[0]
    labels = info.get('Config', {}).get('Labels', {}) or {}
    if (labels.get('org.opencontainers.image.revision') != revision or
            labels.get('io.github.rithvikrs.portfolio.site-url') != 'https://' + domain + '/'):
        raise RuntimeError('CI image revision or site URL does not match this deployment.')
    return info['Id']


def prepare(reuse_image=None):
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    ci_image = os.environ.get('PORTFOLIO_DEPLOY_IMAGE')
    registry_token = sys.stdin.read(16384) if ci_image else ''
    if ci_image and reuse_image:
        raise RuntimeError('Choose CI image or --reuse-image, not both.')
    run(['python3', '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'])
    print('Deployment tests passed.', flush=True)
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
    if ci_image:
        print('Pulling and verifying the CI-built app image; no server build is needed.', flush=True)
        app_id = pull_ci_image(ci_image, os.environ.get('PORTFOLIO_DEPLOY_REVISION', ''),
                              os.environ.get('PORTFOLIO_REGISTRY_USER', ''), registry_token, domain)
        registry_token = ''
        docker('image', 'tag', app_id, app_image)
    elif reuse_image:
        docker('image', 'inspect', reuse_image)
        app_image = reuse_image
    else:
        print('Building and testing the portfolio image before changing running services...', flush=True)
        docker('build', '--build-arg', 'SITE_URL=https://' + domain + '/', '--build-arg', 'VCS_REF=' + revision,
               '-t', app_image, '.', timeout=1500)
    pins = {name: image(compose['services'][name]['image']) for name in CORE if name != 'app'}
    catalog = load_catalog()
    pins['agent'] = image(settings['agent_image'])
    pins.update({name: image(service['image']) for name, service in catalog.get('services', {}).items()})
    for name in catalog.get('services', {}):
        docker('image', 'tag', pins[name], 'portfolio-' + name + ':current')
    secret_path = ROOT / '.portainer/agent-secret'
    if not secret_path.exists():
        secret_path.write_text(secrets.token_urlsafe(40) + '\n')
        secret_path.chmod(0o600)
    # Pin the manager-only app to its local immutable ID, avoiding Docker Hub lookups.
    app_id = json.loads(docker('image', 'inspect', app_image))[0]['Id']
    stack = render(compose, settings, app_id, pins, secret_path.read_text().strip(), release, catalog=catalog)
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
    write(PRIVATE / 'candidate.json', {'file': str(release / 'stack.json'), 'image': app_image, 'revision': revision, 'release': stamp, 'source_image': ci_image})
    print('Prepared and validated release ' + stamp, flush=True)


def container(service):
    ids = docker('ps', '-q', '--filter', 'label=com.docker.swarm.service.name=portfolio_' + service).split()
    if len(ids) != 1:
        raise RuntimeError('Expected one local task for ' + service)
    return ids[0]


def release_stack(path=None):
    if path is None:
        current = json.loads((PRIVATE / 'current.json').read_text(encoding='utf-8'))
        path = current['file']
    return json.loads(Path(path).read_text(encoding='utf-8'))


def service_counts_match(expected, rows):
    """Compare intended replicas with Docker's scheduler counts, including global mode."""
    actual = {row['Name']: row for row in rows}
    if set(actual) != {'portfolio_' + name for name in expected}:
        return False
    for name, service in expected.items():
        row = actual['portfolio_' + name]
        mode = service.get('deploy', {}).get('mode', 'replicated')
        if row['Mode'] != mode or not re.fullmatch(r'[0-9]+/[0-9]+', row['Replicas']):
            return False
        running, desired = map(int, row['Replicas'].split('/'))
        if running != desired:
            return False
        if mode == 'replicated' and desired != service.get('deploy', {}).get('replicas', 1):
            return False
        if mode == 'global' and desired == 0:
            return False
    return True


CANCEL_ERRORS = {
    'Canceled: context canceled',
    'rpc error: code = Canceled desc = context canceled',
    'failed to read config content: Canceled: context canceled',
    'failed to read config content: rpc error: code = Canceled desc = context canceled',
}


def timestamp(value):
    return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))


def can_resume_app(service, tasks, info, target, now):
    """Only recover a known Prepare cancellation after the exact app is healthy."""
    try:
        update = service.get('UpdateStatus') or {}
        spec = service['Spec']
        if update.get('State') != 'paused' or not re.fullmatch(r'sha256:[a-f0-9]{64}', target):
            return False
        if spec['Name'] != 'portfolio_app' or spec['TaskTemplate']['ContainerSpec']['Image'] != target:
            return False
        if spec['Mode']['Replicated']['Replicas'] != 1:
            return False
        start = timestamp(update['StartedAt'])
        recent = [t for t in tasks if timestamp(t['CreatedAt']) >= start]
        rejected = [t for t in recent if t['Status']['State'] in ('rejected', 'failed')]
        if not rejected or any(t['Status']['State'] != 'rejected' or
                t['Status'].get('Err') not in CANCEL_ERRORS or
                t['Spec']['ContainerSpec']['Image'] != target for t in rejected):
            return False
        running = [t for t in tasks if t['DesiredState'] == 'running']
        if len(running) != 1 or running[0]['Status']['State'] != 'running':
            return False
        task = running[0]
        if task['Spec']['ContainerSpec']['Image'] != target or timestamp(task['CreatedAt']) < start:
            return False
        state = info['State']
        health = state.get('Health', {})
        if (not state['Running'] or state.get('OOMKilled') or health.get('Status') != 'healthy'
                or health.get('FailingStreak') != 0 or info['Config']['Image'] != target
                or task['Status']['ContainerStatus']['ContainerID'] != info['Id']):
            return False
        # Require a full monitor window plus three consecutive successful probes.
        probes = health.get('Log', [])[-3:]
        return ((now - timestamp(state['StartedAt'])).total_seconds() >= 45
                and len(probes) == 3 and all(p['ExitCode'] == 0 for p in probes))
    except (KeyError, TypeError, ValueError):
        return False


def resume_canceled_app(expected, descriptions):
    service = next((s for s in descriptions if s['Spec']['Name'] == 'portfolio_app'), None)
    if service is None or (service.get('UpdateStatus') or {}).get('State') != 'paused':
        return False
    ids = docker('service', 'ps', '-q', 'portfolio_app').split()
    tasks = json.loads(docker('inspect', *ids)) if ids else []
    info = json.loads(docker('inspect', container('app')))[0]
    if not can_resume_app(service, tasks, info, expected['app']['image'], datetime.datetime.now(datetime.timezone.utc)):
        return False
    report_failed_tasks()
    print('Resuming app update once after a known Docker cancellation; the target app is healthy.', flush=True)
    # Docker resumes a paused update without --force or changing its task specification.
    try:
        docker('service', 'update', '--detach', '--no-resolve-image', 'portfolio_app')
    except Exception:
        print('App resume request failed; no further resume attempts will be made.', flush=True)
    return True


def wait_ready(stack_path=None, timeout=300, recover_app=False):
    expected = release_stack(stack_path)['services']
    deadline = time.monotonic() + timeout
    resumed = False
    while time.monotonic() < deadline:
        try:
            rows = [json.loads(line) for line in docker('service', 'ls', '--filter',
                    'label=com.docker.stack.namespace=portfolio', '--format', '{{json .}}').splitlines()]
            ready = service_counts_match(expected, rows)
            if ready:
                descriptions = json.loads(docker('service', 'inspect', *['portfolio_' + name for name in expected]))
                if recover_app and not resumed:
                    resumed = resume_canceled_app(expected, descriptions)
                if any((item.get('UpdateStatus') or {}).get('State', 'completed') != 'completed' for item in descriptions):
                    ready = False
                for name in expected:
                    tasks = docker('service', 'ps', '--filter', 'desired-state=running', '-q', 'portfolio_' + name).split()
                    details = json.loads(docker('inspect', *tasks)) if tasks else []
                    row = next(row for row in rows if row['Name'] == 'portfolio_' + name)
                    desired = int(row['Replicas'].split('/')[1])
                    if len(details) != desired or any(t['Status']['State'] != 'running' for t in details):
                        ready = False
                for name in CORE:
                    info = json.loads(docker('inspect', container(name)))[0]
                    if not info['State']['Running'] or info['State'].get('Health', {}).get('Status', 'healthy') != 'healthy':
                        ready = False
            if ready:
                return
        except RuntimeError:
            pass
        time.sleep(5)
    raise RuntimeError('Swarm tasks did not converge; inspect docker service ps before retrying.')


def check(stack_path=None, recover_app=False):
    wait_ready(stack_path, recover_app=recover_app)
    info = json.loads(docker('inspect', container('caddy')))[0]
    env = dict(v.split('=', 1) for v in info['Config']['Env'] if '=' in v)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    checks = [(f'https://{env["DOMAIN"]}{p}', (200,)) for p in ['/', '/api/contact', '/auth/api/health', '/blog/', '/learn/']]
    checks += [(f'https://{env["DOMAIN"]}{p}', (302, 303, 401)) for p in ['/admin/', '/admin/notes/api/export', '/portainer/']]
    checks += [(f'https://{env["NTFY_DOMAIN"]}/v1/health', (200,))]
    if stack_path is None:
        stack_path = json.loads((PRIVATE / 'current.json').read_text(encoding='utf-8'))['file']
    checks_path = Path(stack_path).parent / 'checks.json'
    extra = json.loads(checks_path.read_text(encoding='utf-8')) if checks_path.exists() else {}
    # Older saved releases predate the catalog; retain their node-two gates.
    if not checks_path.exists() and 'node2' in release_stack(stack_path)['services']:
        extra = {'http': [{'url': 'https://{DOMAIN}/node2/', 'statuses': [302, 303, 401]}], 'internal': ['http://node2:80']}
    for item in extra.get('http', []):
        url = item['url'].replace('{DOMAIN}', env['DOMAIN']).replace('{NTFY_DOMAIN}', env['NTFY_DOMAIN'])
        checks.append((url, tuple(item['statuses'])))
    for url, expected in checks:
        request = urllib.request.Request(url, headers={'Remote-User': 'rithvik', 'Remote-Groups': 'admins'})
        try:
            with opener.open(request, timeout=20) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        if status not in expected:
            raise RuntimeError('HTTP validation failed for ' + url + ': ' + str(status))
    for url in extra.get('internal', []):
        docker('exec', container('caddy'), 'wget', '-q', '-T', '10', '-O', '-', url)
    docker('exec', container('caddy'), 'wget', '-q', '-T', '10', '-O', '-', 'http://portainer:9000/api/status')
    run(['python3', 'scripts/setup-ntfy.py', 'check'])
    print('All release services converged; configured HTTP checks, protected routes, Portainer and ntfy access checks passed.', flush=True)


def report_failure_state():
    """Best-effort, bounded snapshot; never emit environments or health output."""
    deadline = time.monotonic() + 30
    snapshot = {'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'services': [], 'local_containers': [], 'unavailable': [],
                'health_scope': 'Manager-local containers only; worker health is not inspected.'}

    def inspect(*args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Diagnostic time budget exhausted')
        return docker(*args, timeout=min(10, remaining))

    try:
        rows = [json.loads(line) for line in inspect('service', 'ls', '--filter',
                'label=com.docker.stack.namespace=portfolio', '--format', '{{json .}}').splitlines()]
        snapshot['services'] = [{key: row.get(key) for key in ('ID', 'Name', 'Mode', 'Replicas')} for row in rows]
        if rows:
            details = json.loads(inspect('service', 'inspect', *[row['ID'] for row in rows]))
            # service ls abbreviates IDs; service inspect returns full IDs.
            by_name = {item['Spec']['Name']: item for item in details}
            for row in snapshot['services']:
                update = by_name[row['Name']].get('UpdateStatus') or {}
                row['update'] = {key: update.get(key) for key in ('State', 'StartedAt', 'CompletedAt')}
                row['update']['State'] = update.get('State', 'not-started')
    except Exception:
        snapshot['unavailable'].append('service update states')

    try:
        ids = inspect('ps', '-aq', '--filter', 'label=com.docker.stack.namespace=portfolio').split()
        if ids:
            for item in json.loads(inspect('inspect', *ids)):
                state = item.get('State', {})
                health = state.get('Health', {})
                snapshot['local_containers'].append({
                    'id': item['Id'],
                    'service': item.get('Config', {}).get('Labels', {}).get('com.docker.swarm.service.name'),
                    'state': {key: state.get(key) for key in
                              ('Status', 'Running', 'OOMKilled', 'ExitCode', 'StartedAt', 'FinishedAt')},
                    'health': {'status': health.get('Status', 'not-configured'),
                               'failing_streak': health.get('FailingStreak', 0),
                               'recent_checks': [{key: entry.get(key) for key in ('Start', 'End', 'ExitCode')}
                                                 for entry in health.get('Log', [])[-5:]]}})
    except Exception:
        snapshot['unavailable'].append('manager-local container health')

    # Raw inspect results and free-form error/health text can contain credentials.
    try:
        write(PRIVATE / 'last-failed-state.json', snapshot)
    except Exception:
        print('Could not save failure-state snapshot; see the summary below.', flush=True)
    print('Swarm update and container health before rollback:\n' + json.dumps(snapshot, indent=2), flush=True)


def report_failed_tasks():
    # Diagnostics must never prevent restoration of the saved release.
    try:
        report_failure_state()
    except Exception:
        print('Could not capture failure state; continuing recovery.', flush=True)
    # Save the task error history before rollback replaces failed task entries.
    try:
        summaries = docker('stack', 'ps', 'portfolio', '--no-trunc', '--format',
                           '{{.Name}} | {{.Node}} | {{.CurrentState}} | {{.Error}}', timeout=10)
        path = PRIVATE / 'last-failed-tasks.txt'
        path.write_text(summaries + '\n', encoding='utf-8')
        path.chmod(0o600)
        print('Swarm task history before rollback:\n' + summaries, flush=True)
    except Exception:
        print('Could not capture task history; inspect docker stack ps portfolio.', flush=True)


def apply():
    candidate = json.loads((PRIVATE / 'candidate.json').read_text())
    old = json.loads((PRIVATE / 'current.json').read_text()) if (PRIVATE / 'current.json').exists() else None
    try:
        print('Applying Swarm release; persistent services update one at a time per service.', flush=True)
        docker('stack', 'deploy', '--prune', '--resolve-image', 'never', '-c', candidate['file'], 'portfolio')
        check(candidate['file'], recover_app=True)
        print(run(['python3', 'scripts/setup-portainer.py', '--configure', '--swarm']), flush=True)
        print(run(['python3', 'scripts/swarm-portainer.py']), flush=True)
    except Exception:
        report_failed_tasks()
        if old:
            print('Validation failed; restoring the last successful Swarm specification.', flush=True)
            docker('stack', 'deploy', '--prune', '--resolve-image', 'never', '-c', old['file'], 'portfolio')
            check(old['file'])
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
    try:
        docker('stack', 'deploy', '--prune', '--resolve-image', 'never', '-c', previous['file'], 'portfolio')
        check(previous['file'])
    except Exception:
        report_failed_tasks()
        docker('stack', 'deploy', '--prune', '--resolve-image', 'never', '-c', current['file'], 'portfolio')
        check(current['file'])
        raise
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
