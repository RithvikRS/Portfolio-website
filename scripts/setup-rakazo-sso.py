#!/usr/bin/env python3
"""Create the separate Rakazo edge recovery set on the manager; never rotate existing keys."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess

PRIVATE = Path('/opt/portfolio/.secrets/rakazo-edge')
AUTH = Path('/opt/portfolio/.auth/secrets')

def main():
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location('family', Path(__file__).with_name('setup-family-services.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    users = json.loads((AUTH / 'directory/users.yml').read_text())['users']
    owner = users['rithvik']
    expected = Path('/opt/portfolio/.secrets/rakazo/owner_email').read_text().strip()
    if owner.get('disabled') or 'admins' not in owner['groups'] or owner['email'].casefold() != expected.casefold():
        raise RuntimeError('Restore the matching enabled owner identity first.')
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    recovery = PRIVATE / 'recovery.json'
    digest = AUTH / 'rakazo-edge-client-hash'
    if not recovery.exists():
        if any(PRIVATE.iterdir()) or digest.exists():
            raise RuntimeError('Restore the existing edge recovery set first.')
        tasks = subprocess.check_output(['sudo', '-n', 'docker', 'ps', '-q', '--filter', 'label=com.docker.swarm.service.name=portfolio_auth'], text=True).split()
        if len(tasks) != 1:
            raise RuntimeError('Expected one local Authelia task.')
        keys = helper.new_client(tasks[0])
        keys['cookie'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        helper.install(recovery, json.dumps(keys) + '\n')
    keys = json.loads(recovery.read_text())
    helper.install(digest, keys['digest'] + '\n')
    helper.install(PRIVATE / 'edge.cfg', 'client_secret = ' + json.dumps(keys['password']) + '\ncookie_secret = ' + json.dumps(keys['cookie']) + '\n')
    for path in [recovery, digest, PRIVATE / 'edge.cfg']:
        path.chmod(0o600)
    print('Private Rakazo edge credentials ready; no values printed.')

if __name__ == '__main__':
    main()
