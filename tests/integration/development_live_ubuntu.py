"""Pinned installed-build acceptance: one owned-child source interval and viewer.

Uses a verified acceptance-only collector drop-in, never modifies the production
binary. Retains new events and selection revisions; preserves prior rows/policy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
SOURCES=('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket')
VIEWER=('hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket')
def system(*args):return subprocess.check_output(['systemctl',*args],text=True,timeout=20).strip()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--expected-manifest',required=True);a.add_argument('--trial',type=Path,required=True);a.add_argument('--trial-sha256',required=True);a.add_argument('--browser-python',type=Path,required=True);a.add_argument('--viewer-only',action='store_true');args=a.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests/integration')]
 import dev,dashboard_pilot_ubuntu as lab
 dev.verify(ROOT,args.expected_manifest)
 sys.path.insert(0,'/opt/hids-dashboard/code')
 from api import setup_manager as manager,setup_preflight as preflight,dashboard_launch as launch
 from api.setup_store import root_store
 from api.dashboard_cli import request
 from engine.ingestion import process_control as control
 assert all(system('show',u,'-p','ActiveState','--value')=='inactive' for u in (*SOURCES,*VIEWER))
 baseline=lab.preserved();work=Path(tempfile.mkdtemp(prefix='hids-release-live.',dir='/opt'));work.chmod(0o700)
 report=dict(result='running',checks={},source_manifest=args.expected_manifest,mode='viewer_only' if args.viewer_only else 'native_and_viewer');checks=report['checks'];drop=Path('/run/systemd/system/hids-process-collector.service.d');created=False;browser=None;policy=None;loaded=False
 backend=pwd.getpwnam('hids-ingest');user=pwd.getpwnam('ivy');binary=Path('/opt/hids-process-pipeline/process-collector');binary_before=sha(binary)
 def owner_read():
  code="""import sqlite3,json,hashlib
