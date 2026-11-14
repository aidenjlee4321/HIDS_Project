"""Explicit owner-approved Linux 2 install/owned-child acceptance; no HTTP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import time

VM='46330e53-4a53-4a94-b9d4-0adefd192ab7'
INSTALL=Path('/opt/hids-process-pipeline')
def require(v):
    if not v:raise RuntimeError('process_install_acceptance_refused')
def command(*args):return subprocess.check_output(args,text=True,timeout=20).strip()
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(path,data,mode=0o600,gid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,gid);os.fchmod(f.fileno(),mode)
def install(source,manifest,build,binary_sha,trial_sha):
    require(os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()==VM)
    require(not INSTALL.exists() and not Path('/etc/hids/process.json').exists() and not Path('/etc/systemd/system/hids-process-runtime.service').exists())
    sys.path.insert(0,str(source/'scripts'));import dev
    dev.verify(source,manifest)
    report=json.loads((build/'report.json').read_text());require(report['status']=='passed' and report['source_sha256']==manifest)
    require(digest(build/'process-collector')==binary_sha and digest(build/'process-owned-trial')==trial_sha)
    reader=pwd.getpwnam('hids-process');backend=pwd.getpwnam('hids-ingest');require(reader.pw_uid>0 and reader.pw_uid!=backend.pw_uid)
    INSTALL.mkdir(mode=0o755);INSTALL.chmod(0o755);(INSTALL/'code').mkdir(mode=0o755);(INSTALL/'code').chmod(0o755);files={}
    for name in ('engine','api'):
        for p in sorted((source/name).rglob('*.py')):
            rel=p.relative_to(source);dst=INSTALL/'code'/rel;dst.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            data=p.read_bytes();write(dst,data,0o644);files[str(rel)]=hashlib.sha256(data).hexdigest()
    for directory in (INSTALL/'code').rglob('*'):
        if directory.is_dir():directory.chmod(0o755)
    write(INSTALL/'code-manifest.json',json.dumps(files,sort_keys=True).encode(),0o644)
    for name,sha in [('process-collector',binary_sha),('process-owned-trial',trial_sha)]:
        data=(build/name).read_bytes();require(hashlib.sha256(data).hexdigest()==sha);write(INSTALL/name,data,0o555)
    import uuid
    cfg=dict(version=1,source_id=str(uuid.uuid4()),code=str(INSTALL/'code'),binary=str(INSTALL/'process-collector'),binary_sha256=binary_sha,max_events=10000,max_bytes=64*1024*1024,minimum_free=256*1024*1024)
    write(Path('/etc/hids/process.json'),json.dumps(cfg,sort_keys=True,separators=(',',':')).encode(),0o440,backend.pw_gid)
    path=Path('/var/lib/hids/process');require(not path.exists());path.mkdir(mode=0o700);os.chown(path,backend.pw_uid,backend.pw_gid)
    runtime=Path('/run/hids/process');require(not runtime.exists());runtime.mkdir(mode=0o750);runtime.chmod(0o750);os.chown(runtime,0,reader.pw_gid)
    backend_run=Path('/run/hids/process-backend');require(not backend_run.exists());backend_run.mkdir(mode=0o750);backend_run.chmod(0o750);os.chown(backend_run,0,backend.pw_gid)
    units=[]
    for name in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket'):
        unit=Path('/etc/systemd/system')/name;write(unit,(source/'packaging/systemd'/name).read_bytes(),0o644);units.append(str(unit))
    write(Path('/usr/lib/tmpfiles.d/hids-process.conf'),(source/'packaging/systemd/hids-process.tmpfiles.conf').read_bytes(),0o644)
    command('systemd-analyze','verify',*units);command('systemctl','daemon-reload')
    require(command('systemctl','show','hids-process-runtime.service','-p','ActiveState','--value')=='inactive')
    dev.verify(source,manifest)
    print(json.dumps({'installed':str(INSTALL),'source_manifest':manifest,'source_id':cfg['source_id'],'collection_started':False}))

def accept():
    require(os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()==VM)
    sys.path.insert(0,str(INSTALL/'code'))
    from api import setup_manager as manager,setup_preflight as preflight
    from api.setup_store import root_store
    from engine.ingestion import process_control as control
    cfg=control.configuration();reader=pwd.getpwnam('hids-process');backend=pwd.getpwnam('hids-ingest')
    lab=Path(tempfile.mkdtemp(prefix='hids-process-integration.',dir='/opt'));lab.chmod(0o700)
    results={};drop=Path('/run/systemd/system/hids-process-collector.service.d');require(not drop.exists());drop.mkdir(mode=0o755)
    override="[Service]\nExecStart=\nExecStart=/opt/hids-process-pipeline/process-owned-trial /run/hids/process/current.json\n"
    write(drop/'owned-fixture.conf',override.encode(),0o644);command('systemctl','daemon-reload')
    original={str(p):digest(p) for p in Path('/etc/hids/setup').glob('selection-*.json')}
    try:
        with manager.root_lock():
            m=manager.manager();current=root_store().load();require(current['selected']==[])
            view=preflight.assess(current);proc=next(s for s in view['sources'] if s['id']=='proc_lifecycle');require(proc['preflight']=='eligible')
            draft=dict(assessment_id=view['assessment_id'],fingerprint=view['fingerprint'],confirmed=current,selected=['proc_lifecycle'])
            result=m.confirm(draft);results['confirmation_state']=result['states']['proc_lifecycle'];require(result['states']['proc_lifecycle']=='initialized_delivery_unproven')
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                state=json.loads(control.trusted(control.STATUS,4096,0o600))
                if state['state'] in ('stopped','failed'):break
                time.sleep(.05)
            require(state['state']=='stopped' and not state['forced'] and state['backend_exit']==0 and state['collector_exit']==0)
            results['owned_fixture_runtime']=True
            stopped=m.stop();require(stopped['proc_lifecycle']=='stopped');results['root_scoped_stop']=True
            current=root_store().load();view=preflight.assess(current)
            empty=m.confirm(dict(assessment_id=view['assessment_id'],fingerprint=view['fingerprint'],confirmed=current,selected=[]))
            require(empty['confirmed']['selected']==[]);results['final_saved_revision']=empty['confirmed']['revision']
        # Read as the actual DB owner. Opening WAL as root could create wrongly
        # owned sidecars; never do that for convenience.
        check="""import json,sqlite3,pathlib,os
