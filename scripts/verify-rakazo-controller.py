#!/usr/bin/env python3
"""Verify the running offline pilot; save only non-secret evidence on Ampere."""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import time
BASE=Path('/var/lib/rakazo-pilot')
DOCKER=['sudo','-u','rakazo-pilot','docker','-H','unix://'+str(BASE/'engine/docker.sock')]
def docker(*args):
    return subprocess.check_output(DOCKER+list(args),text=True,stderr=subprocess.PIPE,timeout=40)
def bridge(path,method='GET'):
    result=subprocess.run(['curl','-sS','--max-time','60','--unix-socket',str(BASE/'bridge/bridge.sock'),'-X',method,'-w','\n%{http_code}','http://pilot'+path],capture_output=True,text=True,check=True)
    body,status=result.stdout.rsplit('\n',1)
    return int(status),body
def main():
    if os.geteuid()!=0:raise SystemExit('Run as root on Ampere')
    info=json.loads(docker('inspect','rakazo-bot-pilot-owner'))[0]
    assert info['State']['Running'],'Start the pilot desktop first'
    cid=info['Id']
    cg=Path('/sys/fs/cgroup/user.slice/user-986.slice/user@986.service/rakazo-computers')/('docker-'+cid)
    ceilings={name:(cg/name).read_text().strip() for name in ['memory.max','memory.swap.max','memory.oom.group','cpu.max','pids.max']}
    assert ceilings=={'memory.max':'2147483648','memory.swap.max':'0','memory.oom.group':'1','cpu.max':'100000 100000','pids.max':'512'}
    configs=list((BASE/'engine/exec/containerd').rglob(cid+'/config.json'))
    assert len(configs)==1
    spec=json.loads(configs[0].read_text())
    assert spec['root']['readonly'] and spec['process']['user']['uid']==1000
    assert spec['process']['noNewPrivileges'] and not any(spec['process'].get('capabilities',{}).values())
    status,body=bridge('/api/view','POST');assert status==200
    s=socket.socket(socket.AF_UNIX);s.settimeout(8);s.connect(str(BASE/'bridge/bridge.sock'))
    request='GET /desktop/websockify HTTP/1.1\r\nHost: pilot\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: '+base64.b64encode(os.urandom(16)).decode()+'\r\n\r\n'
    s.sendall(request.encode());data=s.recv(4096)
    assert data.startswith(b'HTTP/1.1 101')
    if b'RFB' not in data:data+=s.recv(4096)
    assert b'RFB' in data,'Desktop framebuffer handshake missing'
    s.close()
    for path in ['/api/models','/api/agent/run']:
        assert bridge(path,'POST')[0]==404
    code="import socket,json; out={};\nfor ip in ['169.254.169.254','10.0.0.249','10.0.0.13','10.0.0.47','144.24.135.201','129.154.45.198','129.225.69.240','1.1.1.1']:\n try:s=socket.create_connection((ip,443),1);s.close();out[ip]=False\n except OSError:out[ip]=True\nprint(json.dumps(out))"
    denied=json.loads(docker('exec','rakazo-bot-pilot-owner','python3','-c',code));assert all(denied.values())
    assert docker('exec','rakazo-bot-pilot-owner','sh','-c','test ! -e /var/run/docker.sock && test ! -e /opt/portfolio/.secrets && echo isolated').strip()=='isolated'
    assert subprocess.check_output(['findmnt','-no','SOURCE',str(BASE/'workspaces/homes/pilot-owner')],text=True).strip().endswith('[/pilot-home]')
    assert (BASE/'bridge/bridge.sock').stat().st_mode & 0o777 == 0o600
    report={'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'ceilings':ceilings,'read_only_root':True,'unprivileged_guest':True,'screen_websocket_and_framebuffer':True,'model_and_agent_routes_disabled':True,'denied_destinations':denied,'production_mounts_absent':True,'home_in_bounded_cache':True,'private_socket_mode':'0600','admission':json.loads((BASE/'admission-verification.json').read_text())}
    assert report['admission']['admission']['reason']=='One-computer pilot limit reached'
    assert report['admission']['unbounded']['denied']
    path=BASE/'controller-verification.json';path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o600)
    print('Controller, desktop framebuffer, model denial, egress denial, bounded home and resource checks passed.')
if __name__=='__main__':main()
