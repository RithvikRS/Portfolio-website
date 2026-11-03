#!/usr/bin/env python3
"""Connect Portainer to the global Swarm agent without publishing an admin port."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('swarm', ROOT / 'scripts/swarm-deploy.py')
swarm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swarm)

class API:
    def __init__(self):
        caddy = json.loads(swarm.docker('inspect', swarm.container('caddy')))[0]
        portainer = json.loads(swarm.docker('inspect', swarm.container('portainer')))[0]
        self.pid = caddy['State']['Pid']
        self.address = portainer['NetworkSettings']['Networks']['portfolio_swarm_management']['IPAddress']
        self.origin = 'https://' + dict(v.split('=', 1) for v in caddy['Config']['Env'] if '=' in v)['DOMAIN']
        self.token = None

    def call(self, method, path, payload=None, multipart=False):
        headers = {'Origin': self.origin}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        data = None
        if multipart:
            boundary = 'portfolio-' + secrets.token_hex(16)
            data = ''.join('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+str(value)+'\r\n' for key, value in payload.items()) + '--'+boundary+'--\r\n'
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        elif payload is not None:
            data = json.dumps(payload)
            headers['Content-Type'] = 'application/json'
        request = {'url': 'http://' + self.address + ':9000/api' + path, 'method': method, 'headers': headers, 'data': data}
        # Enter only Caddy's network namespace. Run host Python with credentials on stdin.
        code = "import json,sys,urllib.request,urllib.error\nrequest=json.load(sys.stdin)\ndata=request['data'].encode() if request['data'] is not None else None\nopener=urllib.request.build_opener(urllib.request.ProxyHandler({}))\ntry:\n with opener.open(urllib.request.Request(request['url'],data=data,headers=request['headers'],method=request['method']),timeout=30) as response:\n  raw=response.read()\n  print(json.dumps({'status':response.status,'body':json.loads(raw) if raw else None}))\nexcept urllib.error.HTTPError as error:\n print(json.dumps({'status':error.code,'body':None}))\n"
        result = subprocess.run(['sudo', '-n', 'nsenter', '-t', str(self.pid), '-n', 'python3', '-c', code], input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        if result.returncode:
            (ROOT / '.swarm/portainer-transport-error.txt').write_text(result.stderr)
            raise RuntimeError('Private Portainer API transport failed; inspect .swarm/portainer-transport-error.txt.')
        value = json.loads(result.stdout)
        if value['status'] >= 400:
            raise RuntimeError('Portainer API returned HTTP ' + str(value['status']) + ' for ' + path)
        return value['body']


def validate_nodes(expected, observed):
    if not expected or {n['ID'] for n in observed} != {n['ID'] for n in expected}:
        raise RuntimeError('Portainer node inventory differs from the manager inventory.')
    if any(n['Spec'].get('Availability', 'active') == 'active' and n['Status']['State'] != 'ready' for n in observed):
        raise RuntimeError('An active Swarm node is not ready in Portainer.')


def main():
    os.umask(0o077)
    api = API()
    api.token = api.call('POST', '/auth', {'Username': 'admin', 'Password': (ROOT / '.portainer/recovery-password').read_text().strip()})['jwt']
    try:
        endpoints = api.call('GET', '/endpoints')
        snapshot = ROOT / '.swarm/portainer-endpoints-before.json'
        if not snapshot.exists():
            snapshot.write_text(json.dumps(endpoints, indent=2))
        endpoint = next((e for e in endpoints if e['Name'] == 'Oracle Swarm'), None)
        if endpoint is None:
            endpoint = api.call('POST', '/endpoints', {'Name': 'Oracle Swarm', 'EndpointCreationType': 2, 'URL': 'tcp://tasks.agent:9001', 'TLS': 'true', 'TLSSkipVerify': 'true', 'TLSSkipClientVerify': 'true'}, multipart=True)
        nodes = api.call('GET', '/endpoints/' + str(endpoint['Id']) + '/docker/nodes')
        identifiers = swarm.docker('node', 'ls', '-q').split()
        expected = json.loads(swarm.docker('node', 'inspect', *identifiers))
        validate_nodes(expected, nodes)
        print('Portainer Oracle Swarm environment sees all ' + str(len(nodes)) + ' registered nodes; active nodes are ready.')
        # Remove the obsolete direct node-two agent connection only after Swarm works.
        for item in endpoints:
            if item['Id'] != endpoint['Id'] and ('10.0.0.13:9001' in item.get('URL', '') or '129.154.45.198:9001' in item.get('URL', '')):
                api.call('DELETE', '/endpoints/' + str(item['Id']))
                print('Removed the obsolete standalone node-two agent environment.')
    finally:
        api.call('POST', '/auth/logout')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        sys.exit('Portainer Swarm configuration stopped: ' + str(error))
