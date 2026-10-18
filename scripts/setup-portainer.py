#!/usr/bin/env python3
"""Prepare private keys, then reconcile Portainer through its unpublished API.

Run as the server checkout owner. --prepare is safe before starting containers;
--configure requires a running Portainer. Neither mode prints credentials.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        # Commands can return credentials or resolved private configuration.
        raise RuntimeError('A Docker or key-generation command failed; no private output was printed.')
    return result.stdout.strip()


def write_new(path, text):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(text)
    path.chmod(0o600)


def prepare(config, docker):
    private = ROOT / '.portainer'
    auth = ROOT / '.auth/secrets'
    if not (auth / 'users.yml').is_file():
        raise RuntimeError('Run python3 scripts/setup-admin.py first.')
    service = config['services']['auth']
    if service['user'] != f'{os.getuid()}:{os.getgid()}':
        raise RuntimeError('Run as the .auth owner matching AUTHELIA_UID and AUTHELIA_GID.')
    private.mkdir(mode=0o700, exist_ok=True)
    private.chmod(0o700)
    recovery = private / 'recovery-password'
    credentials = private / 'oauth-client.json'
    if (private / 'data/portainer.db').exists() and (not recovery.exists() or not credentials.exists()):
        raise RuntimeError('Existing Portainer data has missing credentials. Restore its private backup; do not reinitialize.')
    if not recovery.exists():
        write_new(recovery, secrets.token_urlsafe(36) + '\n')
    if not credentials.exists():
        result = run(docker + ['run', '--rm', '--network', 'none', service['image'],
            'authelia', 'crypto', 'hash', 'generate', 'pbkdf2', '--variant', 'sha512',
            '--iterations', '310000', '--random', '--random.length', '64'])
        password = re.search(r'^Random Password: (.+)$', result, re.MULTILINE)
        digest = re.search(r'^Digest: (\$pbkdf2-sha512\$.+)$', result, re.MULTILINE)
        if not password or not digest:
            raise RuntimeError('Could not generate the OAuth client credentials.')
        write_new(credentials, json.dumps({'secret': password.group(1), 'hash': digest.group(1)}) + '\n')
    client = json.loads(credentials.read_text())
    client_hash = auth / 'portainer-client-hash'
    if not client_hash.exists():
        write_new(client_hash, client['hash'] + '\n')
    elif client_hash.read_text().strip() != client['hash']:
        raise RuntimeError('OAuth credential files disagree. Restore matching files from backup.')
    if not (auth / 'oidc-hmac').exists():
        write_new(auth / 'oidc-hmac', secrets.token_hex(32) + '\n')
    if not (auth / 'oidc-private.pem').exists():
        # Generate in memory, then create the protected file exclusively.
        key = run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048'])
        write_new(auth / 'oidc-private.pem', key + '\n')
    (private / 'data').mkdir(mode=0o700, exist_ok=True)
    print('Portainer private files are ready; existing passwords and keys were preserved.')


class API:
    def __init__(self, address, origin):
        self.base = f'http://{address}:9000/api'
        self.origin = origin
        self.token = None
        self.opener = build_opener(ProxyHandler({}))

    def call(self, method, path, payload=None, multipart=False):
        headers = {'Origin': self.origin}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        data = None
        if multipart:
            boundary = 'portfolio-' + secrets.token_hex(16)
            data = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
                           for key, value in payload.items()) + f'--{boundary}--\r\n'
            data = data.encode()
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        elif payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        request = Request(self.base + path, data=data, headers=headers, method=method)
        with self.opener.open(request, timeout=15) as response:
            body = response.read()
            return json.loads(body) if body else None


def configure(config, docker, compose):
    service = config['services']['app']
    username = service['environment']['ADMIN_USERNAME']
    if username == 'admin':
        raise RuntimeError('ADMIN_USERNAME must differ from the Portainer recovery account admin.')
    users = json.loads((ROOT / '.auth/secrets/users.yml').read_text())['users']
    if username not in users or 'admins' not in users[username]['groups']:
        raise RuntimeError('ADMIN_USERNAME must already exist in the Authelia admins group.')
    container = run(compose + ['ps', '-q', 'portainer'])
    if not container:
        raise RuntimeError('Start Portainer before running --configure.')
    inspected = json.loads(run(docker + ['inspect', container]))[0]
    networks = inspected['NetworkSettings']['Networks']
    address = next(value['IPAddress'] for name, value in networks.items() if name.endswith('_management'))
    if not ipaddress.ip_address(address).is_private:
        raise RuntimeError('Refusing to send credentials outside the private Docker network.')
    origin = 'https://' + config['services']['auth']['environment']['DOMAIN']
    api = API(address, origin)
    for attempt in range(60):
        try:
            api.call('GET', '/status')
            break
        except (URLError, TimeoutError):
            if attempt == 59:
                raise RuntimeError('Portainer did not become ready within two minutes.') from None
            time.sleep(2)
    private = ROOT / '.portainer'
    api.token = api.call('POST', '/auth', {'Username': 'admin',
        'Password': (private / 'recovery-password').read_text().strip()})['jwt']
    try:
        client = json.loads((private / 'oauth-client.json').read_text())
        oauth = {
            'ClientID': 'portfolio-portainer', 'ClientSecret': client['secret'],
            'AuthorizationURI': origin + '/auth/api/oidc/authorization',
            'AccessTokenURI': origin + '/auth/api/oidc/token',
            'ResourceURI': origin + '/auth/api/oidc/userinfo',
            'RedirectURI': origin + '/portainer/', 'UserIdentifier': 'preferred_username',
            'Scopes': 'openid profile groups email', 'OAuthAutoCreateUsers': False,
            'DefaultTeamID': 0, 'SSO': True, 'LogoutURI': origin + '/auth/logout', 'AuthStyle': 1,
        }
        settings = api.call('GET', '/settings')
        wanted = {'AuthenticationMethod': 3, 'OAuthSettings': oauth,
                  'UserSessionTimeout': '8h', 'ForceSecureCookies': True}
        different = any(settings.get(key) != value for key, value in wanted.items() if key != 'OAuthSettings')
        # Portainer omits the stored client secret from GET responses.
        different |= any(settings.get('OAuthSettings', {}).get(key) != value
                         for key, value in oauth.items() if key != 'ClientSecret')
        if different:
            api.call('PUT', '/settings', wanted)
        accounts = api.call('GET', '/users')
        account = next((user for user in accounts if user['Username'] == username), None)
        if account is None:
            account = api.call('POST', '/users', {'Username': username, 'Password': '', 'Role': 1})
        if account['Role'] != 1 or account['Id'] == 1:
            raise RuntimeError('Existing SSO account has an unexpected role or ID; review it manually.')
        endpoints = api.call('GET', '/endpoints')
        local = next((item for item in endpoints if item['URL'] == 'unix:///var/run/docker.sock'), None)
        if local is None:
            local = api.call('POST', '/endpoints', {'Name': 'Oracle Docker', 'EndpointCreationType': 1,
                'URL': 'unix:///var/run/docker.sock', 'ContainerEngine': 'docker'}, multipart=True)
        containers = api.call('GET', f'/endpoints/{local["Id"]}/docker/containers/json')
        if not isinstance(containers, list):
            raise RuntimeError('Could not read the Oracle Docker environment.')
        print(f'Portainer SSO configured for {username}; Oracle Docker is connected ({len(containers)} running containers).')
    finally:
        api.call('POST', '/auth/logout')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--configure', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.umask(0o077)
    docker = ['docker']
    if subprocess.run(docker + ['info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        docker = ['sudo', '-n', 'docker']
    compose = docker + ['compose', '--env-file', '.env.production', '-f', 'compose.production.yaml']
    config = json.loads(run(compose + ['config', '--format', 'json']))
    if args.prepare:
        prepare(config, docker)
    else:
        configure(config, docker, compose)


if __name__ == '__main__':
    try:
        main()
    except HTTPError as error:
        sys.exit(f'Portainer API returned HTTP {error.code}. Private response details were not printed.')
    except (RuntimeError, OSError, ValueError, KeyError, StopIteration) as error:
        sys.exit(f'Portainer setup stopped: {error}')
