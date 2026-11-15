#!/usr/bin/env python3
"""Publish a tested image archive; never build on or connect to production."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parents[1]


def run(*args, data=None):
    return subprocess.check_output(args, input=data, text=True).strip()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    manifest = json.loads((ROOT / 'deploy/rakazo/publication.json').read_text())
    if os.environ.get('GITHUB_REPOSITORY') != 'RithvikRS/Portfolio-website':
        raise RuntimeError('Publish only from the approved repository.')
    tag = manifest['registry_tag']
    if not re.fullmatch(r'ghcr.io/rithvikrs/portfolio-website:rakazo-workspace-[a-f0-9]{16}', tag):
        raise RuntimeError('Unexpected target tag.')
    request = Request('https://api.github.com/repos/RithvikRS/Portfolio-website/releases/assets/' + str(int(manifest['asset_id'])), headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/octet-stream',
        'X-GitHub-Api-Version': '2022-11-28'})
    try:
        response = build_opener(NoRedirect).open(request, timeout=90)
    except HTTPError as error:
        if error.code != 302:
            raise
        location = error.headers['Location']
        if not location.startswith('https://'):
            raise RuntimeError('Insecure asset redirect.')
        # The signed asset URL needs no GitHub credential.
        response = urlopen(location, timeout=90)
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / 'image.tar.gz'
        with response, archive.open('wb') as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
        digest = hashlib.sha256()
        with archive.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != manifest['archive_sha256']:
            raise RuntimeError('Archive checksum differs from the tested export.')
        run('docker', 'load', '-i', str(archive))
        image = json.loads(run('docker', 'image', 'inspect', manifest['local_tag']))[0]
        if image['Id'] != manifest['image_id']:
            raise RuntimeError('Loaded image differs from the tested configuration.')
        spec = importlib.util.spec_from_file_location('builder', ROOT / 'scripts/build-rakazo-app.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.verify_image(image, manifest['inputs'])
        run('docker', 'tag', image['Id'], tag)
        try:
            run('docker', 'login', 'ghcr.io', '-u', os.environ['GITHUB_ACTOR'], '--password-stdin', data=os.environ['GH_TOKEN'])
            subprocess.run(['docker', 'push', tag], check=True)
        finally:
            subprocess.run(['docker', 'logout', 'ghcr.io'], check=True)
        digests = json.loads(run('docker', 'image', 'inspect', tag))[0]['RepoDigests']
        matches = [d for d in digests if d.startswith('ghcr.io/rithvikrs/portfolio-website@sha256:')]
        if len(matches) != 1:
            raise RuntimeError('Expected one registry manifest digest.')
        print('PUBLISHED_IMAGE=' + matches[0])
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('Verified ARM64 Rakazo image: `' + matches[0] + '`\n')


if __name__ == '__main__':
    main()
