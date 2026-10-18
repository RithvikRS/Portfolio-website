#!/usr/bin/env python3
"""Prepare private ntfy credentials, configure topic access, and check HTTPS."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / '.ntfy'
TOPIC = 'arm-provisioning'


def run(command, data=None):
    result = subprocess.run(command, input=data, text=True, capture_output=True, cwd=ROOT)
    if result.returncode:
        raise RuntimeError('An ntfy setup command failed; private command output was withheld.')
    return result.stdout


def prepare(config):
    service = config['services']['ntfy']
    if service['user'] != f'{os.getuid()}:{os.getgid()}':
        raise RuntimeError('Run as the checkout owner matching NTFY_UID and NTFY_GID.')
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    PRIVATE.chmod(0o700)
    data = PRIVATE / 'data'
    data.mkdir(mode=0o700, exist_ok=True)
    data.chmod(0o700)
    for name, username in [('iphone', 'iphone'), ('publisher', 'arm-publisher')]:
        path = PRIVATE / (name + '.json')
        if not path.exists():
            if (data / 'auth.db').exists():
                raise RuntimeError('Existing ntfy data has missing credentials. Restore its private backup.')
            with path.open('x') as stream:
                json.dump({'username': username, 'password': secrets.token_urlsafe(24), 'topic': TOPIC}, stream)
                stream.write('\n')
        path.chmod(0o600)
    phone = json.loads((PRIVATE / 'iphone.json').read_text())
    url = service['environment']['NTFY_BASE_URL']
    path = PRIVATE / 'iphone.txt'
    path.write_text(f'Server: {url}\nTopic: {TOPIC}\nUsername: {phone["username"]}\nPassword: {phone["password"]}\n')
    path.chmod(0o600)
    print('ntfy private files are ready. Read .ntfy/iphone.txt over SSH for the iPhone login.')


def configure(compose):
    for name, permission in [('iphone', 'ro'), ('publisher', 'wo')]:
        user = json.loads((PRIVATE / (name + '.json')).read_text())
        # Pass the password over stdin; keep it out of argv and container metadata.
        run(compose + ['run', '--rm', '--no-deps', '-T', '--entrypoint', 'sh', 'ntfy', '-c',
            'IFS= read -r NTFY_PASSWORD; export NTFY_PASSWORD; exec ntfy user add --ignore-exists "$1"',
            'sh', user['username']], user['password'] + '\n')
        run(compose + ['run', '--rm', '--no-deps', '-T', 'ntfy', 'access', user['username'], TOPIC, permission])
    print('ntfy permissions: iPhone can read, ARM publisher can write, anonymous clients have no topic access.')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def status(base, path, user=None, write=False):
    headers = {}
    if user:
        token = base64.b64encode((user['username'] + ':' + user['password']).encode()).decode()
        headers['Authorization'] = 'Basic ' + token
    request = Request(base + path, headers=headers, data=b'Access control check' if write else None)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            return response.status
    except HTTPError as error:
        return error.code


def check(config):
    base = config['services']['ntfy']['environment']['NTFY_BASE_URL']
    phone = json.loads((PRIVATE / 'iphone.json').read_text())
    publisher = json.loads((PRIVATE / 'publisher.json').read_text())
    checks = [
        ('health', '/v1/health', None, False, (200,)),
        ('anonymous read', '/' + TOPIC + '/json?poll=1', None, False, (401, 403)),
        ('anonymous publish', '/' + TOPIC, None, True, (401, 403)),
        ('iPhone read', '/' + TOPIC + '/json?poll=1', phone, False, (200,)),
        ('iPhone publish', '/' + TOPIC, phone, True, (403,)),
        ('publisher read', '/' + TOPIC + '/json?poll=1', publisher, False, (403,)),
        ('iPhone other topic', '/unassigned-topic/json?poll=1', phone, False, (403,)),
        ('publisher other topic', '/unassigned-topic', publisher, True, (403,)),
    ]
    for name, path, user, write, allowed in checks:
        actual = status(base, path, user, write)
        if actual not in allowed:
            raise RuntimeError(f'ntfy {name} returned HTTP {actual}; expected {allowed}.')
        print(f'ntfy {name}: HTTP {actual}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'configure', 'check'])
    args = parser.parse_args()
    os.umask(0o077)
    docker = ['docker']
    if subprocess.run(docker + ['info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        docker = ['sudo', '-n', 'docker']
    compose = docker + ['compose', '--env-file', '.env.production', '-f', 'compose.production.yaml']
    config = json.loads(run(compose + ['config', '--format', 'json']))
    if args.mode == 'prepare':
        prepare(config)
    elif args.mode == 'configure':
        configure(compose)
    else:
        check(config)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else 'ntfy setup failed; check the private files and container state.', file=sys.stderr)
        sys.exit(1)
