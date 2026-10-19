#!/usr/bin/env python3
"""Retain successful portfolio images before pruning; never remove runtime data."""
import argparse
from collections import namedtuple
import json
import re
import subprocess
import sys

PRODUCTION = 'rithvik-portfolio:production'
CURRENT = 'rithvik-portfolio:current'
PREVIOUS = 'rithvik-portfolio:previous'
APP_LABEL = 'io.github.rithvikrs.portfolio.app=true'
DiskUsage = namedtuple('DiskUsage', 'total used available')
AppImage = namedtuple('AppImage', 'id manifest')


class Docker:
    def __init__(self, sudo=False):
        self.command = ['sudo', '-n', 'docker'] if sudo else ['docker']

    def run(self, *args, capture=False):
        result = subprocess.run(
            self.command + list(args), check=True, text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout.strip() if capture else None

    def disk_usage(self, path):
        # Read filesystem allocation in bytes, not the sum of shared image sizes.
        # Reuse sudo when Docker's data directory is inaccessible to the SSH user.
        result = subprocess.run(
            self.command[:-1] + ['df', '--block-size=1', '--output=size,used,avail', '--', path],
            check=True, text=True, stdout=subprocess.PIPE,
        )
        lines = result.stdout.strip().splitlines()
        values = lines[-1].split() if lines else []
        if len(values) != 3:
            raise ValueError('Unexpected filesystem usage output.')
        usage = DiskUsage(*(int(value) for value in values))
        if usage.total <= 0 or min(usage.used, usage.available) < 0:
            raise ValueError('Invalid filesystem usage values.')
        return usage


def image_id(docker, reference):
    images = docker.run('image', 'ls', '--quiet', '--no-trunc', reference, capture=True).splitlines()
    if len(images) > 1:
        raise RuntimeError('Expected one image for ' + reference)
    return images[0] if images else None


def healthy_app_image(docker, required=True):
    containers = docker.run(
        'ps', '--all', '--quiet',
        '--filter', 'label=com.docker.compose.project=portfolio',
        '--filter', 'label=com.docker.compose.service=app',
        '--filter', 'label=com.docker.compose.oneoff=False', capture=True,
    ).splitlines()
    if not containers and not required:
        return None
    if len(containers) != 1:
        raise RuntimeError('Expected exactly one portfolio app container.')
    state, descriptor = docker.run(
        'container', 'inspect', '--format',
        '{{.Image}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}|{{json .ImageManifestDescriptor}}',
        containers[0], capture=True,
    ).split('|', 1)
    state = state.split()
    if len(state) != 3 or state[1:] != ['true', 'healthy']:
        raise RuntimeError('The portfolio app must be running and healthy before retaining its image.')
    return AppImage(state[0], json.loads(descriptor))


def matches_runtime(docker, running, reference):
    if not reference:
        return False
    if running.id == reference:
        return True
    # Build attestations can change the index ID without changing the executable
    # manifest. Use Docker's actual container descriptor, never a revision label
    # or layer list: the manifest also identifies the complete image config.
    manifest = running.manifest
    if not isinstance(manifest, dict) or manifest.get('mediaType') not in (
        'application/vnd.oci.image.manifest.v1+json',
        'application/vnd.docker.distribution.manifest.v2+json',
    ):
        raise RuntimeError('Cannot establish the running image manifest; skipping cleanup.')
    digest = manifest.get('digest', '')
    platform = manifest.get('platform')
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest) or not isinstance(platform, dict):
        raise RuntimeError('Invalid running image manifest metadata; skipping cleanup.')
    parts = [platform.get('os'), platform.get('architecture')]
    if platform.get('variant'):
        parts.append(platform['variant'])
    if any(not isinstance(part, str) or not re.fullmatch(r'[a-z0-9_.-]+', part) for part in parts):
        raise RuntimeError('Cannot establish the running image platform; skipping cleanup.')
    candidate = docker.run(
        'image', 'inspect', '--platform', '/'.join(parts), '--format', '{{.Id}}', reference, capture=True,
    )
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', candidate):
        raise RuntimeError('Cannot establish the candidate image manifest; skipping cleanup.')
    return candidate == digest


def prepare(docker):
    # production is a mutable build tag; it may already point at a failed build.
    # Bootstrap from the actual healthy container, then keep this tag on failures.
    if image_id(docker, CURRENT):
        return
    running = healthy_app_image(docker, required=False)
    if running:
        docker.run('image', 'tag', running.id, CURRENT)
        print('Retained the running app as ' + CURRENT)