p=pathlib.Path('/var/lib/hids/process/store.sqlite')
db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON')
rows=db.execute('SELECT envelope FROM process_events ORDER BY ordinal').fetchall();events=[json.loads(r[0]) for r in rows]
assert len(events)==3 and {e['native']['what'] for e in events}=={'PROC_EVENT_FORK','PROC_EVENT_EXEC','PROC_EVENT_EXIT'}
assert len({e['native']['tid'] for e in events})==1 and all(e['native']['tid']==e['native']['tgid'] for e in events)
assert all(e['timestamps']['activity_wall_time'] is None for e in events)
interval=db.execute('SELECT acknowledged,delivery,incomplete,stopped FROM process_intervals').fetchall();assert interval==[(0,1,0,1)]
db.close();print(json.dumps(dict(events=3,owned_child_only=True,activity_wall_time_absent=True,acknowledged=False,delivery=True,incomplete=False,stopped=True)))"""
        p=subprocess.run(control.role_command(backend,'/usr/bin/python3','-I','-B','-c',check),capture_output=True,text=True,timeout=5);require(p.returncode==0);results['private_store']=json.loads(p.stdout)
        require(all(digest(Path(p))==sha for p,sha in original.items()));results['prior_selection_revisions_preserved']=True
        # No new root activation grant remains, and the production binary is
        # unchanged. A unit start without fresh authority must fail before source.
        require(not control.GRANT.exists());require(digest(INSTALL/'process-collector')==cfg['binary_sha256'])
    finally:
        # Fixed private drop-in only, never evidence or prior config.
        (drop/'owned-fixture.conf').unlink();drop.rmdir();command('systemctl','daemon-reload')
    p=subprocess.run(['systemctl','start',control.UNIT],capture_output=True,text=True,timeout=10)
    require(p.returncode==0 or p.returncode==1)
    time.sleep(.2)
    require(command('systemctl','show',control.UNIT,'-p','ActiveState','--value')=='failed')
    command('systemctl','reset-failed',control.UNIT)
    results['restart_without_grant_refused']=True
    require(command('systemctl','show',control.UNIT,'-p','ActiveState','--value')=='inactive')
    require(root_store().load()['selected']==[] and manager.Ownership().load()['instances']=={})
    write(lab/'report.json',json.dumps(results,sort_keys=True).encode());print(json.dumps({'report':str(lab/'report.json'),'checks':results},sort_keys=True))

if __name__=='__main__':
    os.umask(0o077);p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    i=sub.add_parser('install');i.add_argument('source',type=Path);i.add_argument('manifest');i.add_argument('build',type=Path);i.add_argument('binary_sha');i.add_argument('trial_sha');sub.add_parser('accept');a=p.parse_args()
    if a.action=='install':install(a.source,a.manifest,a.build,a.binary_sha,a.trial_sha)
    else:accept()
