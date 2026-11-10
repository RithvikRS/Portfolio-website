#!/usr/bin/env python3
"""Prepare the owner-only workspace app. Keep private input and recovery files out of Git."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

NODE = 'tzqsl1t88r3l1i8zcqvcmredo'
POSTGRES = 'postgres:18-alpine@sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395'
PRIVATE = Path('/opt/portfolio/.secrets/rakazo')
API_DATA = Path('/srv/swarm/rakazo_api')
DB_DATA = Path('/srv/swarm/rakazo_db')


def docker(*args, data=None):
    result = subprocess.run(['sudo', '-n', 'docker', *args], input=data, text=True, capture_output=True, timeout=900)
    if result.returncode:
        raise RuntimeError('Docker operation failed: ' + args[0] + '; inspect the private bootstrap logs on this host.')
    return result.stdout.strip()


def install(path, value):
    if path.exists():
        if path.read_text() != value:
            raise RuntimeError('Existing private recovery set differs; restore it rather than generating new keys.')
        return
    with path.open('x') as f:
        f.write(value)
    path.chmod(0o600)


def manager():
    helper_spec = importlib.util.spec_from_file_location('family', Path(__file__).with_name('setup-family-services.py'))
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    recovery = PRIVATE / 'recovery.json'
    if not recovery.exists():
        if any(PRIVATE.iterdir()) or (helper.AUTH / 'rakazo-client-hash').exists():
            raise RuntimeError('Restore the existing Rakazo private recovery set first.')
        users = json.loads((helper.AUTH / 'directory/users.yml').read_text())['users']
        owner = users['rithvik']
        if 'admins' not in owner['groups'] or not re.fullmatch(r'[^\s@]+@[^\s@]+', owner['email']):
            raise RuntimeError('Expected the existing administrator identity and verified email.')
        tasks = docker('ps', '-q', '--filter', 'label=com.docker.swarm.service.name=portfolio_auth').split()
        if len(tasks) != 1:
            raise RuntimeError('Expected one local Authelia task.')
        keys = {name: secrets.token_hex(32) for name in ['database_owner_password', 'database_app_password', 'encryption_key', 'auth_secret', 'screen_secret']}
        keys['oidc'] = helper.new_client(tasks[0])
        keys['owner_email'] = owner['email'].strip().lower()
        install(recovery, json.dumps(keys) + '\n')
    keys = json.loads(recovery.read_text())
    install(helper.AUTH / 'rakazo-client-hash', keys['oidc']['digest'] + '\n')
    values = {name: keys[name] for name in ['database_owner_password', 'encryption_key', 'auth_secret', 'screen_secret', 'owner_email']}
    values['oidc_secret'] = keys['oidc']['password']
    values['database_url'] = 'postgres://rakazo_app:' + keys['database_app_password'] + '@rakazo_db:5432/rakazo'
    for name, value in values.items():
        install(PRIVATE / name, value)
    print('Private Rakazo credentials and owner allowlist ready; no values printed.')


def worker(image):
    if not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', image):
        raise RuntimeError('Supply the reviewed workspace-only application image by immutable registry digest.')
    if docker('info', '--format', '{{.Swarm.NodeID}}') != NODE or not os.path.ismount('/srv/swarm'):
        raise RuntimeError('Run on the approved Ampere worker with its storage mounted.')
    if Path('/srv/swarm/.storage-node-id').read_text().strip() != NODE:
        raise RuntimeError('Worker storage marker differs.')
    for name in ['rakazo_api', 'rakazo_db']:
        if docker('ps', '-q', '--filter', 'label=com.docker.swarm.service.name=portfolio_' + name):
            raise RuntimeError('Bootstrap only before the production application is running.')
    keys = json.load(sys.stdin)
    for name in ['database_owner_password', 'database_app_password']:
        if not re.fullmatch(r'[0-9a-f]{64}', keys[name]):
            raise RuntimeError('Invalid private database recovery input.')
    for path, owner in [(API_DATA, '1000'), (DB_DATA, '70')]:
        subprocess.run(['sudo', '-n', 'install', '-d', '-m', '700', '-o', owner, '-g', owner, str(path)], check=True)
        subprocess.run(['sudo', '-n', 'restorecon', '-R', str(path)], check=True)
    marker = API_DATA / '.workspace-bootstrap.json'
    if marker.exists():
        if json.loads(marker.read_text())['image'] != image:
            raise RuntimeError('Existing schema needs a separately reviewed migration before updating the image.')
        print('Existing workspace schema preserved.')
        return
    docker('pull', POSTGRES)
    docker('pull', image)
    network = 'rakazo-workspace-bootstrap'
    db_name = 'rakazo-workspace-bootstrap-db'
    migrate_name = 'rakazo-workspace-bootstrap-migrate'
    env = API_DATA / '.bootstrap-migration.env'
    password = API_DATA / '.bootstrap-db-password'
    install(password, keys['database_owner_password'])
    # PostgreSQL runs as UID 70; this single temporary password file is readable by that UID.
    subprocess.run(['sudo', '-n', 'chown', '70:70', str(password)], check=True)
    install(env, 'DATABASE_URL=postgres://rakazo_app:' + keys['database_app_password'] + '@rakazo_db:5432/rakazo\nDATABASE_MIGRATION_URL=postgres://rakazo:' + keys['database_owner_password'] + '@rakazo_db:5432/rakazo\n')
    made_network = started_db = started_migrate = False
    try:
        docker('network', 'create', '--internal', network)
        made_network = True
        docker('run', '-d', '--name', db_name, '--network', network, '--network-alias', 'rakazo_db',
               '--user', '70:70', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '512m', '--cpus', '0.75',
               '--mount', 'type=bind,src=' + str(DB_DATA) + ',dst=/var/lib/postgresql',
               '--mount', 'type=bind,src=' + str(password) + ',dst=/run/secrets/password,readonly',
               '--tmpfs', '/var/run/postgresql:rw,nosuid,nodev,size=16777216,mode=1777',
               '-e', 'POSTGRES_USER=rakazo', '-e', 'POSTGRES_DB=rakazo', '-e', 'POSTGRES_PASSWORD_FILE=/run/secrets/password', POSTGRES)
        started_db = True
        for _ in range(60):
            r = subprocess.run(['sudo', '-n', 'docker', 'exec', db_name, 'pg_isready', '-U', 'rakazo', '-d', 'rakazo'], capture_output=True)
            if r.returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError('Bootstrap database did not become ready.')
        docker('create', '--name', migrate_name, '--network', network, '--user', '1000:1000', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--memory', '1536m', '--cpus', '1.5', '--pids-limit', '256',
               '--env-file', str(env), '--workdir', '/app/apps/api', image, 'node', '--enable-source-maps', 'dist/cli/migrate-database.js')
        started_migrate = True
        docker('start', migrate_name)
        code = docker('wait', migrate_name)
        if code != '0':
            raise RuntimeError('Rakazo migrations failed; preserve private database and inspect migration container locally.')
        # Only names and capability booleans leave the database; never credentials.
        role = docker('exec', db_name, 'psql', '-U', 'rakazo', '-d', 'rakazo', '-tAc',
                      "SELECT rolname || ':' || rolsuper || ':' || rolbypassrls FROM pg_roles WHERE rolname='rakazo_app'")
        if role != 'rakazo_app:false:false':
            raise RuntimeError('Runtime role must exist without superuser or row-security bypass.')
        install(marker, json.dumps({'image': image, 'runtime_role_verified': True}) + '\n')
        print('Workspace schema initialized; runtime role cannot bypass row-level security.')
    finally:
        if started_migrate:
            # Persist diagnostics privately before removing the temporary process.
            result = subprocess.run(['sudo', '-n', 'docker', 'logs', migrate_name], capture_output=True)
            (API_DATA / '.bootstrap-migration.log').write_bytes(result.stdout + result.stderr)
            (API_DATA / '.bootstrap-migration.log').chmod(0o600)
            docker('rm', '-f', migrate_name)
        if started_db:
            docker('stop', '--time', '45', db_name)
            docker('rm', db_name)
        if made_network:
            docker('network', 'rm', network)
        env.unlink(missing_ok=True)
        subprocess.run(['sudo', '-n', 'rm', '-f', '--', str(password)], check=True)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=['manager', 'worker'])
    parser.add_argument('--image')
    args = parser.parse_args()
    manager() if args.role == 'manager' else worker(args.image or '')
