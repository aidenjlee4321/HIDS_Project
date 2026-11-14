"""Explicit root-only synthetic M4 service-account/read-only sandbox acceptance.

Run from a verified source snapshot. Never deploys or opens production HIDS data.
Original paths are hidden in the worker mount namespace. All artifacts retained.
"""
import argparse
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
import dev

PRODUCER='''import sys,json
from pathlib import Path
from engine.ingestion.m3_runtime import Runtime
from engine.ingestion.m3_event import ARCH,PROFILE
from engine.detection.m4_pilot import load_json
from engine.ingestion import m3_storage
root=Path(sys.argv[1]);scope=json.loads(sys.argv[2]);p=m3_storage.defaults(512,4)
p.update(warning_free_bytes=4*1024**2,critical_free_bytes=2*1024**2,minimum_free_bytes=1024**2)
r=Runtime(root/'source',scope['source'],max_activations=4,max_pages=512,position_limit=1024,storage=p)
scope['generation']=r.activate(scope['activation'])['generation']
e=load_json(Path.cwd()/'tests/fixtures/m4/execution.json')['execution']
for n in (1,2):r.progress.register('1.001:'+str(n),(n-1)*10,n*10,eoe=True)
obs=dict(version=1,arch=ARCH,profile=PROFILE,first_observed_unix_ns=123)
r.progress.accept('1.001:2',e,observation=obs)
print(json.dumps(scope),flush=True)
try:
 for line in sys.stdin:
  command=json.loads(line)['command']
  if command=='accept_a':r.progress.accept('1.001:1',e,observation=obs);print('{"accepted":true}',flush=True)
  elif command=='stop':break
  else:raise ValueError('unknown synthetic producer command')
finally:r.close()
'''


def command(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=30)
def receive(stream):
    if not select.select([stream],[],[],20)[0]:raise RuntimeError('producer timeout')
    line=stream.readline()
    if not line:raise RuntimeError('producer exited')
    return json.loads(line)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-manifest',required=True)
    args=parser.parse_args()
    if sys.platform!='linux' or os.getuid()!=0:raise RuntimeError('authorized Ubuntu VM root required')
    dev.verify(ROOT,args.expected_manifest)
    units=('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')
    if any(command('systemctl','show',u,'-p','ActiveState','--value').strip()!='inactive' for u in units):raise RuntimeError('original M3 units must already be inactive')
    if command('systemctl','show','auditd','-p','ActiveState','--value').strip()!='active':raise RuntimeError('Audit must already be active')
    lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    account=pwd.getpwnam('hids-ingest')
    root=Path(tempfile.mkdtemp(prefix='hids-m4-handoff.',dir='/var/tmp'));root.chmod(0o711)
    report=dict(lab_only=True,result='running',source_manifest=args.expected_manifest,root=str(root),runs=[])
    child=None;unit=None
    def save():
        path=root/'report.json';path.write_text(json.dumps(report,sort_keys=True)+'\n');path.chmod(0o600)
    try:
        code=root/ROOT.name;shutil.copytree(ROOT,code)
        for parent,dirs,files in os.walk(code):
            Path(parent).chmod(0o755)
            for name in files:(Path(parent)/name).chmod(0o644)
        dev.verify(code,args.expected_manifest)
        for name in ('source','state'):
            p=root/name;p.mkdir(mode=0o700);os.chown(p,account.pw_uid,account.pw_gid)
        scope=dict(source=str(uuid.uuid4()),activation=str(uuid.uuid4()))
        stderr=(root/'producer.stderr').open('x');os.chmod(stderr.name,0o600)
        child=subprocess.Popen([sys.executable,'-B','-c',PRODUCER,str(root),json.dumps(scope)],cwd=code,
            env={**os.environ,'PYTHONPATH':str(code),'PYTHONDONTWRITEBYTECODE':'1'},user=account.pw_uid,group=account.pw_gid,extra_groups=[],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,start_new_session=True)
        scope=receive(child.stdout)
        from engine.ingestion import m3_storage
        policy=m3_storage.defaults(64,1);policy.update(warning_free_bytes=4*1024**2,critical_free_bytes=2*1024**2,minimum_free_bytes=1024**2)
        config=root/'config.json';config.write_text(json.dumps(dict(version=1,lab_only=True,**scope,max_pages=64,storage=policy)))
        os.chown(config,0,account.pw_gid);config.chmod(0o640)
        properties=dict(User='hids-ingest',Group='hids-ingest',SupplementaryGroups='',WorkingDirectory=str(code),
            UMask='0077',NoNewPrivileges='yes',CapabilityBoundingSet='',AmbientCapabilities='',ProtectSystem='strict',ProtectHome='yes',
            PrivateDevices='yes',ProtectKernelTunables='yes',ProtectKernelModules='yes',ProtectControlGroups='yes',
            RestrictSUIDSGID='yes',RestrictAddressFamilies='AF_UNIX',LimitCORE='0',
            ReadOnlyPaths=str(root/'source'),ReadWritePaths=str(root/'state'),
            InaccessiblePaths='/var/lib/hids/m3 /run/hids/m3')
        report['properties']=properties
        def run():
            nonlocal unit
            unit='hids-m4-handoff-lab-'+uuid.uuid4().hex[:12]
            argv=['systemd-run','--quiet','--wait','--collect','--pipe','--unit',unit]
            for key,value in properties.items():argv+=['--property',key+'='+value]
            argv+=[sys.executable,'-B','-m','engine.detection.m4_handoff_worker','--lab-config',str(config),'--once']
            result=subprocess.run(argv,text=True,capture_output=True,timeout=30)
            out=root/('worker-'+str(len(report['runs']))+'.stdout');out.write_text(result.stdout);out.chmod(0o600)
            err=out.with_suffix('.stderr');err.write_text(result.stderr);err.chmod(0o600)
            if result.returncode:raise RuntimeError('worker failed; private log '+str(err))
            status=json.loads(result.stdout.strip().splitlines()[-1])
            assert all(status['isolation'].values())
            report['runs'].append(status);save();unit=None
            return status
        first=run();assert first['events']==1 and first['unevaluated']==1 and first['alerts']==0
        child.stdin.write('{"command":"accept_a"}\n');child.stdin.flush();assert receive(child.stdout)==dict(accepted=True)
        second=run();assert second['events']==1  # End first sweep at captured frontier 0.
        third=run();assert third['events']==2 and third['unevaluated']==2
        fourth=run();assert fourth['events']==2 and fourth['alerts']==0
        child.stdin.write('{"command":"stop"}\n');child.stdin.flush();child.wait(timeout=15);assert child.returncode==0
        report.update(result='passed',late_A_preserved=True,source_readonly=True,production_paths_hidden=True,
                      actual_uid=account.pw_uid,worker_restarts=4,demo_rules_enabled=False)
    finally:
        if unit:
            subprocess.run(['systemctl','stop',unit],capture_output=True,timeout=20)
        if child and child.poll() is None:
            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15)
        if child:
            child.stdin.close();child.stdout.close()
        if 'stderr' in locals():stderr.close()
        report['original_units_inactive']=all(command('systemctl','show',u,'-p','ActiveState','--value').strip()=='inactive' for u in units)
        report['audit_active']=command('systemctl','show','auditd','-p','ActiveState','--value').strip()=='active'
        if report['result']!='passed':report['result']='failed'
        save();os.close(lock)
        print('Private sandbox report '+str(root/'report.json'),flush=True)
    assert report['original_units_inactive'] and report['audit_active']
    print(json.dumps(dict(result='passed',report=str(root/'report.json'),worker_restarts=4,events=2,alerts=0,source_readonly=True),sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
