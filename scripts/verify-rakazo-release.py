#!/usr/bin/env python3
"""Disposable compiled-entrypoint/browser/restore rehearsal on the approved Ampere worker."""
import argparse
import importlib.util
import json
import io
import tarfile
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('verify_workspace',ROOT/'scripts/verify-rakazo-workspace.py')
v=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(v)
docker=v.Docker(True)
LABEL='portfolio.rakazo.release-test'
BASE=Path('/home/opc/.config')
ORIGIN='https://rakazo.verify.test:18443'


def save(state):
    p=Path(state['directory'])/'state.json'
    p.write_text(json.dumps(state,indent=2)+'\n');p.chmod(0o600)


def load(path):
    p=Path(path).resolve()
    if p.name!='state.json' or p.parent.parent!=BASE or not p.parent.name.startswith('rakazo-release-'):
        raise RuntimeError('Only a private disposable test state is accepted.')
    state=json.loads(p.read_text())
    if Path(state['directory'])!=p.parent or state['prefix']!=p.parent.name:
        raise RuntimeError('Test state path mismatch.')
    info=json.loads(docker.call('info','--format','{{json .}}'))
    v.validate_host(info,'unix:///var/run/docker.sock',True)
    return state


def owned(state,kind,identifier):
    info=json.loads(docker.call(kind,'inspect',identifier))[0]
    labels=info.get('Config',{}).get('Labels') if kind=='container' else info.get('Labels')
    if (labels or {}).get(LABEL)!=state['prefix']:
        raise RuntimeError('Refusing to mutate a resource not owned by this disposable session.')


def create(state,key,args):
    identifier=docker.call('create','--label',LABEL+'='+state['prefix'],*args[1:])
    state['containers'][key]=identifier;save(state)
    return identifier


def remove(state,key):
    identifier=state['containers'].get(key)
    if not identifier:return
    owned(state,'container',identifier)
    docker.call('rm','-f','-v',identifier)
    del state['containers'][key];save(state)


def volume(state,key,suffix):
    name=state['prefix']+'-'+suffix
    docker.call('volume','create','--label',LABEL+'='+state['prefix'],name)
    state['volumes'][key]=name;save(state)
    return name


def wait_db(state):
    for _ in range(60):
        try:
            docker.call('exec',state['containers']['db'],'pg_isready','-h','127.0.0.1','-U','verify_owner','-d',state['database'],timeout=10);return
        except RuntimeError:time.sleep(1)
    raise RuntimeError('Disposable database did not become ready.')


def envs(values):
    return [part for key,value in values.items() for part in ['-e',key+'='+value]]


def start_db(state):
    db=create(state,'db',v.database_args(state['prefix']+'-db',state['network'],state['database'],state['owner_password']))
    docker.call('start',db);wait_db(state)


def migrate(state):
    environment={'DATABASE_URL':state['database_url'],'DATABASE_MIGRATION_URL':state['owner_url'],'NODE_ENV':'production'}
    cid=create(state,'migration',v.application_args(state['prefix']+'-migration',state['network'],state['image'],environment,['node','dist/cli/migrate-database.js'],'/app/apps/api'))
    docker.call('start',cid)
    if docker.call('wait',cid,timeout=600)!='0':raise RuntimeError('Disposable migration failed.')
    remove(state,'migration')


def seed(state,source=None,archives=None):
    cid=create(state,'seed',['create','--name',state['prefix']+'-seed','--network','none',*v.limits('256m','0.25'),'--user','0:0','--cap-add','CHOWN',
        '--mount','type=volume,src='+state['volumes']['secrets']+',dst=/run/secrets',
        '--mount','type=volume,src='+state['volumes']['data']+',dst=/data',
        '--entrypoint','sh',state['image'],'-ec','chown 1000:1000 /data; exec sleep 300'])
    docker.call('start',cid)
    if source:
        for path in source.iterdir():docker.call('cp',str(path),cid+':/run/secrets/'+path.name)
    if archives:
        for key,target in [('secrets','/run/secrets'),('data','/data')]:
            binary(['exec','-i','--user','1000:1000' if key=='data' else '0:0',cid,'tar','--no-same-owner','-xzf','-','-C',target],input_file=archives/key)
    remove(state,'seed')