def warn_cleanup(action, callback):
    try:
        return callback()
    except (subprocess.CalledProcessError, OSError, RuntimeError, ValueError) as error:
        print('WARNING: Deployment is healthy, but ' + action + ' failed: ' + str(error), file=sys.stderr, flush=True)


def format_bytes(value):
    amount = value
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if amount < 1024 or unit == 'TiB':
            return f'{amount:,.2f} {unit} ({value:,} bytes)'
        amount /= 1024


def measure_cleanup_disk(docker, path, phase):
    if not path:
        return None

    def measure():
        usage = docker.disk_usage(path)
        print(f'Cleanup disk usage {phase} ({path} filesystem):', flush=True)
        print(f'  Used: {format_bytes(usage.used)}; available: {format_bytes(usage.available)}; '
              f'total: {format_bytes(usage.total)}', flush=True)
        return usage

    return warn_cleanup(phase + '-cleanup disk measurement', measure)


def report_cleanup_disk_change(before, after):
    if before is None or after is None:
        print('Cleanup disk summary unavailable: could not read both filesystem measurements.', flush=True)
        return
    if before.total != after.total:
        print('Cleanup disk summary unavailable: filesystem capacity changed between measurements.', flush=True)
        return
    freed = before.used - after.used
    if freed < 0:
        print('Net disk usage increased during cleanup: ' + format_bytes(-freed), flush=True)
    else:
        print('Net disk space freed during cleanup: ' + format_bytes(freed), flush=True)
    print('This is the filesystem-wide net change; other writes and delayed Docker reclamation can affect it.', flush=True)


def remove_retired_image(docker, retired):
    # Also handle an old, unlabelled image adopted during the initial rollout.
    # Preserve any other explicit backup tag/digest. Docker refuses removal of
    # an image used by a container; never force removal.
    aliases = docker.run(
        'image', 'inspect', '--format', '{{json .RepoTags}}|{{json .RepoDigests}}',
        retired, capture=True,
    ).split('|')
    if len(aliases) != 2:
        raise RuntimeError('Could not inspect aliases of the retired image.')
    if not any(json.loads(value) for value in aliases):
        print('Cleanup: removing retired app image ' + retired, flush=True)
        docker.run('image', 'rm', retired)


def complete(docker):
    # Call only after ALL deployment checks, including public/private HTTP gates.
    running = healthy_app_image(docker)
    production = image_id(docker, PRODUCTION)
    if not matches_runtime(docker, running, production):
        raise RuntimeError('The running app does not use the newly built production image; skipping cleanup.')
    if running.id != production:
        print('Production and running image indexes differ; their executable manifest matches.', flush=True)
    current = image_id(docker, CURRENT)
    previous = image_id(docker, PREVIOUS)
    changed = bool(current) and not matches_runtime(docker, running, current)

    # Re-running the same image must not replace a useful rollback with itself.
    # Tagging must finish successfully before any cleanup is attempted.
    if changed:
        docker.run('image', 'tag', current, PREVIOUS)
    if current != running.id:
        docker.run('image', 'tag', running.id, CURRENT)
    print('Retained successful app image as ' + CURRENT, flush=True)
    if changed or previous:
        print('Rollback app image is available as ' + PREVIOUS, flush=True)

    path = warn_cleanup('Docker data location lookup', lambda: docker.run(
        'info', '--format', '{{.DockerRootDir}}', capture=True,
    ))
    before = measure_cleanup_disk(docker, path, 'before')

    # Only retire it when the previous tag actually moved to another image.
    if changed and previous and previous not in (current, running.id):
        warn_cleanup('retired app image removal', lambda: remove_retired_image(docker, previous))
    # Deliberately omit --all: tagged current/previous/manual backups must survive.
    print('Cleanup: pruning unused portfolio images...', flush=True)
    warn_cleanup('portfolio image cleanup', lambda: docker.run(
        'image', 'prune', '--force', '--filter', 'label=' + APP_LABEL,
    ))
    # This is the Docker daemon's shared default build cache, not container data.
    print('Cleanup: pruning default build cache (target 256 MB)...', flush=True)
    warn_cleanup('build cache cleanup', lambda: docker.run(
        'buildx', 'prune', '--builder', 'default', '--all', '--force', '--max-used-space', '256MB',
    ))
    after = measure_cleanup_disk(docker, path, 'after')
    report_cleanup_disk_change(before, after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sudo', action='store_true', help='Use sudo -n docker.')
    parser.add_argument('phase', choices=['prepare', 'complete'])
    args = parser.parse_args()
    try:
        {'prepare': prepare, 'complete': complete}[args.phase](Docker(args.sudo))
    except (subprocess.CalledProcessError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, 'Image retention failed; cleanup was not started: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
