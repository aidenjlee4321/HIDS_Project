"""Explicit retained-data dashboard trial. No collection, rule work or publication."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
UNITS=['hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket']
PREP=r'''import json,os,sqlite3,sys
from pathlib import Path
p=Path('/var/lib/hids/process/store.sqlite');h=Path('/var/lib/hids/m4/store/handoff.sqlite');dbs=[];result={}
for name,path in [('process',p),('history',h)]:
 st=path.stat();assert st.st_uid==os.getuid() and st.st_mode&0o777==0o600
 db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=.05);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA busy_timeout=50');db.execute('BEGIN');db.execute('PRAGMA schema_version').fetchone();dbs.append(db)
 if name=='process':
  selected=[dict(source_id=s,activation_id=a) for s,a in db.execute('SELECT source_id,activation_id FROM process_events GROUP BY source_id,activation_id ORDER BY max(ordinal) DESC LIMIT 2')]
  events=[dict(event_id=k,envelope=json.loads(e),received_at=t,arrival_ordinal=str(o)) for k,e,t,o in db.execute('SELECT event_id,envelope,received_at,ordinal FROM process_events ORDER BY ordinal DESC LIMIT 128')]
  result[name]=dict(identity=[st.st_dev,st.st_ino],selected=selected,events=events)
 else:
  bindings=[r[0] for r in db.execute('SELECT binding_key FROM m4h_bindings ORDER BY binding_key LIMIT 3')];assert 1<=len(bindings)<=2
  result[name]=dict(identity=[st.st_dev,st.st_ino],bindings=bindings,events=db.execute('SELECT count(*) FROM m4h_events').fetchone()[0],findings=db.execute('SELECT count(*) FROM m4h_alerts').fetchone()[0],unevaluated=db.execute('SELECT count(*) FROM m4h_events e WHERE NOT EXISTS(SELECT 1 FROM m4h_evaluations v WHERE v.event_key=e.event_key)').fetchone()[0])
print(json.dumps(result),flush=True);sys.stdin.readline()
for db in dbs:db.execute('ROLLBACK');db.close()
'''


def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--browser-build',type=Path,required=True);p.add_argument('--tools',type=Path,required=True);a=p.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path.insert(0,str(ROOT/'scripts'));import dev;dev.verify(ROOT,a.expected_manifest)
 sys.path.insert(0,str(ROOT/'tests/integration'));import dashboard_pilot_ubuntu as lab
 lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 before=lab.preserved();assert before==json.loads(Path('/var/tmp/hids-dashboard-acceptance.4e_4n__z/baseline.json').read_text())
 root=Path(tempfile.mkdtemp(prefix='hids-combined-trial.',dir='/opt'));root.chmod(0o700)
 backend=pwd.getpwnam('hids-ingest');user=pwd.getpwnam('ivy');cfgpath=Path('/etc/hids/dashboard.json');install=Path('/opt/hids-dashboard')
 report=dict(result='running',source_manifest=a.expected_manifest,checks={});checks=report['checks'];created=[];prep=None;browser=None;loaded=False
 def run(cmd,**kw):return subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=30,**kw)
 def system(*args):return run(['/usr/bin/systemctl',*args])
 def hashes():
  return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for d in ('/var/lib/hids/process','/var/lib/hids/m4/store') for p in Path(d).iterdir() if p.is_file() and not p.name.endswith('-shm')}
 original=hashes()
 try:
  assert not cfgpath.exists()
  if install.exists():
   assert (install/'TRIAL_MARKER').read_text()=='hids-p01-combined-trial\n'
   install.rename(install.with_name('hids-dashboard-retained-'+root.name.split('.')[-1]))
  assert all(not Path('/run/systemd/system',n).exists() and not Path('/etc/systemd/system',n).exists() for n in UNITS)
  assert all(system('show',n,'-p','ActiveState','--value').stdout.strip()=='inactive' for n in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service'))
  install.mkdir(mode=0o755);(install/'TRIAL_MARKER').write_text('hids-p01-combined-trial\n');(install/'code').mkdir(mode=0o755)
  for folder in ('api','engine','shared','rules'):shutil.copytree(ROOT/folder,install/'code'/folder,ignore=shutil.ignore_patterns('__pycache__'))
  shutil.copytree(a.assets,install/'assets');(install/'venv').symlink_to('/opt/hids-dashboard-pilot/venv')
  for parent,dirs,files in os.walk(install):
   Path(parent).chmod(0o755)
   for name in files:Path(parent,name).chmod(0o644)
  sys.path.insert(0,str(install/'code'));from api.dashboard_tls import ensure_leaf
  leaf=ensure_leaf(backend.pw_gid);checks['valid_leaf_reused']=ensure_leaf(backend.pw_gid,leaf)==leaf
  cert=Path('/etc/hids/dashboard-tls')/leaf['tls_generation']/'leaf.pem'
  checks['ordinary_key_denied']=subprocess.run(['/usr/bin/test','-r',str(cert.with_name('leaf.key'))],user=user.pw_uid,group=user.pw_gid,extra_groups=[]).returncode!=0
  prep=subprocess.Popen(['/usr/bin/python3','-I','-B','-c',PREP],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'prep.stderr').open('x'),text=True,user=backend.pw_uid,group=backend.pw_gid,extra_groups=[],umask=0o077)
  meta=json.loads(prep.stdout.readline());(root/'ground-truth.json').write_text(json.dumps(meta));assert len(meta['process']['events'])==3 and meta['history']['events']==19 and meta['history']['unevaluated']==16
  cfg=dict(version=1,mode='frozen-dashboard',port=18765,process={k:meta['process'][k] for k in ('identity','selected')},history={k:meta['history'][k] for k in ('identity','bindings')},**leaf)
  fd=os.open(cfgpath,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o440)
  with os.fdopen(fd,'w') as f:json.dump(cfg,f);os.fchown(f.fileno(),0,backend.pw_gid);os.fchmod(f.fileno(),0o440)
  created.append(cfgpath)
  for name in UNITS:
   target=Path('/run/systemd/system',name);shutil.copyfile(ROOT/'packaging/systemd'/name,target);target.chmod(0o644);created.append(target)
  system('daemon-reload');system('start',*UNITS[1:],UNITS[0])
  time.sleep(.3)
  assert system('show',UNITS[0],'-p','ActiveState','--value').stdout.strip()=='active','dashboard service startup refused'
  ctx=ssl.create_default_context(cafile=str(cert))
  for _ in range(100):
   try:urllib.request.urlopen('https://127.0.0.1:18765/',context=ctx,timeout=1).read();break
   except Exception:time.sleep(.1)
  else:raise AssertionError('TLS listener unavailable')
  from api.dashboard_cli import request
  def http(path,token=None,method='GET',value=None):
   headers={'Sec-Fetch-Site':'same-origin'}
   if token:headers['Authorization']='Bearer '+token
   if value is not None:headers.update(Origin='https://127.0.0.1:18765',**{'Content-Type':'application/json'})
   req=urllib.request.Request('https://127.0.0.1:18765'+path,data=None if value is None else json.dumps(value).encode(),headers=headers,method=method)
   with urllib.request.urlopen(req,context=ctx,timeout=3) as r:return json.loads(r.read(65537))
  url=request('mint');auth=http('/v0/auth/redeem',method='POST',value=dict(grant=url.split('#grant=')[1]));token=auth['token'];assert auth['scope']=='dashboard:read'
  summary=http('/v0/dashboard',token);checks['actual_family_counts']=summary['process']['snapshot']['counts']['events']==3 and summary['history']['snapshot']['counts']['events']==19 and summary['history']['snapshot']['counts']['unevaluated']==16
  checks['all_process_fields_match']=all(all(http('/v0/process/events/'+e['event_id'],token)[k]==v for k,v in e.items()) for e in meta['process']['events'])
  http('/v0/auth/logout',token,'POST',{})
  pid=int(system('show',UNITS[0],'-p','MainPID','--value').stdout);status=Path(f'/proc/{pid}/status').read_text()
  checks['backend_zero_capabilities']=f'Uid:\t{backend.pw_uid}\t{backend.pw_uid}\t{backend.pw_uid}\t{backend.pw_uid}' in status and all(f'{cap}:\t0000000000000000' in status for cap in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
  fds=[]
  for fd in Path(f'/proc/{pid}/fd').iterdir():
   try:fds.append(os.readlink(fd))
   except FileNotFoundError:pass
  checks['no_database_connection_while_serving']=not any('store.sqlite' in f or 'handoff.sqlite' in f for f in fds)
  checks['unrelated_paths_hidden']=not Path(f'/proc/{pid}/root/var/lib/hids/m3').exists() and not Path(f'/proc/{pid}/root/etc/hids/process.json').exists()
  prep.stdin.close();prep.wait(timeout=5);assert prep.returncode==0;prep=None
  again=http('/v0/auth/redeem',method='POST',value=dict(grant=request('mint').split('#grant=')[1]))['token']
  checks['snapshot_survives_preparation_close']=http('/v0/dashboard',again)['process']['snapshot']['counts']['events']==3
  http('/v0/auth/logout',again,'POST',{})
  # The fixture preparation is closed before the browser begins; the serving
  # process itself has already closed both SQLite families.
  browserroot=Path('/opt/hids-browser-leaf.940b2j6b/browser');binary=browserroot/'chrome'
  assert hashlib.sha256(binary.read_bytes()).hexdigest()=='40c121f803bd7f2c3dc394a12f064d14af1faea4baf7938dd2a8edd5175086f6'
  profile_name='hids-combined-'+root.name.split('.')[-1].replace('_','x');profile=root/'apparmor.profile';profile.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile '+profile_name+' '+str(binary)+' flags=(unconfined) {\n userns,\n}\n');run(['/usr/sbin/apparmor_parser','--skip-cache','--replace',str(profile)]);loaded=True
  work=Path(tempfile.mkdtemp(prefix='combined-browser.',dir=a.browser_build));os.chown(work,user.pw_uid,user.pw_gid);work.chmod(0o700)
  shutil.copyfile(cert,work/'leaf.pem');os.chown(work/'leaf.pem',user.pw_uid,user.pw_gid);(work/'leaf.pem').chmod(0o600)
  browser=subprocess.Popen([str(a.browser_build/'venv/bin/python'),'-B',str(ROOT/'tests/integration/combined_dashboard_browser.py'),str(work),str(a.tools),str(binary)],stdin=subprocess.PIPE,stdout=(root/'browser.stdout').open('x'),stderr=(root/'browser.stderr').open('x'),text=True,user=user.pw_uid,group=user.pw_gid,extra_groups=[],env=dict(os.environ,PLAYWRIGHT_BROWSERS_PATH=str(a.browser_build/'browsers')))
  browser.communicate(json.dumps(dict(url=request('mint'),counts=dict(process=3,history=19,findings=1)))+'\n',timeout=60)
  result=json.loads((work/'report.json').read_text());report['browser_report']=str(work/'report.json');report['browser_checks']=result['checks'];checks['browser_acceptance']=browser.returncode==0 and result['passed']
  request('revoke_all');dev.verify(ROOT,a.expected_manifest)
 except Exception as e:
  report['error_type']=type(e).__name__
  import traceback;(root/'failure.txt').write_text(traceback.format_exc())
 finally:
  if browser and browser.poll() is None:browser.terminate();browser.wait(timeout=8)
  if prep:
   prep.stdin.close();prep.wait(timeout=5)
  subprocess.run(['/usr/bin/systemctl','stop',*UNITS],capture_output=True,timeout=20)
  subprocess.run(['/usr/bin/systemctl','reset-failed',*UNITS],capture_output=True,timeout=10)
  if loaded:checks['temporary_browser_policy_removed']=subprocess.run(['/usr/sbin/apparmor_parser','--skip-cache','--remove',str(profile)],capture_output=True).returncode==0
  for path in reversed(created):path.unlink()
  subprocess.run(['/usr/bin/systemctl','daemon-reload'],capture_output=True,timeout=15)
  checks['original_state_preserved']=lab.preserved()==before
  checks['main_wal_bytes_preserved']=all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in original.items())
  checks['no_collection_started']=all(system('show',n,'-p','ActiveState','--value').stdout.strip()=='inactive' for n in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service'))
  report['result']='passed' if checks and all(checks.values()) and 'error_type' not in report else 'failed'
  (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(root/'report.json'),checks=checks,error_type=report.get('error_type'))))
 return 0 if report['result']=='passed' else 1
if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