def start_apps(state):
    if 'native-fixture' not in state['containers']:
        cid=create(state,'native-fixture',['create','--name',state['prefix']+'-native-fixture','--network',state['network'],
            '--network-alias','omniroute','--network-alias','rakazo_executor',*v.limits('128m','0.25'),'--user','1000:1000','--read-only',
            '--mount','type=volume,src='+state['volumes']['secrets']+',dst=/run/secrets,readonly',
            '-e','VERIFY_RAKAZO_DISPOSABLE=1','--entrypoint','node',state['image'],'/run/secrets/verify-native-model.mjs'])
        docker.call('start',cid)
    catalog=json.loads((ROOT/'deploy/swarm-services.json').read_text())
    for mode in ['api','web']:
        source=catalog['services']['rakazo_'+mode]
        environment=dict(source['environment'])
        for key in ['API_URL','BETTER_AUTH_URL','WEB_ORIGIN']:
            if key in environment:environment[key]=ORIGIN
        if mode=='api':
            environment.update(OIDC_ISSUER=ORIGIN+'/idp',OIDC_CLIENT_ID='disposable-client',OIDC_NAME='Disposable identity',NODE_EXTRA_CA_CERTS='/run/secrets/test-ca.pem')
            # Deliberately hostile service overrides must be reset by the real entrypoint.
            environment.update(WORKSPACE_ONLY='false',SANDBOX_PROVIDER='docker',CLOUD_AGENT_PROVIDER='emulator',AUTH_PASSWORD_ENABLED='true',OIDC_ALLOW_SIGNUP_BYPASS='true')
        else:environment.update(RAKAZO_HOST='rakazo.verify.test',RAKAZO_ALLOWED_HOSTS='verify-web,localhost,127.0.0.1',API_PROXY_TARGET='http://verify-api:3100')
        args=['create','--name',state['prefix']+'-'+mode,'--network',state['network'],'--network-alias','verify-'+mode,
            *v.limits('1g' if mode=='api' else '512m','1' if mode=='api' else '0.5'),'--user','1000:1000','--read-only',
            '--mount','type=volume,src='+state['volumes']['secrets']+',dst=/run/secrets,readonly']
        for mount in source['volumes']:
            if mount['type']=='tmpfs':args+=['--tmpfs',mount['target']+':rw,nosuid,nodev,mode=1777,size='+str(mount['tmpfs']['size'])]
        if mode=='api':args+=['--mount','type=volume,src='+state['volumes']['data']+',dst=/data']
        args += envs(environment)+['--entrypoint','node',state['image'],'/run/secrets/entrypoint.mjs',mode]
        cid=create(state,mode,args);docker.call('start',cid)
    edge=create(state,'edge',['create','--name',state['prefix']+'-edge','--network',state['network'],'--network-alias','rakazo.verify.test',
        *v.limits('128m','0.25'),'--user','1000:1000','--read-only',
        '--mount','type=volume,src='+state['volumes']['secrets']+',dst=/run/secrets,readonly',
        '-e','VERIFY_RAKAZO_DISPOSABLE=1','--entrypoint','node',state['image'],'/run/secrets/verify-edge.mjs'])
    docker.call('start',edge)
    for mode,port,path in [('api',3100,'/ready'),('web',5173,'/')]:
        for _ in range(60):
            try:
                docker.call('exec',state['containers'][mode],'node','-e',f"fetch('http://127.0.0.1:{port}{path}').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))",timeout=10)
                break
            except RuntimeError:time.sleep(1)
        else:raise RuntimeError('Compiled '+mode+' failed readiness under production entrypoint settings.')
    print('Compiled API and web are ready with read-only roots and file-backed disposable secrets.')


