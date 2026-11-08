#!/usr/bin/env python3
"""Install bounded controller services after staging pinned prerequisites on Ampere."""
import json
import os
from pathlib import Path
import pwd
import subprocess
BASE = Path('/var/lib/rakazo-pilot')
ROOT = Path(__file__).resolve().parents[1]
DEST = Path('/opt/rakazo-runtime/pilot')
PREFIX = ['sudo','-u','rakazo-pilot','env','XDG_RUNTIME_DIR=/run/user/986','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/986/bus','HOME='+str(BASE)]
def run(*args):
    return subprocess.run(args,check=True,capture_output=True,text=True).stdout.strip()
def write(path,text,mode=0o644,owner=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text.replace('\r\n','\n'),encoding='utf-8');path.chmod(mode)
    if owner:os.chown(path,*owner)
def main():
    if os.geteuid()!=0 or run('docker','info','--format','{{.Swarm.NodeID}}')!='tzqsl1t88r3l1i8zcqvcmredo':
        raise SystemExit('Run as root on the approved Ampere worker')
    user=pwd.getpwnam('rakazo-pilot')
    if (user.pw_uid,user.pw_gid)!=(986,984):raise SystemExit('Unexpected pilot identity')
    cache=BASE/'engine/cache'
    image=Path('/srv/swarm/.rakazo-runtime-cache.img')
    if not os.path.ismount(cache) or not image.is_file() or image.stat().st_size!=8*1024**3:
        raise SystemExit('Stage and mount the dedicated 8 GiB cache first')
    for path in [BASE/'controller.env',BASE/'controller-src/infra/sandboxes/supervisor/node_modules/tsx/dist/cli.mjs',Path('/opt/rakazo-runtime/node'),Path('/opt/rakazo-runtime/release-20261102.0/runsc')]:
        if not path.is_file():raise SystemExit('Missing staged prerequisite: '+str(path))
    for name in ['runtime_launcher.py','prepare_cgroups.py','enter_namespace.py','bridge.mjs']:
        write(DEST/name,(ROOT/'deploy/rakazo'/name).read_text(),0o755)
    settings=json.loads((BASE/'engine/daemon.json').read_text())
    if settings['data-root']!=str(cache) or settings.get('iptables') is not False or settings.get('bridge')!='none':
        raise SystemExit('Unexpected isolated engine configuration')
    settings['runtimes']['runsc']={'path':str(DEST/'runtime_launcher.py'),'runtimeArgs':['--platform=systrap']}
    settings['default-runtime']='runsc'
    write(BASE/'engine/daemon.json',json.dumps(settings,indent=2)+'\n',0o600,(986,984))
    env=dict(line.split('=',1) for line in (BASE/'controller.env').read_text().splitlines() if '=' in line)
    if any(any(word in key for word in ['OPENAI','ANTHROPIC','GROQ','OPENROUTER','MODEL_API']) for key in env):
        raise SystemExit('Provider credentials are forbidden')
    env.update(SANDBOX_SCREEN_NETWORK='internal',SUPERVISOR_HOST='127.0.0.1',SANDBOX_MAX_COMPUTERS_PER_USER='1',SANDBOX_MAX_COMPUTERS_PER_SPACE='1',SANDBOX_TEAM_SCREEN_LIMIT='1',RAKAZO_COMPUTER_MEMORY='2g',RAKAZO_COMPUTER_CPUS='1',RAKAZO_COMPUTER_PIDS_LIMIT='512')
    write(BASE/'controller.env',''.join(k+'='+v+'\n' for k,v in env.items()),0o600,(986,984))
    for name in ['rakazo-bridge','rakazo-controller','rakazo-engine','rakazo-controller-probe','rakazo-engine-probe']:
        subprocess.run(PREFIX+['systemctl','--user','stop',name],capture_output=True)
    home=BASE/'workspaces/homes/pilot-owner'
    bounded=cache/'pilot-home'
    if not bounded.exists():
        bounded.mkdir();run('cp','-a',str(home)+'/.',str(bounded)+'/');os.chown(bounded,2000999,2000999)
    home_mount=run('systemd-escape','--path','--suffix=mount',str(home))
    write(Path('/etc/systemd/system')/home_mount,f'[Unit]\nRequiresMountsFor={cache}\n[Mount]\nWhat={bounded}\nWhere={home}\nType=none\nOptions=bind,nodev,nosuid\n')
    if not os.path.ismount(home):run('mount','--bind',str(bounded),str(home))
    bridge=BASE/'bridge';bridge.mkdir(exist_ok=True);bridge.chmod(0o700);os.chown(bridge,986,984)
    source=BASE/'controller-src/infra/sandboxes/supervisor/src/computer-spec.ts'
    write(source,source.read_text().replace('process.env.RAKAZO_PILOT_BIND_IP ?? "127.0.0.1"','"127.0.0.1"'),owner=(986,984))
    mount_name=run('systemd-escape','--path','--suffix=mount',str(cache))
    write(Path('/etc/systemd/system')/mount_name,f'[Unit]\nDescription=Bounded disposable Rakazo cache\nRequiresMountsFor=/srv/swarm\n[Mount]\nWhat={image}\nWhere={cache}\nType=ext4\nOptions=loop,nodev,nosuid\n')
    write(Path('/etc/systemd/system/user@986.service.d/rakazo-delegation.conf'),f'[Unit]\nRequiresMountsFor={cache} {home}\n[Service]\nDelegate=cpu cpuset io memory pids\n')
    write(Path('/etc/systemd/system/user-986.slice.d/rakazo-limits.conf'),'[Slice]\nMemoryMax=4G\nMemorySwapMax=0\nCPUQuota=150%\nTasksMax=1536\n')
    units=BASE/'.config/systemd/user'
    units.mkdir(parents=True,exist_ok=True)
    for directory in [BASE/'.config', BASE/'.config/systemd', units]: os.chown(directory,986,984)
    common='\nMemorySwapMax=0\nCPUQuota=50%\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=30\n[Install]\nWantedBy=default.target\n'
    engine=f'''[Unit]
Description=Isolated rootless Rakazo engine
[Service]
Type=simple
Delegate=yes
Environment=HOME={BASE}
Environment=DOCKERD_ROOTLESS_ROOTLESSKIT_NET=none
Environment=DOCKERD_ROOTLESS_ROOTLESSKIT_DETACH_NETNS=false
Environment=DOCKERD_ROOTLESS_ROOTLESSKIT_STATE_DIR={BASE}/engine/rootlesskit
ExecStartPre=/usr/bin/python3 {DEST}/prepare_cgroups.py
ExecStart=/usr/bin/dockerd-rootless.sh --config-file={BASE}/engine/daemon.json
MemoryMax=1G
TasksMax=512'''
    write(units/'rakazo-engine.service',engine+common,owner=(986,984))
    for mode,limit in [('controller','512M'),('bridge','128M')]:
        write(units/('rakazo-'+mode+'.service'),f'[Unit]\nDescription=Rakazo pilot {mode}\nAfter=rakazo-engine.service\nBindsTo=rakazo-engine.service\n[Service]\nEnvironmentFile={BASE}/controller.env\nExecStart=/usr/bin/python3 {DEST}/enter_namespace.py {mode}\nMemoryMax={limit}\nTasksMax=128'+common,owner=(986,984))
    run('systemctl','daemon-reload')
    for name in ['rakazo-controller-probe','rakazo-engine-probe']:
        subprocess.run(PREFIX+['systemctl','--user','stop',name],capture_output=True)
    run(*PREFIX,'systemctl','--user','daemon-reload')
    run(*PREFIX,'systemctl','--user','enable','rakazo-engine','rakazo-controller','rakazo-bridge')
    run('loginctl','enable-linger','rakazo-pilot')
    run(*PREFIX,'systemctl','--user','start','rakazo-engine','rakazo-controller','rakazo-bridge')
    print('Dedicated services installed; no public route opened.')
if __name__=='__main__':main()
