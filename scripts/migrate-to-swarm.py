#!/usr/bin/env python3
"""One-time Compose-to-Swarm cutover with a consistent snapshot and automatic fallback."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import signal
import time

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('swarm', ROOT / 'scripts/swarm-deploy.py')
swarm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swarm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True, type=Path)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise RuntimeError('Cutover interrupted; restoring Compose.')
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, interrupted)
    os.umask(0o077)
    os.chdir(ROOT)
    backup = args.backup.resolve()
    parent = Path('/home/opc/.config/portfolio-deploy').resolve()
    if backup.parent != parent or not backup.name.startswith('pre-swarm-') or not (backup / 'source-before.tar.gz').is_file():
        raise RuntimeError('Use the prepared private pre-migration backup directory.')
    if (ROOT / '.swarm/enabled').exists():
        raise RuntimeError('Swarm is already enabled; use the normal deployment command.')
    if not (ROOT / '.swarm/candidate.json').exists():
        raise RuntimeError('Prepare and validate the Swarm release first.')
    lock = open(ROOT / '.git/portfolio-deploy.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ids = swarm.docker('ps', '-q', '--filter', 'label=com.docker.compose.project=portfolio').split()
    containers = json.loads(swarm.docker('inspect', *ids))
    if len(containers) != 5 or any(not c['State']['Running'] for c in containers):
        raise RuntimeError('Expected all five original services to be running.')
    originals = {c['Config']['Labels']['com.docker.compose.service']: c for c in containers}
    tags = {name: json.loads(swarm.docker('image', 'inspect', 'rithvik-portfolio:' + name))[0]['Id'] for name in ['production', 'current', 'previous']}
    (backup / 'original-image-tags.json').write_text(json.dumps(tags))
    (backup / 'compose-containers.json').write_text(json.dumps(containers))
    os.environ['PORTFOLIO_DEPLOY_LOCK_HELD'] = '1'
    stopping = False
    try:
        print('Stopping the five Compose writers for the migration snapshot.', flush=True)
        stopping = True
        swarm.docker('update', '--restart=no', *ids)
        swarm.docker('stop', *ids, timeout=150)
        def archive(name, base, paths):
            swarm.run(['sudo', '-n', 'tar', '--acls', '--xattrs', '--selinux', '--numeric-owner', '-czf', str(backup / name), '-C', str(base), '--', *paths], timeout=180)
            swarm.run(['sudo', '-n', 'chown', str(os.getuid()) + ':' + str(os.getgid()), str(backup / name)])
            (backup / name).chmod(0o600)
        archive('private-state.tar.gz', ROOT, ['.env.production', '.auth', '.portainer', '.notes', '.ntfy', '.swarm'])
        for name in ['portfolio_caddy_data', 'portfolio_caddy_config']:
            mount = json.loads(swarm.docker('volume', 'inspect', name))[0]['Mountpoint']
            archive(name + '.tar.gz', mount, ['.'])
        print('Consistent private-data and certificate snapshot saved. Starting Swarm services.', flush=True)
        subprocess.run(['python3', 'scripts/swarm-deploy.py', 'apply'], check=True, timeout=600)
        (backup / 'MIGRATION-SUCCESS.txt').write_text('Swarm passed its convergence and HTTP gates. Original Compose containers remain stopped with restart disabled.\n')
        print('Migration passed. Original Compose containers remain stopped for recovery.', flush=True)
    except BaseException:
        if stopping:
            print('Migration failed. Removing new Swarm tasks before restarting Compose.', flush=True)
            swarm.docker('stack', 'rm', 'portfolio')
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                tasks = swarm.docker('ps', '-q', '--filter', 'label=com.docker.stack.namespace=portfolio').split()
                if not tasks:
                    break
                time.sleep(3)
            else:
                raise RuntimeError('New Swarm tasks still running; refusing simultaneous database writers.')
            for name, identifier in tags.items():
                swarm.docker('image', 'tag', identifier, 'rithvik-portfolio:' + name)
            (ROOT / '.swarm/enabled').unlink(missing_ok=True)
            swarm.docker('update', '--restart=unless-stopped', *ids)
            swarm.docker('start', *ids, timeout=180)
            print('Original Compose containers restarted. Keep the snapshot and inspect the failure before retrying.', flush=True)
        raise


if __name__ == '__main__':
    main()
