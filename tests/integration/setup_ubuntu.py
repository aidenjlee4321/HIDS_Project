"""Explicit D-14a lab: synthetic faults/controls first, then real empty selection."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import pwd
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import termios
import time

ROOT=Path(__file__).resolve().parents[2]
UNITS=('hids-dashboard-setup.service','hids-dashboard-setup-http.socket','hids-dashboard-setup-control.socket')

def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--browser-build',type=Path,required=True);p.add_argument('--tools',type=Path,required=True);p.add_argument('--real',action='store_true');args=p.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path.insert(0,str(ROOT/'scripts'));import dev;dev.verify(ROOT,args.expected_manifest)
 sys.path.insert(0,str(ROOT/'tests/integration'));import dashboard_pilot_ubuntu as lab
 lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 before=lab.preserved();assert before==json.loads(Path('/var/tmp/hids-dashboard-acceptance.4e_4n__z/baseline.json').read_text()) and all(v=='inactive' for v in before['units'].values())
 for source in (ROOT/'frontend').rglob('*'):
  if source.is_file():assert source.read_bytes()==(args.assets.parent/source.relative_to(ROOT/'frontend')).read_bytes()
 root=Path(tempfile.mkdtemp(prefix='hids-setup-lab.',dir='/opt'));root.chmod(0o755);evidence=root/'private';evidence.mkdir(mode=0o700)
 report=dict(result='running',real=args.real,source_manifest=args.expected_manifest,checks={});checks=report['checks'];installed=[];browser=None;loaded=False
 backend=pwd.getpwnam('hids-ingest');user=pwd.getpwnam('ivy');config_path=Path('/etc/hids/dashboard-setup.json');preview=Path('/etc/hids/setup-preview');install=Path('/opt/hids-dashboard-setup')
 normal_dirs=(Path('/home/ivy/.pki/nssdb'),Path('/home/ivy/.local/share/pki/nssdb'))
 def inventory():return {str(d):{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in d.glob('*') if p.is_file()} if d.exists() else None for d in normal_dirs}
 normal=inventory();policy=Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns').read_text()
 def run(*cmd):return subprocess.run(list(cmd),check=True,capture_output=True,text=True,timeout=20)
 def system(*cmd):return run('/usr/bin/systemctl',*cmd)
 def stop():subprocess.run(['/usr/bin/systemctl','stop',*UNITS],capture_output=True,timeout=15)
 try:
  assert not config_path.exists()
  for name in UNITS:assert not Path('/run/systemd/system',name).exists() and not Path('/etc/systemd/system',name).exists()
  with socket.socket() as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',18765));s.listen(1)
  if not install.exists():install.mkdir(mode=0o755);(install/'TRIAL_MARKER').write_text('hids-d14a-setup\n')
  assert (install/'TRIAL_MARKER').read_text()=='hids-d14a-setup\n'
  version=install/('build-'+root.name.split('.')[-1]);version.mkdir(mode=0o755)
  for folder in ('api','engine','shared'):shutil.copytree(ROOT/folder,version/folder,ignore=shutil.ignore_patterns('__pycache__'))
  (version/'tests/unit').mkdir(parents=True);shutil.copyfile(ROOT/'tests/unit/test_setup.py',version/'tests/unit/test_setup.py');shutil.copytree(args.assets,version/'assets')
  for parent,dirs,files in os.walk(version):
   Path(parent).chmod(0o755)
   for name in files:(Path(parent)/name).chmod(0o644)
  for name,target in (('code',version),('assets',version/'assets')):
   link=install/name
   if link.exists() or link.is_symlink():assert link.is_symlink() and str(link.resolve()).startswith(str(install)+'/build-');link.unlink()
   link.symlink_to(target)
  if not (install/'venv').exists():(install/'venv').symlink_to('/opt/hids-dashboard-pilot/venv')
  sys.path.insert(0,str(version));sys.path.insert(0,str(ROOT/'tests/unit'))
  from api.setup_store import _Store
  from api.setup_contract import canonical
  from api.setup_manager import RUNTIME
  from test_setup import fixture
  if not args.real:
   from setup_faults_ubuntu import run_faults
   faults=root/'faults';faults.mkdir(mode=0o755);report['faults']=run_faults(faults,version);checks['faults_and_actual_m3_control_ipc']=all(report['faults'].values())
   choices=root/'choices';choices.mkdir(mode=0o750);os.chown(choices,0,backend.pw_gid);owned=root/'owned';owned.mkdir(mode=0o700)
  else:
   choices=Path('/etc/hids/setup');owned=RUNTIME
   for d,mode,gid in ((choices,0o750,backend.pw_gid),(owned,0o700,0)):
    if not d.exists():d.mkdir(mode=mode);os.chown(d,0,gid)
  store=_Store(choices,0,backend.pw_gid);initial=store.load();require_empty=initial['selected']==[];assert require_empty,'real trial only permits empty source selection'
  def view():
   if args.real:
    from api.setup_preflight import assess
    result=assess(store.load());assert all(s['preflight']!='eligible' for s in result['sources']),'unexpected usable source; trial is empty/blocked only';return result
   return fixture(record=store.load())
  # Trial snapshot directories are retained; any pre-existing known snapshot is
  # moved to a private retained directory rather than silently overwritten.
  if preview.exists():
   assert (preview/'TRIAL_MARKER').read_text()=='hids-d14a-preview\n';preview.rename(preview.with_name(preview.name+'-retained-'+root.name.split('.')[-1]))
  preview.mkdir(mode=0o750);os.chown(preview,0,backend.pw_gid);(preview/'TRIAL_MARKER').write_text('hids-d14a-preview\n')
  cert=Path('/etc/hids/dashboard-history-tls/leaf.pem');fingerprint=hashlib.sha256(subprocess.check_output(['/usr/bin/openssl','x509','-in',str(cert),'-outform','DER'])).hexdigest()
  def publish_view():
   raw=canonical(view()).encode();vp=preview/'view.json';vp.write_bytes(raw);os.chown(vp,0,backend.pw_gid);vp.chmod(0o440)
   config_path.write_text(json.dumps(dict(version=1,port=18765,certificate_sha256=fingerprint,view_sha256=hashlib.sha256(raw).hexdigest())));os.chown(config_path,0,backend.pw_gid);config_path.chmod(0o440)
  publish_view();installed.append(config_path)
  for name in UNITS:
   target=Path('/run/systemd/system',name);shutil.copyfile(ROOT/'packaging/systemd'/name,target);target.chmod(0o644);installed.append(target)
  system('daemon-reload');system('start',*UNITS)
  from api.setup_cli import request
  def mint():
   for _ in range(40):
    try:return request('mint')
    except Exception:time.sleep(.1)
   raise AssertionError('setup grant unavailable')
  if not args.real:
   good=config_path.read_text();bad=json.loads(good);bad['view_sha256']='0'*64;config_path.write_text(json.dumps(bad));system('restart',UNITS[0]);time.sleep(.4)
   try:request('mint')
   except Exception:checks['unsafe_snapshot_refuses_grants']=True
   else:checks['unsafe_snapshot_refuses_grants']=False
   checks['unavailable_snapshot_root_revoke_available']=request('revoke_all') is True
   config_path.write_text(good);system('restart',UNITS[0])
  url=mint();checks['ordinary_user_cli_denied']=subprocess.run(['/opt/hids-dashboard-pilot/venv/bin/python','-I','-B','-c',"import sys;sys.path.insert(0,sys.argv[1]);from api.setup_cli import request;request('mint')",str(version)],user=user.pw_uid,group=user.pw_gid,extra_groups=[],capture_output=True).returncode!=0
  checks['ordinary_user_config_denied']=subprocess.run(['/usr/bin/test','-r',str(config_path)],user=user.pw_uid,group=user.pw_gid,extra_groups=[]).returncode!=0
  pid=int(system('show',UNITS[0],'--property=MainPID','--value').stdout);status=Path(f'/proc/{pid}/status').read_text();checks['backend_zero_caps_unprivileged']=f'Uid:\t{backend.pw_uid}\t{backend.pw_uid}\t{backend.pw_uid}\t{backend.pw_uid}' in status and 'CapEff:\t0000000000000000' in status
  checks['original_hids_state_hidden']=not Path(f'/proc/{pid}/root/var/lib/hids').exists() or not os.access(f'/proc/{pid}/root/var/lib/hids',os.R_OK) # inspect mount explicitly below
  probe="import os;from pathlib import Path;\nfor p in ['/var/lib/hids/m3','/var/lib/hids/m4/store','/run/hids-setup']:\n try:os.listdir(p)\n except (PermissionError,FileNotFoundError):pass\n else:raise AssertionError('sensitive state visible')\nprint('hidden')"
  checks['original_hids_state_hidden']=run('/usr/bin/nsenter','-t',str(pid),'-m','--','/usr/bin/setpriv','--reuid='+str(backend.pw_uid),'--regid='+str(backend.pw_gid),'--clear-groups','/usr/bin/python3','-B','-c',probe).stdout.strip()=='hidden'
  report['limits']=system('show',UNITS[0],'--property=MemoryMax,MemoryPeak,TasksMax,RuntimeMaxUSec').stdout
  binary=Path('/opt/hids-browser-leaf.940b2j6b/browser/chrome');assert hashlib.sha256(binary.read_bytes()).hexdigest()=='40c121f803bd7f2c3dc394a12f064d14af1faea4baf7938dd2a8edd5175086f6'
  profile_name='hids-setup-'+root.name.split('.')[-1].replace('_','x');profile=evidence/'apparmor.profile';profile.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile '+profile_name+' '+str(binary)+' flags=(unconfined) {\n userns,\n}\n');run('/usr/sbin/apparmor_parser','--skip-cache','--replace',str(profile));loaded=True
  work=Path(tempfile.mkdtemp(prefix='setup-browser.',dir=args.browser_build));os.chown(work,user.pw_uid,user.pw_gid);work.chmod(0o700);shutil.copyfile(cert,work/'leaf.pem');os.chown(work/'leaf.pem',user.pw_uid,user.pw_gid);(work/'leaf.pem').chmod(0o600)
  browser=subprocess.Popen([str(args.browser_build/'venv/bin/python'),'-B',str(ROOT/'tests/integration/setup_browser.py'),str(work),str(args.tools),str(binary)],user=user.pw_uid,group=user.pw_gid,extra_groups=[],env=dict(os.environ,PLAYWRIGHT_BROWSERS_PATH=str(args.browser_build/'browsers')),stdin=subprocess.PIPE,stdout=(evidence/'browser.stdout').open('x'),stderr=(evidence/'browser.stderr').open('x'),text=True)
  browser.stdin.write(json.dumps(dict(url=url,synthetic=not args.real,revision=initial['revision']))+'\n');browser.stdin.close()
  def waitfile(name,seconds=40):
   end=time.monotonic()+seconds
   while not (work/name).exists() and browser.poll() is None and time.monotonic()<end:time.sleep(.05)
   assert (work/name).exists(),'browser failed before '+name;return json.loads((work/name).read_text())
  def notify(name,value):
   p=work/name;p.write_text(json.dumps(value));os.chown(p,user.pw_uid,user.pw_gid);p.chmod(0o600)
  if not args.real:
   expired=waitfile('ready-expiry.json');waitfile('expiry-complete.json',80)
   try:request('review',expired['reference'])
   except Exception:checks['actual_expired_draft_refused']=True
   else:checks['actual_expired_draft_refused']=False
   notify('expiry-verified.json',dict(verified=checks['actual_expired_draft_refused']))
  ready=waitfile('ready-confirm.json')
  try:request('review',ready['old_reference'])
  except Exception:checks['replaced_draft_reference_refused']=True
  else:checks['replaced_draft_reference_refused']=False
  draft=request('review',ready['reference']);assert draft['selected']==[],'trial refuses a nonempty browser selection'
  # Exercise the actual terminal main using a private PTY; references are never
  # command arguments and terminal echo is disabled before secret input.
  code="import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
  if not args.real:
   code+="import api.setup_store as st;import api.setup_manager as mg;import api.setup_preflight as pf;sys.path.insert(0,sys.argv[1]+'/tests/unit');from test_setup import fixture;st.DIRECTORY=Path(sys.argv[2]);mg.RUNTIME=Path(sys.argv[3]);pf.assess=lambda record:fixture(record=record);"
  code+="from api.setup_cli import main;sys.argv=['setup','confirm/start'];raise SystemExit(main())"
  master,slave=pty.openpty();attrs=termios.tcgetattr(slave);attrs[3]&=~termios.ECHO;termios.tcsetattr(slave,termios.TCSANOW,attrs)
  cli=subprocess.Popen(['/usr/bin/python3','-I','-B','-c',code,str(version),str(choices),str(owned)],stdin=slave,stdout=slave,stderr=slave);os.close(slave);os.write(master,(ready['reference']+'\nCONFIRM\n').encode());out=bytearray();deadline=time.monotonic()+30
  while cli.poll() is None and time.monotonic()<deadline:
   if select.select([master],[],[],.1)[0]:
    try:out.extend(os.read(master,4096))
    except OSError:break
   assert len(out)<=16384
  cli.wait(timeout=3);os.close(master);(evidence/'cli.stdout').write_bytes(bytes(out).replace(ready['reference'].encode(),b'<redacted>'));assert cli.returncode==0,'root terminal confirmation failed'
  current=store.load();assert current['revision']==initial['revision']+1 and current['selected']==[];owned_value=json.loads((owned/'owned.json').read_text());assert owned_value['instances']=={}
  checks['actual_root_terminal_confirmation']=True;checks['empty_selection_no_source_authority']=True
  try:request('take',ready['reference'])
  except Exception:checks['taken_draft_replay_refused']=True
  else:checks['taken_draft_replay_refused']=False
  notify('confirmed.json',dict(selected=current['selected'],states={}))
  waitfile('ready-restart.json');publish_view();system('restart',UNITS[0]);new_url=mint();notify('new-session.json',dict(url=new_url,revision=current['revision']))
  browser.wait(timeout=40);r=json.loads((work/'report.json').read_text());report['browser_report']=str(work/'report.json');report['browser_checks']=r['checks'];checks['browser_acceptance']=browser.returncode==0 and r['passed']
  request('revoke_all');report['peak']=system('show',UNITS[0],'--property=MemoryPeak').stdout
  checks['choice_revision_retained']=store.load()==current
  dev.verify(ROOT,args.expected_manifest);checks['source_snapshot_unchanged']=True;report['result']='passed' if all(checks.values()) else 'failed'
 except Exception as e:
  report.update(result='failed',error_type=type(e).__name__,error=str(e)[:150] if isinstance(e,AssertionError) else 'private failure retained')
  import traceback;(evidence/'failure.txt').write_text(traceback.format_exc())
 finally:
  if browser and browser.poll() is None:browser.terminate();browser.wait(timeout=8)
  stop()
  if loaded:
   r=subprocess.run(['/usr/sbin/apparmor_parser','--skip-cache','--remove',str(profile)],capture_output=True);checks['temporary_browser_permission_removed']=r.returncode==0 and profile_name not in Path('/sys/kernel/security/apparmor/profiles').read_text()
  for p in reversed(installed):
   if p.exists():p.unlink()
  system('daemon-reload');checks['normal_nss_unchanged']=inventory()==normal;checks['global_namespace_policy_unchanged']=Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns').read_text()==policy
  
  try:checks['collection_and_history_preserved']=lab.preserved()==before
  except Exception as e:checks['collection_and_history_preserved']=False;report['preservation_error_type']=type(e).__name__
  checks['viewer_stopped']=all(subprocess.run(['/usr/bin/systemctl','is-active','--quiet',u],capture_output=True).returncode!=0 for u in UNITS)
  if not all(checks.values()):report['result']='failed'
  p=evidence/'report.json';p.write_text(json.dumps(report,indent=2));p.chmod(0o600);os.close(lock)
  print(json.dumps(dict(result=report['result'],report=str(p),checks=checks,error=report.get('error'))),flush=True)
 return 0 if report['result']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