def binary(args,output_file=None,input_file=None):
    with (Path(input_file).open('rb') if input_file else open(os.devnull,'rb')) as source:
        if output_file:
            fd=os.open(output_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as target:
                r=subprocess.run(docker.prefix+args,stdin=source,stdout=target,stderr=subprocess.PIPE,timeout=300)
        else:r=subprocess.run(docker.prefix+args,stdin=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
    if r.returncode:
        destination=Path(output_file or input_file).parent/'command-error.log'
        destination.write_bytes(r.stderr);destination.chmod(0o600)
        raise RuntimeError('Private backup/restore operation failed; private diagnostics retained, no database output printed.')


def logs(state):
    target=Path(state['directory'])/'logs';target.mkdir(mode=0o700,exist_ok=True)
    for key,cid in state['containers'].items():
        try: content=docker.call('logs',cid)
        except RuntimeError:content='Logs unavailable'
        for value in [state['owner_password'],state['app_password']]:content=content.replace(value,'[redacted]')
        p=target/(key+'.log');p.write_text(content);p.chmod(0o600)


def cleanup(state):
    errors=[]
    for key in list(state['containers']):
        try:remove(state,key)
        except RuntimeError:errors.append(key)
    for key,name in list(state['volumes'].items()):
        try:
            owned(state,'volume',name);docker.call('volume','rm',name);del state['volumes'][key];save(state)
        except RuntimeError:errors.append(key)
    if state.get('network'):
        try:
            owned(state,'network',state['network']);docker.call('network','rm',state['network']);state['network']=None;save(state)
        except RuntimeError:errors.append('network')
    if errors:raise RuntimeError('Disposable cleanup incomplete: '+','.join(errors))
    print('Removed only the labelled test containers, volumes and network.')


def check_missing_secrets(state):
    code=(ROOT/'deploy/rakazo/entrypoint.mjs').read_text(encoding='utf-8-sig')
    cid=create(state,'missing-secrets',['create','--name',state['prefix']+'-missing-secrets','--network','none',
        *v.limits('128m','0.25'),'--user','1000:1000','--read-only',
        '-e','DATABASE_URL=postgres://disposable-invalid/db','--entrypoint','node',state['image'],
        '--input-type=module','-e',code,'fixture','api'])
    docker.call('start',cid)
    result=docker.call('wait',cid)
    output=docker.call('logs',cid)
    if result=='0' or 'ENOENT' not in output or 'rakazo_database_url' not in output:
        raise RuntimeError('Missing secret file did not fail closed at the expected read.')
    remove(state,'missing-secrets')
    print('Missing secret files fail closed even when a fallback environment value is present.')


def start(image):
    v.verify(image,True,docker,True)
    prefix='rakazo-release-'+uuid.uuid4().hex[:12]
    directory=BASE/prefix;directory.mkdir(mode=0o700)
    database='rakazo_workspace_verify_'+prefix.removeprefix('rakazo-release-')
    owner_password,app_password=secrets.token_hex(32),secrets.token_hex(32)
    state={'prefix':prefix,'directory':str(directory),'image':image,'database':database,'owner_password':owner_password,'app_password':app_password,
           'database_url':f'postgres://rakazo_app:{app_password}@verify-db:5432/{database}',
           'owner_url':f'postgres://verify_owner:{owner_password}@verify-db:5432/{database}', 'containers':{},'volumes':{}}
    save(state)
    try:
        state['network']=docker.call('network','create','--internal','--label',LABEL+'='+prefix,prefix);save(state)
        check_missing_secrets(state)
        volume(state,'secrets','secrets');volume(state,'data','data')
        bundle=directory/'bundle';bundle.mkdir(mode=0o700)
        values={name:secrets.token_hex(32) for name in ['rakazo_encryption_key','rakazo_auth_secret','rakazo_screen_secret','rakazo_oidc_secret','rakazo_pilot_model_key']}
        values.update(rakazo_database_url=state['database_url'],rakazo_owner_email='owner@example.test')
        for name,value in values.items():(bundle/name).write_text(value)
        for name in ['entrypoint.mjs','verify-edge.mjs','verify-native-model.mjs']:(bundle/name).write_bytes((ROOT/'deploy/rakazo'/name).read_bytes())
        r=subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(bundle/'test-key.pem'),'-out',str(bundle/'test-ca.pem'),'-days','2','-subj','/CN=rakazo.verify.test','-addext','subjectAltName=DNS:rakazo.verify.test'],capture_output=True,timeout=30)
        if r.returncode:raise RuntimeError('Could not create disposable TLS certificate.')
        for path in bundle.iterdir():path.chmod(0o444)
        seed(state,source=bundle);start_db(state);migrate(state);start_apps(state)
        print('STATE='+str(directory/'state.json'))
    except BaseException:
        logs(state);cleanup(state);raise


