#!/usr/bin/env python3
"""Stage/apply bounded per-user homes; run on Ampere only during controller maintenance.

Default is a read-only preflight. --apply stops only the isolated Rakazo services.
--rollback restores the old mount/config; retains new home data on the bounded cache.
Rollback also restores the pre-migration bridge code before restarting services.
Never deletes the original home data. Swarm services are not touched.
"""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess

BASE = Path('/var/lib/rakazo-pilot')
CACHE = BASE / 'engine/cache'
HOMES = BASE / 'workspaces/homes'
BOUNDED = CACHE / 'family-homes'
STATE = BASE / 'family-homes-migration.json'
UNITS = Path('/etc/systemd/system')
RUNTIME = Path('/opt/rakazo-runtime/pilot')
DROPIN = Path('/etc/systemd/system/user@986.service.d/rakazo-delegation.conf')
PREFIX = ['sudo', '-u', 'rakazo-pilot', 'env', 'XDG_RUNTIME_DIR=/run/user/986', 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/986/bus', 'HOME=' + str(BASE), 'systemctl', '--user']
SERVICES = ['rakazo-bridge', 'rakazo-controller', 'rakazo-engine']

def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()

def unit(path):
    return run('systemd-escape', '--path', '--suffix=mount', str(path))

def preflight():
    if os.geteuid() != 0 or run('docker', 'info', '--format', '{{.Swarm.NodeID}}') != 'tzqsl1t88r3l1i8zcqvcmredo':
        raise RuntimeError('Run as root on the approved Ampere worker')
    image = Path('/srv/swarm/.rakazo-runtime-cache.img')
    if not os.path.ismount(CACHE) or image.stat().st_size != 8 * 1024**3:
        raise RuntimeError('Dedicated 8 GiB cache must be mounted')
    # Resolve the mounted loop device to its backing file, not just a same-sized file.
    source = run('findmnt', '-n', '-o', 'SOURCE', '--target', str(CACHE))
    if Path(run('losetup', '-n', '-O', 'BACK-FILE', source)).resolve() != image.resolve():
        raise RuntimeError('Cache is not backed by the approved loop image')
    if HOMES.is_symlink() or BOUNDED.is_symlink():
        raise RuntimeError('Home roots must not be symlinks')

def update_dependencies(text):
    # Preserve unrelated Unit/Service settings and Delegate exactly as configured.
    lines = text.splitlines()
    section = None
    found = False
    for i, line in enumerate(lines):
        if line.startswith('['):
            section = line
        if section == '[Unit]' and line.startswith('RequiresMountsFor='):
            values = line.split('=', 1)[1].split()
            values = [v for v in values if v != str(HOMES / 'pilot-owner')]
            for value in [str(CACHE), str(HOMES)]:
                if value not in values:
                    values.append(value)
            lines[i] = 'RequiresMountsFor=' + ' '.join(values)
            found = True
    if not found:
        lines += ['[Unit]', f'RequiresMountsFor={CACHE} {HOMES}']
    return '\n'.join(lines) + '\n'


def assert_homes_mount():
    if not os.path.ismount(HOMES):
        raise RuntimeError('Homes mount missing')
    target, source = os.stat(HOMES), os.stat(BOUNDED)
    if (target.st_dev, target.st_ino) != (source.st_dev, source.st_ino):
        raise RuntimeError('Unexpected homes mount')


def restore(state):
    # A failed start may leave some services running. Stop before undoing mounts.
    run(*PREFIX, 'stop', *SERVICES)
    if os.path.ismount(HOMES):
        assert_homes_mount()
        run('umount', str(HOMES))
    for name, text in state['files'].items():
        path = Path(name)
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text)
    for name, saved in state.get('runtime', {}).items():
        path = Path(name)
        path.write_text(saved['text']); path.chmod(saved['mode'])
    run('systemctl', 'daemon-reload')
    if state['old_mounted'] and not os.path.ismount(HOMES / 'pilot-owner'):
        run('mount', '--bind', str(CACHE / 'pilot-home'), str(HOMES / 'pilot-owner'))
    if state['active']:
        run(*PREFIX, 'start', *reversed(state['active']))

def validate_reapply(state):
    # Never replace the original rollback snapshot with a snapshot of the newer bridge.
    if STATE.is_symlink() or STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o077:
        raise RuntimeError('Migration record must be private and root-owned')
    expected_files = {str(UNITS / unit(HOMES/'pilot-owner')), str(UNITS / unit(HOMES)), str(DROPIN)}
    expected_runtime = {str(RUNTIME/'bridge.mjs'), str(RUNTIME/'native-agent-bridge.mjs')}
    if set(state.get('files', {})) != expected_files or set(state.get('runtime', {})) != expected_runtime or state.get('old_mounted') is not True:
        raise RuntimeError('Incomplete or unexpected original rollback record')
    for name, text in state['files'].items():
        path = Path(name)
        if path.is_symlink() or (path.read_text() if path.exists() else None) != text:
            raise RuntimeError('Legacy service configuration differs from rollback record')
    for name, saved in state['runtime'].items():
        path = Path(name)
        if path.is_symlink() or path.read_text() != saved['text'] or path.stat().st_mode & 0o777 != saved['mode']:
            raise RuntimeError('Legacy bridge differs from rollback record')
    legacy = HOMES/'pilot-owner'
    original = CACHE/'pilot-home'
    if not os.path.ismount(legacy) or legacy.is_symlink():
        raise RuntimeError('Restore legacy pilot mount before reapplying')
    if (legacy.stat().st_dev, legacy.stat().st_ino) != (original.stat().st_dev, original.stat().st_ino):
        raise RuntimeError('Unexpected legacy home source')
    if not BOUNDED.is_dir() or BOUNDED.is_symlink():
        raise RuntimeError('Retained family homes missing or unsafe')
    root = BOUNDED.stat()
    if root.st_dev != CACHE.stat().st_dev or (root.st_uid, root.st_gid) != (986, 984) or root.st_mode & 0o022:
        raise RuntimeError('Retained home root has unsafe storage or ownership')
    for home in BOUNDED.iterdir():
        if home.is_symlink() or not home.is_dir() or not re.fullmatch(r'pilot-owner|chat-[a-f0-9]{64}', home.name):
            raise RuntimeError('Unexpected retained home')
        stat = home.stat()
        if stat.st_dev != root.st_dev or (stat.st_uid, stat.st_gid) != (2000999, 2000999) or stat.st_mode & 0o022:
            raise RuntimeError('Retained home ownership or permissions differ')
    if not (BOUNDED/'pilot-owner').is_dir():
        raise RuntimeError('Retained manual home missing')
    # A legacy session after rollback may have changed its home; never hide those edits.
    run('diff', '-qr', str(legacy), str(BOUNDED/'pilot-owner'))