c=sqlite3.connect('file:/var/lib/hids/process/store.sqlite?mode=ro&immutable=1',uri=True);c.execute('PRAGMA query_only=ON')
r=dict(events={k:hashlib.sha256(e.encode()).hexdigest() for k,e in c.execute('SELECT event_id,envelope FROM process_events')},intervals=c.execute('SELECT acknowledged,delivery,incomplete,stopped FROM process_intervals').fetchall(),integrity=c.execute('PRAGMA quick_check').fetchone()[0]);c.close();print(json.dumps(r))"""
  p=subprocess.run(control.role_command(backend,'/usr/bin/python3','-I','-B','-c',code),capture_output=True,text=True,timeout=5);assert p.returncode==0;return json.loads(p.stdout)
 old=owner_read();oldchoices={str(p):sha(p) for p in Path('/etc/hids/setup').glob('selection-*.json')}
 profiles=Path('/sys/kernel/security/apparmor/profiles');oldprofiles=set(profiles.read_text().splitlines())
 try:
  subprocess.run([str(args.browser_python),'-I','-B','-c','import playwright.sync_api'],capture_output=True,check=True,timeout=10,user=user.pw_uid,group=user.pw_gid,extra_groups=[])
  after=old
  if not args.viewer_only:
   assert not drop.exists() and sha(args.trial)==args.trial_sha256
   trialdir=Path(tempfile.mkdtemp(prefix='hids-release-owned.',dir='/opt'));trialdir.chmod(0o755)
   trial=trialdir/'process-owned-trial';shutil.copyfile(args.trial,trial);trial.chmod(0o555);report['trial_binary']=str(trial)
   drop.mkdir(mode=0o755);drop.chmod(0o755);created=True
   (drop/'owned-child.conf').write_text('[Service]\nExecStart=\nExecStart='+str(trial)+' /run/hids/process/current.json\n');(drop/'owned-child.conf').chmod(0o644);system('daemon-reload')
   with manager.root_lock():
    m=manager.manager();current=root_store().load();assert current['selected']==[]
    view=preflight.assess(current);assert next(s for s in view['sources'] if s['id']=='proc_lifecycle')['preflight']=='eligible'
    answer=m.confirm(dict(assessment_id=view['assessment_id'],fingerprint=view['fingerprint'],confirmed=current,selected=['proc_lifecycle']))
    checks['explicit_root_initialization']=answer['states']['proc_lifecycle']=='initialized_delivery_unproven';assert checks['explicit_root_initialization']
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
     state=json.loads(control.trusted(control.STATUS,4096,0o600))
     if state['state'] in ('stopped','failed'):break
     time.sleep(.02)
    checks['native_owned_interval_clean_stop']=state['version']==2 and state['state']=='stopped' and not state['forced'] and state['backend_exit']==state['collector_exit']==0
    checks['explicit_owned_stop']=m.stop()=={'proc_lifecycle':'stopped'}
    current=root_store().load();view=preflight.assess(current);m.confirm(dict(assessment_id=view['assessment_id'],fingerprint=view['fingerprint'],confirmed=current,selected=[]))
   after=owner_read();checks['prior_process_events_preserved']=all(after['events'].get(k)==v for k,v in old['events'].items())
   checks['exactly_three_new_native_events']=len(after['events'])==len(old['events'])+3 and len(after['intervals'])==len(old['intervals'])+1 and after['intervals'][-1]==[0,1,0,1] and after['integrity']=='ok'
   checks['prior_choices_preserved']=all(sha(p)==v for p,v in oldchoices.items())
   (drop/'owned-child.conf').unlink();drop.rmdir();created=False;system('daemon-reload')
   p=subprocess.run(['systemctl','start',control.UNIT],capture_output=True,timeout=10);time.sleep(.15)
   checks['restart_without_fresh_grant_refused']=system('show',control.UNIT,'-p','ActiveState','--value')=='failed' and not control.GRANT.exists()
   system('reset-failed',control.UNIT)
  selected=launch.recent('process');bindings=launch.recent('history');cert=launch.prepare(selected,bindings)
  ctx=ssl.create_default_context(cafile=str(cert));opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx))
  def http(path,token=None,value=None):
   headers={'Sec-Fetch-Site':'same-origin'}
   if token:headers['Authorization']='Bearer '+token
   if value is not None:headers.update(Origin='https://127.0.0.1:18765',**{'Content-Type':'application/json'})
   r=urllib.request.Request('https://127.0.0.1:18765'+path,headers=headers,data=None if value is None else json.dumps(value).encode())
   try:
    with opener.open(r,timeout=3) as answer:return answer.status,json.loads(answer.read(65537))
   except urllib.error.HTTPError as exc:return exc.code,None
  def token():return http('/v0/auth/redeem',value={'grant':request('mint').split('#grant=')[1]})[1]['token']
  first=token();_,summary=http('/v0/dashboard',first)
  checks['frozen_real_counts']=summary['process']['snapshot']['counts']['events']==len(after['events']) and summary['history']['snapshot']['counts']['events']==19 and summary['history']['snapshot']['counts']['unevaluated']==16
  procview=summary['process']['snapshot']['view_id']
  launch.stop();launch.prepare(selected,bindings)
  checks['viewer_restart_revokes_old_session']=http('/v0/dashboard',first)[0]==403
  second=token();_,newsummary=http('/v0/dashboard',second)
  checks['reopen_refreezes_retained_history']=newsummary['process']['snapshot']['view_id']!=procview and newsummary['process']['snapshot']['counts']==summary['process']['snapshot']['counts']
  request('revoke_all');checks['explicit_root_revoke']=http('/v0/dashboard',second)[0]==403
  # Actual ordinary sandboxed browser against the packaged app and both stores.
  name='hids-release-'+work.name.split('.')[-1].replace('_','x');policy=work/'browser.profile'
  policy.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile '+name+' /opt/hids-browser/chrome flags=(unconfined) {\n userns,\n}\n');loaded=True
  subprocess.run(['apparmor_parser','--skip-cache','--replace',str(policy)],check=True,capture_output=True,timeout=10)
  bwork=Path(tempfile.mkdtemp(prefix='hids-release-browser.',dir='/var/tmp'));os.chown(bwork,user.pw_uid,user.pw_gid);bwork.chmod(0o700)
  shutil.copyfile(cert,bwork/'leaf.pem');os.chown(bwork/'leaf.pem',user.pw_uid,user.pw_gid);(bwork/'leaf.pem').chmod(0o600)
  browser=subprocess.Popen([str(args.browser_python),'-B',str(ROOT/'tests/integration/combined_dashboard_browser.py'),str(bwork),'/usr/bin','/opt/hids-browser/chrome'],stdin=subprocess.PIPE,stdout=(work/'browser.stdout').open('x'),stderr=(work/'browser.stderr').open('x'),text=True,user=user.pw_uid,group=user.pw_gid,extra_groups=[])
  browser.communicate(json.dumps(dict(url=request('mint'),counts=dict(process=len(after['events']),history=19,findings=1)))+'\n',timeout=60)
  br=json.loads((bwork/'report.json').read_text());checks['ordinary_browser_full_acceptance']=browser.returncode==0 and br['passed'];report['browser_report']=str(bwork/'report.json');report['browser_checks']=br['checks']
  launch.stop()
  checks['production_binary_unchanged']=sha(binary)==binary_before
  checks['empty_final_choices']=root_store().load()['selected']==[];report['final_revision']=root_store().load()['revision'];report['process_event_count']=len(after['events'])
  dev.verify(ROOT,args.expected_manifest)
 except BaseException as exc:
  import traceback;report['error_type']=type(exc).__name__;(work/'failure.txt').write_text(traceback.format_exc())
 finally:
  if browser is not None and browser.poll() is None:browser.terminate();browser.wait(timeout=8)
  launch.stop()
  with manager.root_lock():manager.manager().stop()
  if created and all(system('show',u,'-p','ActiveState','--value')=='inactive' for u in SOURCES):
   (drop/'owned-child.conf').unlink();drop.rmdir();system('daemon-reload')
  if loaded:launch.remove_policy(policy,name)
  checks['temporary_policy_restored']=set(profiles.read_text().splitlines())==oldprofiles
  checks['original_m3_m4_policy_preserved']=lab.preserved()==baseline
  checks['all_services_stopped']=all(system('show',u,'-p','ActiveState','--value')=='inactive' for u in (*SOURCES,*VIEWER))
  report['result']='passed' if checks and all(checks.values()) and 'error_type' not in report else 'failed'
  (work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(work/'report.json'),checks=checks,error_type=report.get('error_type'),final_revision=report.get('final_revision'),process_event_count=report.get('process_event_count'))))
 return int(report['result']!='passed')
if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
