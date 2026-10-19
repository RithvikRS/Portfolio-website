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
ERROR_MESSAGES = {
    'ssh-key': 'Oracle rejected the ARM SSH public key. Check the dedicated public-key file.',
    'authentication': 'Oracle rejected the ARM request credentials or permissions. Check OCI configuration.',
    'quota': 'Oracle reported an ARM quota or service limit. Review limits before retrying.',
    'connection': 'ARM provisioning hit a rate limit or connection timeout. Check the server logs if it persists.',
    'other': 'ARM provisioning encountered an unexpected error. Check ~/stack-latest-job.json on the AMD server.',
}
ERROR_COOLDOWN = 86400


def classify_error(text):
    """Only known capacity responses are routine; other failures need attention."""
    lower = text.lower()
    if 'out of host capacity' in lower or 'out of capacity' in lower:
        return 'capacity', ''
    if 'invalid ssh public key' in lower:
        return 'ssh-key', ERROR_MESSAGES['ssh-key']
    if any(x in lower for x in ('notauthenticated', 'notauthorized', 'authentication', 'authorization')):
        return 'authentication', ERROR_MESSAGES['authentication']
    if any(x in lower for x in ('limitexceeded', 'quotaexceeded', 'limit exceeded', 'quota exceeded')):
        return 'quota', ERROR_MESSAGES['quota']
    if any(x in lower for x in ('toomanyrequests', 'too many requests', 'timed out', 'timeout')):
        return 'connection', ERROR_MESSAGES['connection']
    return 'other', ERROR_MESSAGES['other']


def write_private(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)
    if os.name == 'posix':
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


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
    sent = state.setdefault('sent_errors', {})
    pending = state.setdefault('pending', {})
    # Preserve the last delivered alert when upgrading the original state file.
    old = state.get('error', {})
    if old.get('category') in ERROR_MESSAGES and 'sent_at' in old:
        sent.setdefault(old['category'], old['sent_at'])
    if kind == 'error':
        category, _ = classify_error(detail)
        if category == 'capacity':
            kind = 'clear'
        else:
            state['error'] = {'category': category}
            if category not in sent or now - sent[category] >= ERROR_COOLDOWN:
                # At most one fixed alert per category, plus one success: six records.
                pending.setdefault(category, {'created_at': now})
    if kind == 'clear':
        # Clear current condition only. Capacity must not reset delivery history.
        state.pop('error', None)
    elif kind == 'success':
        if detail not in ('RUNNING', 'PROVISIONING'):
            raise ValueError('Unsupported instance state')
        if not state.get('success'):
            pending.setdefault('success', {'created_at': now, 'state': detail})
        state.pop('error', None)
    # Persist before any network request; retries never depend on the next OCI result.
    write_private(state_path, state)
    for key, event in list(pending.items()):
        if key == 'success':
            label = 'running' if event['state'] == 'RUNNING' else 'provisioning'
            send('ARM instance claimed', 'Oracle reports vantize-ampere-a1 is ' + label +
                 ' (2 OCPUs, 12 GB RAM). Capacity retries have stopped. Check the Oracle console for its IP and readiness.', 4)
            state['success'] = {'sent_at': now, 'state': event['state']}
        else:
            message = ERROR_MESSAGES[key]
            if now - event['created_at'] >= 60:
                message += ' Delayed alert from an earlier attempt; the condition may have changed.'
            send('ARM provisioning needs attention', message, 4)
            sent[key] = now
        del pending[key]
        write_private(state_path, state)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('event', choices=['error', 'success', 'clear', 'retry', 'test'])
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
