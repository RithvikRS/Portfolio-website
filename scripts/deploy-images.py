#!/usr/bin/env python3
"""Retain successful portfolio images before pruning; never remove runtime data."""
import argparse
import json
import subprocess
import sys

PRODUCTION = 'rithvik-portfolio:production'
CURRENT = 'rithvik-portfolio:current'
PREVIOUS = 'rithvik-portfolio:previous'
APP_LABEL = 'io.github.rithvikrs.portfolio.app=true'


class Docker:
    def __init__(self, sudo=False):
        self.command = ['sudo', '-n', 'docker'] if sudo else ['docker']

    def run(self, *args, capture=False):
        result = subprocess.run(
            self.command + list(args), check=True, text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout.strip() if capture else None


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
    state = docker.run(
        'container', 'inspect', '--format',
        '{{.Image}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}',
        containers[0], capture=True,
    ).split()
    if len(state) != 3 or state[1:] != ['true', 'healthy']:
        raise RuntimeError('The portfolio app must be running and healthy before retaining its image.')
    return state[0]


def prepare(docker):
    # production is a mutable build tag; it may already point at a failed build.
    # Bootstrap from the actual healthy container, then keep this tag on failures.
    if image_id(docker, CURRENT):
        return
    running = healthy_app_image(docker, required=False)
    if running:
        docker.run('image', 'tag', running, CURRENT)
        print('Retained the running app as ' + CURRENT)


def warn_cleanup(action, callback):
    try:
        callback()
    except (subprocess.CalledProcessError, OSError, RuntimeError, ValueError) as error:
        print('WARNING: Deployment is healthy, but ' + action + ' failed: ' + str(error), file=sys.stderr)


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
        docker.run('image', 'rm', retired)


def complete(docker):
    # Call only after ALL deployment checks, including public/private HTTP gates.
    running = healthy_app_image(docker)
    if running != image_id(docker, PRODUCTION):
        raise RuntimeError('The running app does not use the newly built production image; skipping cleanup.')
    current = image_id(docker, CURRENT)
    previous = image_id(docker, PREVIOUS)

    # Re-running the same image must not replace a useful rollback with itself.
    # Tagging must finish successfully before any cleanup is attempted.
    if current and current != running:
        docker.run('image', 'tag', current, PREVIOUS)
    if current != running:
        docker.run('image', 'tag', running, CURRENT)
    print('Retained successful app image as ' + CURRENT)
    if (current and current != running) or previous:
        print('Rollback app image is available as ' + PREVIOUS)

    # Only retire it when the previous tag actually moved to another image.
    if current and current != running and previous and previous not in (current, running):
        warn_cleanup('retired app image removal', lambda: remove_retired_image(docker, previous))
    # Deliberately omit --all: tagged current/previous/manual backups must survive.
    warn_cleanup('portfolio image cleanup', lambda: docker.run(
        'image', 'prune', '--force', '--filter', 'label=' + APP_LABEL,
    ))
    # This is the Docker daemon's shared default build cache, not container data.
    warn_cleanup('build cache cleanup', lambda: docker.run(
        'buildx', 'prune', '--builder', 'default', '--all', '--force', '--max-used-space', '256MB',
    ))


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
