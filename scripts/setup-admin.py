#!/usr/bin/env python3
"""One-time Oracle setup. Keeps passwords and identity keys out of Git and logs."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
os.umask(0o077)
private = ROOT / '.auth'
if private.exists():
    sys.exit('.auth already exists; preserving the current account and encryption keys.')

docker = ['docker']
if subprocess.run(docker + ['info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
    docker = ['sudo', '-n', 'docker']
compose = docker + ['compose', '--env-file', '.env.production', '-f', 'compose.production.yaml']
# Capture configuration in memory: it also contains private SMTP values.
result = subprocess.run(compose + ['config', '--format', 'json'], capture_output=True, text=True)
if result.returncode:
    sys.exit('Compose configuration is invalid. Run compose config --quiet to diagnose it.')
config = json.loads(result.stdout)
service = config['services']['auth']
identity_owner = service['user']
if identity_owner != f'{os.getuid()}:{os.getgid()}':
    sys.exit('Set AUTHELIA_UID and AUTHELIA_GID in .env.production to your id -u and id -g, then rerun as that user.')
domain = service['environment']['DOMAIN']
username = config['services']['app']['environment']['ADMIN_USERNAME']
if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', username):
    sys.exit('ADMIN_USERNAME must contain only letters, digits, underscores, or hyphens.')

result = subprocess.run(docker + ['run', '--rm', '--network', 'none', service['image'],
    'authelia', 'crypto', 'hash', 'generate', 'argon2', '--random', '--random.length', '32',
    '--parallelism', '1'], capture_output=True, text=True)
password = re.search(r'^Random Password: (.+)$', result.stdout, re.MULTILINE)
digest = re.search(r'^Digest: (\$argon2id\$.+)$', result.stdout, re.MULTILINE)
if result.returncode or not password or not digest:
    sys.exit('Password generation failed. No account files were written.')

private.mkdir(mode=0o700)
(private / 'secrets').mkdir(mode=0o700)
(private / 'data').mkdir(mode=0o700)
for filename in ['session-secret', 'storage-key']:
    (private / 'secrets' / filename).write_text(secrets.token_hex(32) + '\n', encoding='utf-8')
users = {'users': {username: {'displayname': 'Rithvik', 'password': digest.group(1),
    'email': 'rithvik.career@gmail.com', 'groups': ['admins']}}}
# JSON is a subset of YAML, avoiding an extra Python package for this setup script.
(private / 'secrets' / 'users.yml').write_text(json.dumps(users, indent=2) + '\n', encoding='utf-8')
(private / 'bootstrap-login.txt').write_text(
    f'Portfolio admin dashboard\n\nURL: https://{domain}/admin/\nUsername: {username}\n'
    f'Password: {password.group(1)}\n\nSave this in your password manager. Do not commit or share this file.\n',
    encoding='utf-8')
print('Created the private account, keys, and data directory.')
print('Login details: .auth/bootstrap-login.txt (readable only by your server user).')
print('Back up the complete .auth directory securely before changing or moving it.')