def seal_backup(state, backup):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    recovery={key:state[key] for key in ['database','owner_password','app_password','database_url','owner_url','image']}
    (backup/'database-recovery.json').write_text(json.dumps(recovery))
    (backup/'database-recovery.json').chmod(0o600)
    names=['database.dump','secrets','data','database-recovery.json']
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode='w:gz') as archive:
        for name in names:
            if (backup/name).stat().st_size>128*1024**2:raise RuntimeError('Disposable backup unexpectedly large.')
            archive.add(backup/name,arcname=name)
    key=secrets.token_bytes(32);nonce=secrets.token_bytes(12);aad=b'rakazo-disposable-backup-v1'
    encrypted=AESGCM(key).encrypt(nonce,payload.getvalue(),aad)
    recovery_dir=Path(state['directory'])/'recovery';recovery_dir.mkdir(mode=0o700)
    key_file=recovery_dir/'backup.key';key_file.write_bytes(key);key_file.chmod(0o600)
    sealed=backup/'archive.aesgcm';sealed.write_bytes(nonce+encrypted);sealed.chmod(0o600)
    for test_key,test_data in [(secrets.token_bytes(32),encrypted),(key,encrypted[:-1]+bytes([encrypted[-1]^1]))]:
        try:AESGCM(test_key).decrypt(nonce,test_data,aad)
        except InvalidTag:pass
        else:raise RuntimeError('Backup authentication negative check failed.')
    if AESGCM(key).decrypt(nonce,encrypted,aad)!=payload.getvalue():raise RuntimeError('Backup round-trip failed.')
    for name in names:(backup/name).unlink()
    print('Complete disposable backup encrypted with AES-256-GCM; wrong-key and tamper checks rejected access.')


def open_backup(state,backup):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    value=(backup/'archive.aesgcm').read_bytes()
    key=(Path(state['directory'])/'recovery/backup.key').read_bytes()
    clear=AESGCM(key).decrypt(value[:12],value[12:],b'rakazo-disposable-backup-v1')
    destination=Path(state['directory'])/'restore-input';destination.mkdir(mode=0o700)
    expected={'database.dump','secrets','data','database-recovery.json'}
    with tarfile.open(fileobj=io.BytesIO(clear),mode='r:gz') as archive:
        members=archive.getmembers()
        if len(members)!=len(expected) or {m.name for m in members}!=expected:
            raise RuntimeError('Unexpected disposable backup contents.')
        for member in members:
            if not member.isfile() or member.size>128*1024**2:raise RuntimeError('Unsafe backup entry.')
            target=destination/member.name;target.write_bytes(archive.extractfile(member).read());target.chmod(0o600)
    recovered=json.loads((destination/'database-recovery.json').read_text())
    for key in ['database','owner_password','app_password','database_url','owner_url','image']:state[key]=recovered[key]
    save(state)
    return destination


def restore(state):
    backup=Path(state['directory'])/'backup'
    backup.mkdir(mode=0o700)
    # Stop writers before coordinated database, encryption-material and file snapshots.
    for key in ['edge','web','api','native-fixture']:remove(state,key)
    binary(['exec',state['containers']['db'],'pg_dump','-U','verify_owner','-d',state['database'],'-Fc'],output_file=backup/'database.dump')
    for key in ['secrets','data']:
        helper=create(state,'archive',['create','--name',state['prefix']+'-archive','--network','none',*v.limits('256m','0.25'),'--user','1000:1000','--read-only',
            '--mount','type=volume,src='+state['volumes'][key]+',dst=/backup,readonly','--entrypoint','tar',state['image'],'-czf','-','-C','/backup','.'])
        binary(['start','--attach',helper],output_file=backup/key)
        if json.loads(docker.call('inspect',helper))[0]['State']['ExitCode']!=0:raise RuntimeError('Snapshot archive failed.')
        remove(state,'archive')
    seal_backup(state,backup)
    remove(state,'db')
    for key,name in list(state['volumes'].items()):
        owned(state,'volume',name);docker.call('volume','rm',name);del state['volumes'][key];save(state)
    volume(state,'secrets','restored-secrets');volume(state,'data','restored-data')
    restored=open_backup(state,backup)
    seed(state,archives=restored);start_db(state);migrate(state)
    binary(['exec','-i',state['containers']['db'],'pg_restore','-U','verify_owner','-d',state['database'],'--clean','--if-exists','--exit-on-error'],input_file=restored/'database.dump')
    start_apps(state)
    for path in restored.iterdir():path.unlink()
    restored.rmdir()
    state['restored']=True;save(state)
    print('Restored into a new database and new secret/data volumes after removing the originals; verify notes in the browser.')


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','restore','stop','logs'])
    parser.add_argument('--image');parser.add_argument('--state')
    args=parser.parse_args()
    try:
        if args.action=='start':start(args.image or '')
        else:
            state=load(args.state or '')
            try:
                if args.action=='restore':restore(state)
                elif args.action=='stop':cleanup(state)
                else:logs(state)
            except BaseException:
                logs(state)
                if args.action=='restore':cleanup(state)
                raise
    except (RuntimeError,ValueError,KeyError,OSError) as error:
        print(str(error) if isinstance(error,RuntimeError) else 'Disposable operation stopped; inspect private test diagnostics.',file=sys.stderr)
        sys.exit(1)
