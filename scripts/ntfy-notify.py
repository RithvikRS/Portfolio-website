#!/usr/bin/env python3
"""Publish fixed ARM status messages without forwarding OCI output or credentials."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / '.ntfy'


def classify_error(text):
    """Only known capacity responses are routine; other failures need attention."""
    lower = text.lower()
    if 'out of host capacity' in lower or 'out of capacity' in lower:
        return 'capacity', ''
    if 'invalid ssh public key' in lower:
        return 'ssh-key', 'Oracle rejected the ARM SSH public key. Check the dedicated public-key file.'
    if any(x in lower for x in ('notauthenticated', 'notauthorized', 'authentication', 'authorization')):
        return 'authentication', 'Oracle rejected the ARM request credentials or permissions. Check OCI configuration.'
    if any(x in lower for x in ('limitexceeded', 'quotaexceeded', 'limit exceeded', 'quota exceeded')):
        return 'quota', 'Oracle reported an ARM quota or service limit. Review limits before retrying.'
    if any(x in lower for x in ('toomanyrequests', 'too many requests', 'timed out', 'timeout')):
        return 'connection', 'ARM provisioning hit a rate limit or connection timeout. Check the server logs if it persists.'
    return 'other', 'ARM provisioning encountered an unexpected error. Check ~/stack-latest-job.json on the AMD server.'


def write_private(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
        stream.write('\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def publish(title, message, priority=3):
    credentials = json.loads((PRIVATE / 'publisher.json').read_text())
    authorization = base64.b64encode((credentials['username'] + ':' + credentials['password']).encode()).decode()
    request = Request('http://127.0.0.1:2586/' + credentials['topic'], data=message.encode(),
                      headers={'Authorization': 'Basic ' + authorization, 'Title': title,
                               'Priority': str(priority), 'Content-Type': 'text/plain; charset=utf-8'})
    # Keep local credentials on this machine and reject unexpected redirects.
    from urllib.request import HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
        result = json.load(response)
    if result.get('event') != 'message' or result.get('topic') != credentials['topic']:
        raise RuntimeError('Unexpected publish response')


def notify(kind, detail='', state_path=None, send=None, now=None):
    state_path = state_path or PRIVATE / 'arm-notifications.json'
    send = send or publish
    now = time.time() if now is None else now
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if kind == 'error':
        category, message = classify_error(detail)
        if category == 'capacity':
            kind = 'clear'
        else:
            old = state.get('error', {})
            if old.get('category') == category and now - old.get('sent_at', 0) < 86400:
                return True
            send('ARM provisioning needs attention', message, 4)
            state['error'] = {'category': category, 'sent_at': now}
    if kind == 'clear':
        state.pop('error', None)
    elif kind == 'success':
        if state.get('success'):
            return True
        label = 'running' if detail == 'RUNNING' else 'provisioning'
        send('ARM instance claimed', 'Oracle reports vantize-ampere-a1 is ' + label +
             ' (2 OCPUs, 12 GB RAM). Capacity retries have stopped. Check the Oracle console for its IP and readiness.', 4)
        state['success'] = {'sent_at': now, 'state': detail}
        state.pop('error', None)
    write_private(state_path, state)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('event', choices=['error', 'success', 'clear', 'test'])
    parser.add_argument('detail', nargs='?', default='')
    args = parser.parse_args()
    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    import fcntl
    with (PRIVATE / 'notify.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if args.event == 'test':
                publish('ntfy test', 'Private notifications are connected to the AMD server. Normal ARM capacity retries stay quiet.')
            else:
                detail = Path(args.detail).read_text() if args.event == 'error' else args.detail
                notify(args.event, detail)
        except Exception:
            # Never print network errors containing credentials, raw OCI responses, or tokens.
            print('ntfy delivery failed; leave the ARM cron entry enabled so the next run can retry.', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
