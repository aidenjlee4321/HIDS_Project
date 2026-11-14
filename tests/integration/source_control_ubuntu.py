"""Pinned source-free control acceptance: synthetic grants and systemd workers."""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

def system(*args):return subprocess.check_output(['systemctl',*args],text=True,timeout=20).strip()
def wait_state(path,activation):
 deadline=time.monotonic()+5
 while time.monotonic()<deadline:
  try:
   value=json.loads(path.read_text())
   if value['activation']==activation and value['state']=='initialized_delivery_unproven':return value
  except (FileNotFoundError,ValueError):pass
  time.sleep(.02)
 raise AssertionError('synthetic worker did not initialize')

def main():
 a=argparse.ArgumentParser();a.add_argument('--expected-manifest',required=True);args=a.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests/integration')]
 import dev;dev.verify(ROOT,args.expected_manifest)
 import dashboard_pilot_ubuntu as lab
 from api import setup_manager as m
 from api.setup_store import _Store
 from api.setup_contract import canonical
 from api.pilot_sessions import Denied
 from engine.ingestion import process_control as p
 original=lab.preserved();work=Path(tempfile.mkdtemp(prefix='hids-source-control.',dir='/opt'));work.chmod(0o755)
 runtime=work/'runtime';runtime.mkdir(mode=0o750);runtime.chmod(0o750);os.chown(runtime,0,pwd.getpwnam('hids-process').pw_gid)
 setup=work/'setup';setup.mkdir(mode=0o700)
 prefs=work/'preferences';prefs.mkdir(mode=0o750);prefs.chmod(0o750);os.chown(prefs,0,pwd.getpwnam('hids-ingest').pw_gid)
 code=work/'code';(code/'engine/ingestion').mkdir(parents=True)
 for name in ('engine/ingestion/process_control.py','engine/ingestion/process_contract.py','engine/ingestion/m1_contract.py'):
  shutil.copyfile(ROOT/name,code/name)
 for parent,dirs,files in os.walk(code):
  Path(parent).chmod(0o755)
  for name in files:Path(parent,name).chmod(0o644)
 names=tuple('hids-control-test-'+uuid.uuid4().hex+'.service' for _ in range(4));created=[]
 entry=dict(source=str(uuid.uuid4()),activation=str(uuid.uuid4()),generation=str(uuid.uuid4()),state='initialization_unconfirmed')
 report=dict(result='running',checks={},source_manifest=args.expected_manifest);checks=report['checks']
 worker=work/'worker.py'
 worker.write_text('''import sys,os,fcntl,signal,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from engine.ingestion import process_control as p
p.RUNTIME=Path(sys.argv[2]);p.STATUS=p.RUNTIME/'status.json';p.GRANT=p.RUNTIME/'next-start.json'
fd=os.open(p.RUNTIME/'owner.lock',os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
v=p.c.decode(p.trusted(p.GRANT,4096,0o600));p.GRANT.unlink()
s=dict(version=1,source=v['source_id'],activation=v['activation_id'],generation=v['generation'],state='initialized_delivery_unproven',backend_exit=None,collector_exit=None)
stop=[False];signal.signal(signal.SIGTERM,lambda *_:stop.__setitem__(0,True));p.publish(s)
while not stop[0]:time.sleep(.02)
s.update(state='stopped',forced=False,backend_exit=0,collector_exit=0);p.publish(s)
''');worker.chmod(0o644)
 try:
  for index,name in enumerate(names):
   path=Path('/run/systemd/system')/name;assert not path.exists()
   command='/usr/bin/python3 -I -B '+str(worker)+' '+str(code)+' '+str(runtime) if index==0 else '/usr/bin/sleep 300'
   path.write_text('[Service]\nType=simple\nExecStart='+command+'\nRestart=no\nNoNewPrivileges=yes\nCapabilityBoundingSet=CAP_CHOWN\nPrivateNetwork=yes\nProtectSystem=strict\nProtectHome=yes\nReadWritePaths='+str(runtime)+'\n');path.chmod(0o644);created.append(path)
  system('daemon-reload')
  def unit(name):
   assert name in names
   return dict(ActiveState=system('show',name,'-p','ActiveState','--value'))
  with patch.object(p,'RUNTIME',runtime),patch.object(p,'GRANT',runtime/'next-start.json'),patch.object(p,'STATUS',runtime/'status.json'),patch.object(p,'UNIT',names[0]),patch.object(p,'PARTS',names[1:]),patch.object(m,'RUNTIME',setup),patch.object(m.setup_preflight,'unit',side_effect=unit):
   store=_Store(prefs,0,pwd.getpwnam('hids-ingest').pw_gid);record=store.save(['proc_lifecycle'],0);saved=(prefs/'selection-0001.json').read_bytes()
   ownership=m.Ownership();adapter=m.ProcessAdapter();manager=m._Manager(store,ownership,None,{'proc_lifecycle':adapter})
   def journal(value):ownership.write(dict(version=1,revision=record['revision'],instances={'proc_lifecycle':dict(value)}))
   def grant(value):p.write_new(p.GRANT,dict(version=1,source_id=value['source'],activation_id=value['activation'],generation=value['generation'],expires=time.monotonic()+30))
   journal(entry);grant(entry)
   with m.root_lock():answer=manager.stop()
   checks['missing_status_pending_grant_cancelled']=answer=={'proc_lifecycle':'stopped'} and not p.GRANT.exists() and not p.STATUS.exists()
   system('start',names[0]) # No grant: the test worker must fail before publishing.
   deadline=time.monotonic()+5
   while unit(names[0])['ActiveState']!='failed':
    assert time.monotonic()<deadline;time.sleep(.02)
   journal(entry);grant(entry)
   with m.root_lock():answer=manager.stop()
   checks['failed_unit_grant_revoked_without_claiming_stop']=answer=={'proc_lifecycle':'stop_unconfirmed'} and not p.GRANT.exists()
   system('reset-failed',names[0])
   foreign=dict(entry,activation=str(uuid.uuid4()));grant(foreign);before=p.GRANT.read_bytes()
   try:adapter.cancel_pending(entry)
   except Denied:pass
   else:raise AssertionError('foreign authorization removed')
   checks['foreign_grant_unchanged']=p.GRANT.read_bytes()==before
   p.GRANT.rename(work/'foreign-grant-retained.json') # retain test input outside active grant path
   grant(entry);system('start',names[0]);bound=wait_state(p.STATUS,entry['activation']);scope=p.runtime_scope()
   checks['v2_actual_invocation_binding']=bound['version']==2 and bound['runtime_pid']==scope['MainPID'] and bound['runtime_invocation']==scope['InvocationID']
   journal(dict(entry,state='initialized_delivery_unproven'))
   with m.root_lock():answer=manager.stop()
   checks['owned_live_runtime_stopped_by_pidfd']=answer=={'proc_lifecycle':'stopped'} and unit(names[0])['ActiveState']=='inactive'
   terminal=p.STATUS.read_bytes()
   grant(foreign);system('start',names[0]);wait_state(p.STATUS,foreign['activation']);live=p.runtime_scope()
   p.write_new(runtime/'stale.pending',json.loads(terminal));os.replace(runtime/'stale.pending',p.STATUS)
   try:adapter.stop(entry)
   except Denied:pass
   else:raise AssertionError('foreign live invocation accepted')
   checks['stale_status_never_signals_foreign_runtime']=p.runtime_scope()==live
   system('stop',names[0]);p.write_new(runtime/'terminal.pending',json.loads(terminal));os.replace(runtime/'terminal.pending',p.STATUS)
   system('start',names[1]);part=system('show',names[1],'-p','MainPID','--value');journal(entry)
   with m.root_lock():answer=manager.stop()
   checks['unknown_active_part_not_stopped']=answer=={'proc_lifecycle':'stop_unconfirmed'} and unit(names[1])['ActiveState']=='active' and system('show',names[1],'-p','MainPID','--value')==part
   system('stop',names[1]);checks['selection_bytes_unchanged']=(prefs/'selection-0001.json').read_bytes()==saved
   dev.verify(ROOT,args.expected_manifest)
 except BaseException as exc:
  report['error_type']=type(exc).__name__
  import traceback;(work/'failure.txt').write_text(traceback.format_exc())
 finally:
  subprocess.run(['systemctl','stop',*names],capture_output=True,timeout=20)
  subprocess.run(['systemctl','reset-failed',*names],capture_output=True,timeout=10)
  for path in created:path.unlink()
  system('daemon-reload');checks['original_state_preserved']=lab.preserved()==original
  checks['production_sources_stopped']=all(system('show',u,'-p','ActiveState','--value')=='inactive' for u in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket','hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket'))
  report['result']='passed' if checks and all(checks.values()) and 'error_type' not in report else 'failed'
  work.chmod(0o700);(work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(work/'report.json'),checks=checks,error_type=report.get('error_type'))))
 return int(report['result']!='passed')

if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