def activate_retained_homes(state):
    old_unit = UNITS/unit(HOMES/'pilot-owner')
    new_unit = UNITS/unit(HOMES)
    run('umount', str(HOMES/'pilot-owner'))
    old_unit.unlink(missing_ok=True)
    new_unit.write_text(f'[Unit]\nRequiresMountsFor={CACHE}\n[Mount]\nWhat={BOUNDED}\nWhere={HOMES}\nType=none\nOptions=bind,nodev,nosuid\n')
    DROPIN.write_text(update_dependencies(state['files'][str(DROPIN)] or ''))
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start', new_unit.name)
    assert_homes_mount()
    if state['active']:
        run(*PREFIX, 'start', *reversed(state['active']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--rollback', action='store_true')
    mode.add_argument('--reapply', action='store_true', help='Reuse retained bounded homes after a completed rollback; keep original snapshot')
    args = parser.parse_args()
    preflight()
    if args.rollback:
        state = json.loads(STATE.read_text())
        run(*PREFIX, 'stop', *SERVICES)
        restore(state)
        print('Original mount restored; family-homes data retained in bounded cache.')
        return
    if os.path.ismount(HOMES):
        assert_homes_mount()
        print('All homes already use bounded storage.')
        return
    if args.reapply:
        state = json.loads(STATE.read_text())
        validate_reapply(state)
        try:
            run(*PREFIX, 'stop', *SERVICES)
            validate_reapply(state)
            activate_retained_homes(state)
        except BaseException:
            restore(state)
            raise
        print('Retained bounded homes reactivated; original rollback record and bridge snapshot unchanged. Install scoped controller before reopening API admission.')
        return
    if STATE.exists() or BOUNDED.exists():
        raise RuntimeError('Prior migration artifacts exist; inspect or roll back before retrying')
    size = int(run('du', '-s', '-B1', str(HOMES)).split()[0])
    if shutil.disk_usage(CACHE).free < size + 256 * 1024**2:
        raise RuntimeError('Insufficient bounded cache space to preserve and copy existing homes')
    print('Preflight passed: copy existing homes, preserve original data, bind all homes into 8 GiB cache.')
    if not args.apply:
        return
    old_unit = UNITS / unit(HOMES / 'pilot-owner')
    new_unit = UNITS / unit(HOMES)
    state = {'files': {str(p): p.read_text() if p.exists() else None for p in [old_unit, new_unit, DROPIN]},
             'runtime': {str(p): {'text': p.read_text(), 'mode': p.stat().st_mode & 0o777} for p in [RUNTIME/'bridge.mjs', RUNTIME/'native-agent-bridge.mjs'] if p.exists()},
             'old_mounted': os.path.ismount(HOMES / 'pilot-owner'),
             'active': [s for s in SERVICES if subprocess.run(PREFIX + ['is-active', '--quiet', s]).returncode == 0]}
    STATE.write_text(json.dumps(state, indent=2) + '\n'); STATE.chmod(0o600)
    try:
        run(*PREFIX, 'stop', *SERVICES)
        BOUNDED.mkdir(mode=0o700)
        run('cp', '-a', str(HOMES) + '/.', str(BOUNDED) + '/')
        os.chown(BOUNDED, 986, 984)
        # Compare content before hiding the old tree. Existing copies remain for rollback.
        run('diff', '-qr', str(HOMES), str(BOUNDED))
        if state['old_mounted']:
            run('umount', str(HOMES / 'pilot-owner'))
        old_unit.unlink(missing_ok=True)
        new_unit.write_text(f'[Unit]\nRequiresMountsFor={CACHE}\n[Mount]\nWhat={BOUNDED}\nWhere={HOMES}\nType=none\nOptions=bind,nodev,nosuid\n')
        DROPIN.write_text(update_dependencies(state['files'][str(DROPIN)] or ''))
        run('systemctl', 'daemon-reload')
        run('systemctl', 'start', new_unit.name)
        assert_homes_mount()
        if state['active']:
            run(*PREFIX, 'start', *reversed(state['active']))
    except BaseException:
        restore(state)
        raise
    print('All homes bounded; original pilot-home and migration record retained for rollback.')

if __name__ == '__main__':
    main()
