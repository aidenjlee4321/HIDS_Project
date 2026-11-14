"""Explicit bounded D-12c trial. Real payload evidence never leaves private VM dirs."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
UNITS=['hids-dashboard-history.service','hids-dashboard-history-http.socket','hids-dashboard-history-control.socket']
META=r'''import json,os,sqlite3,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
p=Path('/var/lib/hids/m4/store/handoff.sqlite');assert os.statvfs(p.parent).f_flag&os.ST_RDONLY
st=p.stat();db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,isolation_level=None);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA busy_timeout=50');db.execute('BEGIN')
try:
 bindings=[r[0] for r in db.execute('SELECT binding_key FROM m4h_bindings ORDER BY binding_key LIMIT 3')];assert 1<=len(bindings)<=2
 result=dict(identity=[st.st_dev,st.st_ino],bindings=bindings,counts=dict(events=db.execute('SELECT count(*) FROM m4h_events').fetchone()[0],findings=db.execute('SELECT count(*) FROM m4h_alerts').fetchone()[0],unevaluated=db.execute('SELECT count(*) FROM m4h_events e WHERE NOT EXISTS(SELECT 1 FROM m4h_evaluations v WHERE v.event_key=e.event_key)').fetchone()[0]))
 # Protected ground truth; never stdout real payloads outside this private pipe.
 result['events']=[dict(event_id=k,content_hash=h,first_offset=str(o),envelope=json.loads(e),imported_at=t) for k,h,o,e,t in db.execute('SELECT event_key,content_hash,first_offset,envelope,imported_at FROM m4h_events LIMIT 129')]
 result['findings']=[dict(finding_id=k,event_id=e,rule_id=r,revision=v,explanation=x,matched_values=json.loads(m)) for k,e,r,v,x,m in db.execute('SELECT alert_id,event_key,rule_id,revision,explanation,matched_values FROM m4h_alerts LIMIT 33')]
 print(json.dumps(result),flush=True)
finally:db.execute('ROLLBACK');db.close()
'''
IMPOSTOR=r'''import http.server,json,ssl,sys
class H(http.server.BaseHTTPRequestHandler):
 def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'impostor')
 def log_message(self,*a):pass
server=http.server.HTTPServer(('127.0.0.1',18765),H);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(sys.argv[1],sys.argv[2]);server.socket=ctx.wrap_socket(server.socket,server_side=True);print('ready',flush=True);server.serve_forever()
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--browser-build',type=Path,required=True);p.add_argument('--tools',type=Path,required=True);p.add_argument('--real',action='store_true');args=p.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path.insert(0,str(ROOT/'scripts'));import dev;dev.verify(ROOT,args.expected_manifest)
 sys.path.insert(0,str(ROOT/'tests/integration'));import dashboard_pilot_ubuntu as lab;import tls_acceptance_ubuntu as tls
 lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 before=lab.preserved();assert all(v=='inactive' for v in before['units'].values())
 assert before==json.loads(Path('/var/tmp/hids-dashboard-acceptance.4e_4n__z/baseline.json').read_text()),'original baseline mismatch before setup'
 for source in (ROOT/'frontend').rglob('*'):
  if source.is_file():assert source.read_bytes()==(args.assets.parent/source.relative_to(ROOT/'frontend')).read_bytes(),'frontend build input mismatch'
 root=Path(tempfile.mkdtemp(prefix='hids-history-trial.',dir='/var/tmp'));root.chmod(0o700)
 report=dict(result='running',real_data=args.real,source_manifest=args.expected_manifest,checks={});checks=report['checks'];loaded=False;browser=None;servers=None;impostor=None;installed=[];config_path=Path('/etc/hids/dashboard-history.json');override=Path('/run/systemd/system/hids-dashboard-history.service.d')
 install=Path('/opt/hids-dashboard-history');certdir=Path('/etc/hids/dashboard-history-tls');user=pwd.getpwnam('ivy');backend=pwd.getpwnam('hids-ingest');normal_dirs=[Path('/home/ivy/.pki/nssdb'),Path('/home/ivy/.local/share/pki/nssdb')]
 def inventory():return {str(d):{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in d.glob('*') if p.is_file()} if d.exists() else None for d in normal_dirs}
 normal=inventory();policy=Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns').read_text();profile_name='hids-history-'+root.name.split('.')[-1].replace('_','x')
 def run(cmd,**kw):return subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=30,**kw)
 def system(*cmd):return run(['/usr/bin/systemctl',*cmd])
 def stop():
  subprocess.run(['/usr/bin/systemctl','stop',*UNITS],capture_output=True,timeout=15)
 def readonly_meta(store):
  return json.loads(run(['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect','--unit='+profile_name+'-meta','-p','User=hids-ingest','-p','Group=hids-ingest','-p','NoNewPrivileges=yes','-p','ProtectSystem=strict','-p','ProtectHome=yes','-p','TemporaryFileSystem=/var/lib/hids:ro','-p','BindReadOnlyPaths='+str(store)+':/var/lib/hids/m4/store','/opt/hids-dashboard-pilot/venv/bin/python','-I','-B','-c',META,str(install/'code')]).stdout)
 try:
  assert not config_path.exists() and not override.exists()
  for name in UNITS:assert not Path('/run/systemd/system',name).exists() and not Path('/etc/systemd/system',name).exists()
  with socket.socket() as probe:
   # Match systemd's ordinary TCP address reuse. An active listener still
   # refuses; recently closed TLS connections in TIME_WAIT do not masquerade
   # as an occupied listener between bounded synthetic/real trials.
   probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);probe.bind(('127.0.0.1',18765));probe.listen(1)
  if not install.exists():install.mkdir(mode=0o755);(install/'TRIAL_MARKER').write_text('hids-d12c-frozen-history\n')
  assert (install/'TRIAL_MARKER').read_text()=='hids-d12c-frozen-history\n'
  # Preserve any earlier trial build; never rewrite evidence or old snapshots.
  version=install/('build-'+root.name.split('.')[-1]);version.mkdir(mode=0o755)
  for folder in ('api','engine','shared','rules'):shutil.copytree(ROOT/folder,version/folder,ignore=shutil.ignore_patterns('__pycache__'))
  shutil.copytree(args.assets,version/'assets')
  report['asset_sha256']={str(p.relative_to(version/'assets')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (version/'assets').rglob('*') if p.is_file()}
  (version/'tests/unit').mkdir(parents=True);shutil.copyfile(ROOT/'tests/unit/test_history_view.py',version/'tests/unit/test_history_view.py')
  # Fixed service paths point only to this root-controlled accepted build.
  for name,target in (('code',version),('assets',version/'assets')):
   link=install/name
   if link.exists() or link.is_symlink():assert link.is_symlink() and str(link.resolve()).startswith(str(install)+'/build-');link.unlink()
   link.symlink_to(target)
  if not (install/'venv').exists():(install/'venv').symlink_to('/opt/hids-dashboard-pilot/venv')
  for parent,dirs,files in os.walk(version):
   Path(parent).chmod(0o755)
   for name in files:(Path(parent)/name).chmod(0o644)
  fixture=Path('/opt/hids-tls-synthetic.8m5rf1fp')
  # Retain distinct fresh trial keys under a fixed root-managed directory.
  if certdir.exists():
   assert (certdir/'TRIAL_MARKER').read_text()=='hids-d12c-leaf\n'
   retained=certdir.with_name(certdir.name+'-retained-'+root.name.split('.')[-1]);certdir.rename(retained)
  certdir.mkdir(mode=0o750);os.chown(certdir,0,backend.pw_gid);(certdir/'TRIAL_MARKER').write_text('hids-d12c-leaf\n')
  run(['/usr/bin/openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','7','-subj','/CN=HIDS bounded history trial','-addext','basicConstraints=critical,CA:FALSE','-addext','subjectAltName=IP:127.0.0.1','-addext','extendedKeyUsage=serverAuth','-keyout',str(certdir/'leaf.key'),'-out',str(certdir/'leaf.pem')])
  os.chown(certdir/'leaf.key',0,backend.pw_gid);(certdir/'leaf.key').chmod(0o440);(certdir/'leaf.pem').chmod(0o644)
  fingerprint=hashlib.sha256(subprocess.check_output(['/usr/bin/openssl','x509','-in',str(certdir/'leaf.pem'),'-outform','DER'])).hexdigest()
  checks['ordinary_user_key_denied']=subprocess.run(['/usr/bin/test','-r',str(certdir/'leaf.key')],user=user.pw_uid,group=user.pw_gid,extra_groups=[]).returncode!=0
  if args.real:store=Path('/var/lib/hids/m4/store')
  else:
   synthetic=Path(tempfile.mkdtemp(prefix='hids-history-fixture.',dir='/opt'));synthetic.chmod(0o755);store=synthetic/'store';store.mkdir(mode=0o700);os.chown(store,backend.pw_uid,backend.pw_gid)
   # Fixture creation occurs before the read-only trial, in an ordinary backend
   # process, with an open writer keeping WAL/SHM present throughout acceptance.
   code="import sys,json,sqlite3,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[1]+'/tests/unit');from test_history_view import fixture,DDL_V2;db=sqlite3.connect(sys.argv[2],isolation_level=None);db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA application_id=0x48344c31');db.execute('PRAGMA user_version=2');db.executescript(DDL_V2);rows=fixture();[(db.execute('INSERT INTO '+t+' ('+','.join(r)+') VALUES ('+','.join('?' for _ in r)+')',tuple(r.values()))) for t,rs in rows.items() for r in rs];print('ready',flush=True);sys.stdin.readline();db.close()"
   fixture_writer=subprocess.Popen(['/opt/hids-dashboard-pilot/venv/bin/python','-I','-B','-c',code,str(version),str(store/'handoff.sqlite')],user=backend.pw_uid,group=backend.pw_gid,extra_groups=[],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'fixture.stderr').open('x'),text=True,umask=0o077);assert fixture_writer.stdout.readline().strip()=='ready'
  baseline={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in store.iterdir() if p.is_file() and not p.name.endswith('-shm')}
  meta=readonly_meta(store);(root/'ground-truth.json').write_text(json.dumps(meta));checks['ground_truth_counts']=meta['counts']==(dict(events=19,findings=1,unevaluated=16) if args.real else dict(events=25,findings=1,unevaluated=16))
  config_path.write_text(json.dumps(dict(version=1,mode='frozen-history',port=18765,identity=meta['identity'],bindings=meta['bindings'],certificate_sha256=fingerprint)));os.chown(config_path,0,backend.pw_gid);config_path.chmod(0o440);installed.append(config_path)
  checks['ordinary_user_config_denied']=subprocess.run(['/usr/bin/test','-r',str(config_path)],user=user.pw_uid,group=user.pw_gid,extra_groups=[]).returncode!=0
  for name in UNITS:
   target=Path('/run/systemd/system',name);shutil.copyfile(ROOT/'packaging/systemd'/name,target);target.chmod(0o644);installed.append(target)
  if not args.real:
   override.mkdir(mode=0o755);p=override/'fixture.conf';p.write_text('[Service]\nBindReadOnlyPaths=\nBindReadOnlyPaths='+str(store)+':/var/lib/hids/m4/store\n');installed.append(p)
  system('daemon-reload');system('start','hids-dashboard-history-http.socket','hids-dashboard-history-control.socket','hids-dashboard-history.service')
  for _ in range(100):
   if system('show','hids-dashboard-history.service','--property=ActiveState','--value').stdout.strip()!='active':raise AssertionError('history service inactive')
   try:
    import ssl,urllib.request
    ctx=ssl.create_default_context(cafile=str(certdir/'leaf.pem'))
    urllib.request.urlopen('https://127.0.0.1:18765/',context=ctx,timeout=1).read();break
   except Exception:time.sleep(.1)
  else:raise AssertionError('history TLS startup unavailable')
  sys.path.insert(0,str(version));from api.history_cli import request
  if not args.real:
   original=config_path.read_text();bad=json.loads(original);bad['identity'][1]+=1;config_path.write_text(json.dumps(bad));system('restart','hids-dashboard-history.service');time.sleep(.5)
   try:request('mint')
   except Exception:checks['unavailable_store_refuses_grants']=True
   else:checks['unavailable_store_refuses_grants']=False
   checks['unavailable_store_allows_root_revoke']=request('revoke_all')=='All history sessions revoked.'
   config_path.write_text(original);system('restart','hids-dashboard-history.service');time.sleep(.5)
  url=request('mint');token=None
  def http(path,token=None,method='GET',value=None):
   headers={'Sec-Fetch-Site':'same-origin'}
   if token:headers['Authorization']='Bearer '+token
   if value is not None:headers.update(Origin='https://127.0.0.1:18765',**{'Content-Type':'application/json'})
   req=urllib.request.Request('https://127.0.0.1:18765'+path,data=None if value is None else json.dumps(value).encode(),headers=headers,method=method)
   with urllib.request.urlopen(req,context=ctx,timeout=3) as r:return json.loads(r.read(65537))
  auth=http('/v0/auth/redeem',method='POST',value={'grant':url.split('#grant=')[1]});token=auth['token'];assert auth['scope']=='history:read'
  summary=http('/v0/history',token);checks['api_counts_and_history_only']=all(summary['counts'][k]==v for k,v in meta['counts'].items()) and summary['history_only'] and summary['monitoring_status']=='not_assessed'
  got=[];cursor=None
  while True:
   data=http('/v0/history/events'+('' if cursor is None else '?cursor='+cursor),token);got+=data['items'];cursor=data['next_cursor']
   if cursor is None:break
  checks['selected_exact_keys']=sorted(v['event_id'] for v in got)==sorted(v['event_id'] for v in meta['events'])
  good=True
  for expected in meta['events']:
   actual=http('/v0/history/events/'+expected['event_id'],token);native=expected['envelope'];execution=dict(native['execution']);execution['result']=str(execution['result']);metadata=dict(native['metadata']);metadata['first_observed_unix_ns']=None if metadata['first_observed_unix_ns'] is None else str(metadata['first_observed_unix_ns'])
   good=good and actual['execution']==execution and actual['metadata']==metadata and actual['content_hash']==expected['content_hash'] and actual['native_identity']==native['identity'] and actual['first_offset']==expected['first_offset'] and actual['scope']=={k:native[k] for k in ('source','activation','generation')}
  checks['every_projected_event_matches_ground_truth']=good
  checks['every_projected_finding_matches_ground_truth']=all(all(http('/v0/history/findings/'+v['finding_id'],token)[k]==x for k,x in v.items()) for v in meta['findings'])
  http('/v0/auth/logout',token,'POST',{});url=request('mint')
  pid=int(system('show','hids-dashboard-history.service','--property=MainPID','--value').stdout);status=Path(f'/proc/{pid}/status').read_text();checks['backend_unprivileged_zero_caps']=f'Uid:\t{backend.pw_uid}\t{backend.pw_uid}\t{backend.pw_uid}\t{backend.pw_uid}' in status and 'CapEff:\t0000000000000000' in status
  fds=[]
  for p in Path(f'/proc/{pid}/fd').iterdir():
   try:fds.append(os.readlink(p))
   except FileNotFoundError:pass  # A just-closed HTTP/control connection.
  checks['no_sqlite_reader_retained']=not any('handoff.sqlite' in name for name in fds)
  checks['private_mount_hides_other_state']=not Path(f'/proc/{pid}/root/var/lib/hids/m3').exists() and not Path(f'/proc/{pid}/root/var/lib/hids/m4/backups').exists()
  probe="import os,errno,json;from pathlib import Path;p=Path('/var/lib/hids/m4/store');assert os.statvfs(p).f_flag&os.ST_RDONLY;\ntry:os.open(p/'must-not-create',os.O_CREAT|os.O_WRONLY,0o600)\nexcept OSError as e:assert e.errno==errno.EROFS\nelse:raise AssertionError('writable store')\nprint('read-only')"
  checks['backend_store_write_denied']=run(['/usr/bin/nsenter','-t',str(pid),'-m','--','/usr/bin/setpriv','--reuid='+str(backend.pw_uid),'--regid='+str(backend.pw_gid),'--clear-groups','/usr/bin/python3','-B','-c',probe]).stdout.strip()=='read-only'
  report['resource_limits']=system('show','hids-dashboard-history.service','--property=MemoryMax,MemoryPeak,TasksMax,TasksCurrent,RuntimeMaxUSec').stdout
  checks['memory_and_task_limits']='MemoryMax=268435456' in report['resource_limits'] and 'TasksMax=32' in report['resource_limits'] and 'RuntimeMaxUSec=10min' in report['resource_limits']
  # Use a distinct root-owned browser image and temporary exact-path userns grant.
  browserroot=Path('/opt/hids-browser-leaf.940b2j6b/browser')
  assert browserroot.is_dir() and browserroot.resolve()==browserroot
  for parent,dirs,files in os.walk(browserroot):
   for p in [Path(parent),*(Path(parent)/n for n in dirs+files)]:
    info=p.lstat();assert info.st_uid==0 and (p.is_symlink() or not info.st_mode&0o022)
    if p.is_symlink():assert str(p.resolve()).startswith(str(browserroot)+'/')
  binary=browserroot/'chrome';report['browser_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest();assert report['browser_sha256']=='40c121f803bd7f2c3dc394a12f064d14af1faea4baf7938dd2a8edd5175086f6'
  profile=root/'apparmor.profile';profile.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile '+profile_name+' '+str(binary)+' flags=(unconfined) {\n userns,\n}\n');run(['/usr/sbin/apparmor_parser','--skip-cache','--replace',str(profile)]);loaded=True
  fingerprint_synthetic=hashlib.sha256(subprocess.check_output(['/usr/bin/openssl','x509','-in',str(fixture/'valid.pem'),'-outform','DER'])).hexdigest()
  servers=subprocess.Popen(['/usr/bin/python3','-B','-c',tls.SERVER,str(fixture/'code'),str(fixture),str(backend.pw_gid),fingerprint_synthetic],user=backend.pw_uid,group=backend.pw_gid,extra_groups=[],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'tls.stderr').open('x'),text=True);ports=json.loads(servers.stdout.readline())
  work=Path(tempfile.mkdtemp(prefix='history-browser.',dir=args.browser_build));os.chown(work,user.pw_uid,user.pw_gid);work.chmod(0o700)
  for name,source in [('valid',fixture/'valid.pem'),('expired',fixture/'expired.pem'),('history',certdir/'leaf.pem')]:
   p=work/(name+'.pem');shutil.copyfile(source,p);os.chown(p,user.pw_uid,user.pw_gid);p.chmod(0o600)
  command=dict(url=url,ports=ports,counts=meta['counts'],synthetic=not args.real)
  browser=subprocess.Popen([str(args.browser_build/'venv/bin/python'),'-B',str(ROOT/'tests/integration/history_browser.py'),str(work),str(args.tools),str(binary)],user=user.pw_uid,group=user.pw_gid,extra_groups=[],env=dict(os.environ,PLAYWRIGHT_BROWSERS_PATH=str(args.browser_build/'browsers')),stdin=subprocess.PIPE,stdout=(root/'browser.stdout').open('x'),stderr=(root/'browser.stderr').open('x'),text=True);browser.stdin.write(json.dumps(command)+'\n');browser.stdin.close()
  deadline=time.monotonic()+100
  while not (work/'ready-impostor').exists() and browser.poll() is None and time.monotonic()<deadline:time.sleep(.1)
  if not (work/'ready-impostor').exists():raise AssertionError('browser failed before impostor test')
  report['resource_peak_after_browser']=system('show','hids-dashboard-history.service','--property=MemoryPeak,TasksCurrent').stdout
  request('revoke_all');stop()
  impostor=subprocess.Popen(['/usr/bin/python3','-B','-c',IMPOSTOR,str(fixture/'foreign.pem'),str(fixture/'foreign.key')],user=backend.pw_uid,group=backend.pw_gid,extra_groups=[],stdout=subprocess.PIPE,stderr=(root/'impostor.stderr').open('x'),text=True);assert impostor.stdout.readline().strip()=='ready';signal=work/'impostor-ready';signal.write_text('ready');os.chown(signal,user.pw_uid,user.pw_gid);browser.wait(timeout=30)
  result=json.loads((work/'report.json').read_text());report['browser_report']=str(work/'report.json');checks['browser_acceptance']=browser.returncode==0 and result['passed'];report['browser_checks']=result['checks']
  # Reopening metadata only confirms no stored evaluation or history change.
  after_meta=readonly_meta(store);checks['ground_truth_unchanged']=after_meta==meta
  checks['trial_store_main_wal_unchanged']=baseline=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in store.iterdir() if p.is_file() and not p.name.endswith('-shm')}
  dev.verify(ROOT,args.expected_manifest);checks['source_snapshot_unchanged']=True
  report['result']='passed' if all(checks.values()) else 'failed'
 except Exception as e:
  report['result']='failed';report['error_type']=type(e).__name__;report['error']=str(e)[:150] if isinstance(e,AssertionError) else 'private failure retained'
  import traceback;(root/'failure.txt').write_text(traceback.format_exc())
 finally:
  if browser and browser.poll() is None:browser.terminate();browser.wait(timeout=10)
  if impostor:impostor.terminate();impostor.wait(timeout=5)
  stop()
  if servers:
   try:servers.stdin.write('stop\n');servers.stdin.flush();servers.wait(timeout=8)
   except Exception:servers.kill();servers.wait()
   checks['tls_helpers_stopped']=servers.returncode==0
  if loaded:
   result=subprocess.run(['/usr/sbin/apparmor_parser','--skip-cache','--remove',str(profile)],capture_output=True);checks['temporary_browser_policy_removed']=result.returncode==0 and profile_name not in Path('/sys/kernel/security/apparmor/profiles').read_text()
  # Only paths exclusively created by this trial are removed. Evidence, source,
  # key/cert, browser environment and all pre-existing history remain retained.
  for p in reversed(installed):
   if p.exists():p.unlink()
  if override.exists():override.rmdir()
  system('daemon-reload')
  checks['service_stopped']=all(subprocess.run(['/usr/bin/systemctl','is-active','--quiet',u],capture_output=True).returncode!=0 for u in UNITS)
  checks['normal_nss_unchanged']=inventory()==normal;checks['global_namespace_policy_unchanged']=Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns').read_text()==policy;checks['production_preserved']=lab.preserved()==before
  checks['original_preservation_baseline_matches']=before==json.loads(Path('/var/tmp/hids-dashboard-acceptance.4e_4n__z/baseline.json').read_text())
  if not args.real and 'fixture_writer' in locals():fixture_writer.stdin.write('stop\n');fixture_writer.stdin.flush();fixture_writer.wait(timeout=5)
  if not all(checks.values()):report['result']='failed'
  report['elapsed_complete']=True;p=root/'report.json';p.write_text(json.dumps(report,indent=2));p.chmod(0o600);os.close(lock)
  print(json.dumps(dict(result=report['result'],report=str(p),checks=checks,error=report.get('error'))),flush=True)
 return 0 if report['result']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
