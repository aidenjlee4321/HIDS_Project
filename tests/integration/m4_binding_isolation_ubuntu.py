"""Two explicitly selected synthetic bindings: failure/backoff/recovery isolation.

Actual M4 fixed paths are mount-aliased to private fixtures; no live collection,
production state mutation, configuration expansion or automatic history import.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests/integration')]
import dev
from m4_handoff_ubuntu import receive

PRODUCER='''import sys,json,sqlite3,uuid,hashlib
from pathlib import Path
from engine.ingestion.m3_runtime import Runtime
from engine.ingestion.m3_event import ARCH,PROFILE
from engine.ingestion import m3_storage
from engine.detection.m4_pilot import load_json
root=Path(sys.argv[1]);source=str(uuid.uuid4())
r=Runtime(root/'source',source,max_activations=4,max_pages=512,position_limit=1024,storage=m3_storage.defaults(512,4))
e=load_json(Path.cwd()/'tests/fixtures/m4/execution.json')['execution'];e.update(euid=0,exe_base64='L3Vzci9iaW4vZGFzaA==')
obs=dict(version=1,arch=ARCH,profile=PROFILE,first_observed_unix_ns=123)
first=str(uuid.uuid4());a=r.activate(first);r.progress.register('1.001:1',0,10,eoe=True);r.progress.accept('1.001:1',e,observation=obs)
a_db=sqlite3.connect(root/'source'/(first+'.sqlite'),isolation_level=None)
row=a_db.execute('SELECT * FROM m3_event_metadata WHERE identity=?',('1.001:1',)).fetchone();assert row
r.revoke(first)
a_path=root/'source'/(first+'.sqlite');before_bytes=hashlib.sha256(a_path.read_bytes()).hexdigest();a_path.chmod(0o000)
second=str(uuid.uuid4());b=r.activate(second);r.progress.register('1.001:1',0,10,eoe=True);r.progress.accept('1.001:1',e,observation=obs)
scopes=[dict(source=source,activation=first,generation=a['generation']),dict(source=source,activation=second,generation=b['generation'])]
print(json.dumps(dict(stage='ready',scopes=scopes)),flush=True)
try:
 for line in sys.stdin:
  command=json.loads(line)['command']
  if command=='add_b':
   for n in (2,3):
    identity='1.001:'+str(n);r.progress.register(identity,(n-1)*10,n*10,eoe=True);r.progress.accept(identity,e,observation=obs)
   print('{"stage":"b_added"}',flush=True)
  elif command=='repair_a':
   a_path.chmod(0o600)
   assert hashlib.sha256(a_path.read_bytes()).hexdigest()==before_bytes
   assert a_db.execute('SELECT * FROM m3_event_metadata WHERE identity=?',('1.001:1',)).fetchone()==row
   print('{"stage":"a_repaired","main_bytes_unchanged":true}',flush=True)
  elif command=='stop':break
  else:raise ValueError('invalid fixture coordination')
finally:a_db.close();r.close()
'''

WORKER='''import sys,json,os
from pathlib import Path
from engine.detection.m4_live import LiveSource
from engine.detection.m4_rule_store import RuleStore
from engine.detection.m4_rules import load_rules,REFERENCE
from engine.detection.m4_handoff import Worker
from engine.detection.m4_service import isolation_probe
root=Path(sys.argv[1]);scopes=json.loads(sys.argv[2])
assert root.parent==Path('/var/tmp') and root.name.startswith('hids-m4-bindings.')
assert Path('/var/lib/hids/m3').samefile(root/'source') and Path('/var/lib/hids/m4').samefile(root/'state')
sources=[LiveSource(Path('/var/lib/hids/m3'),**s) for s in scopes]
isolation=isolation_probe(sources[1]);calls={s.key:0 for s in sources}
for s in sources:
 original=s.read_page
 def counted(*args,_source=s,_read=original,**kwargs):
  calls[_source.key]+=1;return _read(*args,**kwargs)
 s.read_page=counted
clock=[0.0]
with RuleStore(create=True) as store:
 rules=load_rules([REFERENCE]);worker=Worker(store,sources,rules,clock=lambda:clock[0],page_limit=1)
 print(json.dumps(dict(stage='ready',uid=os.getuid(),groups=os.getgroups(),isolation=isolation)),flush=True)
 for line in sys.stdin:
  command=json.loads(line)['command']
  if command=='stop':break
  assert command in ('step','advance')
  if command=='advance':clock[0]=3.0
  result=worker.step()
  print(json.dumps(dict(stage='step',status=result,calls=calls,source_keys=[s.key for s in sources],clock=clock[0])),flush=True)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expected-manifest',required=True);parser.add_argument('--expected-vm-uuid',required=True);args=parser.parse_args()
    assert sys.platform=='linux' and os.getuid()==0
    expected=str(uuid.UUID(args.expected_vm_uuid))
    if Path('/sys/class/dmi/id/product_uuid').read_text().strip()!=expected:raise RuntimeError('VM identity differs; no experiment started')
    dev.verify(ROOT,args.expected_manifest)
    def command(*a):return subprocess.check_output(a,text=True,timeout=20).strip()
    units=('hids-m3.service','hids-m3.socket','hids-m3-health.service','hids-m3-health.timer')
    assert all(command('systemctl','show',u,'-p','ActiveState','--value')=='inactive' for u in units) and command('systemctl','is-active','auditd')=='active'
    lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def preserved():
        paths=[*Path('/var/lib/hids/m3').glob('*.sqlite'),*Path('/var/lib/hids/m4').rglob('*.sqlite'),Path('/etc/hids/m3.json'),Path('/etc/audit/auditd.conf'),*Path('/etc/audit/plugins.d').glob('*.conf')]
        return dict(files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},rules=command('auditctl','-l'))
    baseline=preserved();root=Path(tempfile.mkdtemp(prefix='hids-m4-bindings.',dir='/var/tmp'));root.chmod(0o711)
    report=dict(result='running',lab_only=True,vm_uuid=expected,source_manifest=args.expected_manifest,steps=[])
    processes=[];logs=[];unit=None
    def save():
        p=root/'report.json';p.write_text(json.dumps(report,sort_keys=True)+'\n');p.chmod(0o600)
    def log(name):
        p=root/name;f=p.open('x');p.chmod(0o600);logs.append(f);return f
    def send(stream,value):stream.write(json.dumps(value)+'\n');stream.flush()
    def finish(p):
        send(p.stdin,dict(command='stop'));p.wait(timeout=10);assert p.returncode==0
        p.stdin.close();p.stdout.close();processes.remove(p)
    try:
        code=root/ROOT.name;shutil.copytree(ROOT,code)
        for parent,dirs,files in os.walk(code):
            Path(parent).chmod(0o755)
            for n in files:(Path(parent)/n).chmod(0o644)
        dev.verify(code,args.expected_manifest)
        a=pwd.getpwnam('hids-ingest')
        for name in ('source','state'):
            p=root/name;p.mkdir(mode=0o700);os.chown(p,a.pw_uid,a.pw_gid)
        producer=subprocess.Popen([sys.executable,'-B','-c',PRODUCER,str(root)],cwd=code,user=a.pw_uid,group=a.pw_gid,extra_groups=[],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log('producer.stderr'),text=True)
        processes.append(producer);ready=receive(producer.stdout);assert ready['stage']=='ready';scopes=ready['scopes']
        report['selected_scopes']=scopes;save()
        unit='hids-m4-bindings-'+uuid.uuid4().hex[:12]
        properties=dict(User='hids-ingest',Group='hids-ingest',SupplementaryGroups='',WorkingDirectory=str(code),UMask='0077',NoNewPrivileges='yes',
            CapabilityBoundingSet='',AmbientCapabilities='',ProtectSystem='strict',ProtectHome='yes',PrivateDevices='yes',ProtectKernelTunables='yes',
            ProtectKernelModules='yes',ProtectControlGroups='yes',RestrictSUIDSGID='yes',RestrictAddressFamilies='AF_UNIX',LimitCORE='0',
            BindReadOnlyPaths=str(root/'source')+':/var/lib/hids/m3',BindPaths=str(root/'state')+':/var/lib/hids/m4',
            ReadOnlyPaths='/var/lib/hids/m3',ReadWritePaths='/var/lib/hids/m4',InaccessiblePaths='/run/hids/m3',RuntimeMaxSec='60')
        argv=['systemd-run','--quiet','--wait','--collect','--pipe','--unit',unit]
        for k,v in properties.items():argv+=['-p',k+'='+v]
        argv+=[sys.executable,'-B','-c',WORKER,str(root),json.dumps(scopes)]
        worker=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log('worker.stderr'),text=True)
        processes.append(worker);ready=receive(worker.stdout);assert ready['stage']=='ready' and ready['uid']==a.pw_uid and set(ready['groups'])<={a.pw_gid} and all(ready['isolation'].values())
        report['identity']=ready
        def step(kind):
            send(worker.stdin,dict(command=kind));value=receive(worker.stdout);assert value['stage']=='step';report['steps'].append(value);save();return value
        first=step('step');ak,bk=first['source_keys']
        assert first['status']['bindings']=={ak:'source_invalid',bk:'imported'} and first['status']['events']==first['status']['alerts']==1
        send(producer.stdin,dict(command='add_b'));assert receive(producer.stdout)['stage']=='b_added'
        second=step('step');assert second['calls'][ak]==first['calls'][ak]==1
        assert second['status']['bindings'][ak]=='source_invalid' and second['status']['events']==second['status']['alerts']==2
        send(producer.stdin,dict(command='repair_a'));assert receive(producer.stdout)['stage']=='a_repaired'
        third=step('advance');assert third['calls'][ak]==2 and third['status']['bindings'][ak]=='imported' and set(third['status']['bindings'].values())<={'imported','idle'}
        assert third['status']['events']==third['status']['alerts']==4 and third['status']['pending']==0
        fourth=step('step');assert fourth['status']['events']==fourth['status']['alerts']==4
        for _ in range(6):
            repeated=step('step');assert repeated['status']['events']==repeated['status']['alerts']==4
        assert set(repeated['status']['bindings'].values())=={'idle'}
        finish(worker);unit=None;finish(producer)
        report.update(result='passed',failed_binding_isolated=True,backoff_skips_only_failed_binding=True,repair_detected=True,native_identity_scoped=True,paginated_backlog=True,events=4,findings=4)
        dev.verify(code,args.expected_manifest)
    finally:
        for p in processes:
            if p.poll() is None:p.kill();p.wait(timeout=10)
            p.stdin.close();p.stdout.close()
        if unit:subprocess.run(['systemctl','stop',unit],capture_output=True,timeout=20)
        for f in logs:f.close()
        report['production_preserved']=preserved()==baseline
        report['original_units_inactive']=all(command('systemctl','show',u,'-p','ActiveState','--value')=='inactive' for u in units)
        if report['result']!='passed' or not report['production_preserved'] or not report['original_units_inactive']:report['result']='failed'
        save();os.close(lock)
        print(json.dumps(dict(result=report['result'],report=str(root/'report.json'),production_preserved=report['production_preserved'])),flush=True)
    assert report['result']=='passed'


if __name__=='__main__':main()
