"""Explicit D-12b synthetic-only manual acceptance. Root, pinned VM, no data API."""
import argparse
import fcntl
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import pty
import pwd
import select
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
INSTALL=Path('/opt/hids-dashboard-pilot')
UNITS=('hids-dashboard-pilot.service','hids-dashboard-pilot-http.socket','hids-dashboard-pilot-control.socket')
ORIGINAL=('hids-m3.service','hids-m3.socket','hids-m3-health.service','hids-m3-health.timer')

def cmd(*args,**kw):return subprocess.check_output(args,text=True,timeout=20,**kw).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def preserved():
 paths=[*Path('/var/lib/hids/m3').glob('*.sqlite'),*Path('/var/lib/hids/m4').rglob('*'),Path('/etc/hids/m3.json'),Path('/etc/audit/auditd.conf'),*Path('/etc/audit/plugins.d').glob('*.conf')]
 files={str(p):sha(p) for p in paths if p.is_file() and not p.name.endswith('-shm')}
 installed=Path('/var/tmp/hids-m3-workflow/jobs/hids-m3-lab-5571cb8a78dc/run-20261112T010147Z-52bd1c95b1c9/installed.json')
 for row in json.loads(installed.read_text()):
  p=Path(row['target']);assert sha(p)==row['sha256'];files[str(p)]=sha(p)
 source=Path('/root/hids-m3-native-workload.m6s9o0ye/report.json')
 from source_preservation import verify_prefixes
 verify_prefixes(json.loads(source.read_text())['source_before'])
 return {'files':files,'rules':cmd('auditctl','-l'),'units':{u:cmd('systemctl','show',u,'-p','ActiveState','--value') for u in ORIGINAL},'audit':cmd('systemctl','is-active','auditd')}

def own_tree(root):
 for parent,dirs,files in os.walk(root,followlinks=False):
  os.chown(parent,0,0);Path(parent).chmod(0o755)
  for name in dirs:
   p=Path(parent)/name
   if p.is_symlink():os.chown(p,0,0,follow_symlinks=False)
  for name in files:
   p=Path(parent)/name;os.chown(p,0,0,follow_symlinks=False)
   if not p.is_symlink():p.chmod(0o755 if p.stat().st_mode & 0o111 else 0o644)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--build',type=Path,required=True);parser.add_argument('--expected-manifest',required=True);parser.add_argument('--expected-vm-uuid',required=True);args=parser.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()==args.expected_vm_uuid
 sys.path.insert(0,str(ROOT/'scripts'));import dev;dev.verify(ROOT,args.expected_manifest)
 assert all(cmd('systemctl','show',u,'-p','ActiveState','--value')=='inactive' for u in ORIGINAL)
 assert cmd('systemctl','is-active','auditd')=='active'
 assert not Path('/etc/hids/m4.json').exists()
 lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 baseline=preserved();run=Path(tempfile.mkdtemp(prefix='hids-dashboard-acceptance.',dir='/var/tmp'));run.chmod(0o700)
 report={'result':'running','synthetic_only':True,'source_manifest':args.expected_manifest,'checks':{},'browser':[]};created=[];browser=None;secrets=[]
 def save():
  p=run/'report.json';p.write_text(json.dumps(report,indent=2)+'\n');p.chmod(0o600)
 def check(name,value):
  assert value,name;report['checks'][name]=True;save()
 (run/'baseline.json').write_text(json.dumps(baseline));save()
 try:
  reuse=INSTALL.exists()
  if reuse:
   assert INSTALL.stat().st_uid==0 and (INSTALL/'PILOT_MARKER').read_text()=='hids-d12b-synthetic\n'
   for p in INSTALL.rglob('*'):
    info=p.lstat();assert info.st_uid==0 and (p.is_symlink() or not info.st_mode & 0o022)
  assert not Path('/etc/hids/dashboard-pilot.json').exists()
  assert not Path('/run/hids-dashboard-pilot').exists()
  for u in UNITS:
   assert cmd('systemctl','show',u,'-p','LoadState','--value')=='not-found'
   assert not (Path('/run/systemd/system')/u).exists()
  # Tie the build inputs and bundled assets to the verified source snapshot.
  for source in (ROOT/'frontend').rglob('*'):
   if source.is_file():
    assert sha(source)==sha(args.build/'source/frontend'/source.relative_to(ROOT/'frontend')), 'frontend build source differs'
  report['assets']={str(p.relative_to(args.build/'source/frontend/dist')):sha(p) for p in (args.build/'source/frontend/dist').rglob('*') if p.is_file()}
  # Build inputs are frozen into a root-owned runtime copy before execution.
  if not reuse:
   INSTALL.mkdir(mode=0o755)
   shutil.copytree(args.build/'runtime-venv',INSTALL/'venv',symlinks=True)
   (INSTALL/'code/api').mkdir(parents=True)
   (INSTALL/'PILOT_MARKER').write_text('hids-d12b-synthetic\n')
  for p in (ROOT/'api').glob('pilot_*.py'):shutil.copy2(p,INSTALL/'code/api'/p.name)
  if (INSTALL/'assets').exists():
   (INSTALL/'assets').rename(INSTALL/('assets-before-'+run.name))
  shutil.copytree(args.build/'source/frontend/dist',INSTALL/'assets')
  shutil.copy2(ROOT/'packaging/hids-dashboard-access',INSTALL/'hids-dashboard-access')
  (INSTALL/'hids-dashboard-access').chmod(0o755);own_tree(INSTALL)
  cfg=Path('/etc/hids/dashboard-pilot.json');cfg.write_bytes((ROOT/'packaging/dashboard-pilot.example.json').read_bytes());cfg.chmod(0o644);created.append(cfg)
  for u in UNITS:
   p=Path('/run/systemd/system')/u;p.write_bytes((ROOT/'packaging/systemd'/u).read_bytes());p.chmod(0o644);created.append(p)
  cmd('systemctl','daemon-reload')
  # Occupying the exact loopback port must refuse startup, never choose another.
  with socket.socket() as occupied:
   occupied.bind(('127.0.0.1',18765));occupied.listen(1)
   failed=subprocess.run(['systemctl','start',UNITS[1]],capture_output=True,timeout=15)
   check('occupied_port_refused',failed.returncode!=0)
  subprocess.run(['systemctl','reset-failed',UNITS[1]],capture_output=True)
  cmd('systemctl','start',*UNITS)
  sys.path.insert(0,str(INSTALL/'code'))
  from api.pilot_cli import request
  from api.pilot_sessions import closed_json
  def mint():
   url=request('mint');secrets.append(url.split('#grant=')[1]);return url
  for _ in range(50):
   try:url=mint();break
   except Exception:time.sleep(.1)
  else:raise AssertionError('pilot did not become ready')
  token_url=url
  check('root_control_mints_after_ready',True)
  info=Path('/run/hids-dashboard-pilot/control.sock').stat()
  check('root_socket_modes',info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600 and stat.S_IMODE(Path('/run/hids-dashboard-pilot').stat().st_mode)==0o700)
  pid=int(cmd('systemctl','show',UNITS[0],'-p','MainPID','--value'))
  status=Path('/proc')/str(pid)/'status';text=status.read_text();account=pwd.getpwnam('hids-ingest')
  check('unprivileged_zero_capabilities',f'Uid:\t{account.pw_uid}\t{account.pw_uid}\t{account.pw_uid}\t{account.pw_uid}' in text and 'CapEff:\t0000000000000000' in text and 'NoNewPrivs:\t1' in text)
  check('real_data_paths_hidden',not (Path('/proc')/str(pid)/'root/var/lib/hids/m4/store/handoff.sqlite').exists())
  ordinary=pwd.getpwnam('ivy')
  denied="import socket; s=socket.socket(socket.AF_UNIX); s.connect('/run/hids-dashboard-pilot/control.sock')"
  p=subprocess.run(['/usr/bin/python3','-B','-c',denied],user=ordinary.pw_uid,group=ordinary.pw_gid,extra_groups=[],capture_output=True)
  check('ordinary_socket_denied',p.returncode!=0 and b'PermissionError' in p.stderr)
  # The terminal-only CLI cannot be piped, and ordinary UID cannot authorize.
  isolated="import sys;sys.path.insert(0,'/opt/hids-dashboard-pilot/code');from api.pilot_cli import main;raise SystemExit(main())"
  p=subprocess.run(['/usr/bin/python3','-I','-B','-c',isolated,'mint'],capture_output=True)
  check('cli_nonterminal_refused',p.returncode!=0 and b'#grant=' not in p.stdout)
  master,slave=pty.openpty()
  p=subprocess.Popen(['/usr/bin/python3','-I','-B','-c',isolated,'mint'],stdout=slave,stderr=slave,stdin=subprocess.DEVNULL);os.close(slave)
  rc=p.wait(timeout=5)
  data=os.read(master,4096).decode().strip();os.close(master)
  if rc!=0:
   (run/'terminal-cli.txt').write_text(data)
   raise AssertionError('root terminal CLI refused; private diagnostic retained')
  check('root_terminal_cli',data.startswith('http://127.0.0.1:18765/#grant='));secrets.append(data.split('#grant=')[1]);request('revoke_all')
  def http(path,method='GET',body=None,headers=()):
   c=HTTPConnection('127.0.0.1',18765,timeout=5)
   c.putrequest(method,path,skip_host=True,skip_accept_encoding=True)
   for k,v in [('Host','127.0.0.1:18765'),('Sec-Fetch-Site','same-origin'),*headers]:c.putheader(k,v)
   if body is not None:c.putheader('Content-Length',str(len(body)))
   c.endheaders(body);r=c.getresponse();data=r.read();result=(r.status,dict(r.getheaders()),data);c.close();return result
  def redeem(url):
   grant=url.split('#grant=')[1];status,_,body=http('/v0/auth/redeem','POST',json.dumps({'grant':grant}).encode(),[('Origin','http://127.0.0.1:18765'),('Content-Type','application/json')]);assert status==200
   token=json.loads(body)['token'];secrets.append(token);return token
  check('unauthenticated_real_route_absent',http('/v0/events')[0]==404)
  check('no_bearer_refused',http('/v0/pilot')[0]==403)
  t=redeem(mint());idle_start=time.monotonic();idle_token=t
  check('synthetic_api_only',json.loads(http('/v0/pilot',headers=[('Authorization','Bearer '+t)])[2])['synthetic'] is True)
  for headers in ([('Host','evil.example')],[('Origin','http://evil.example')],[('Sec-Fetch-Site','cross-site')],[('Authorization','Bearer '+t)]*2,[('X-Forwarded-Host','127.0.0.1:18765')],[('Cookie','token='+t)]):
   # h11 rejects duplicate Host before ASGI with 400; middleware uses 403.
   assert http('/v0/pilot',headers=headers)[0] in (400,403)
  check('network_header_negatives',True)
  # Exercise framing and deadlines against the actual inherited control listener.
  for payload in (b'{"version":true,"operation":"mint"}\n', b'{"version":1,"operation":"shell"}\n',
                  b'{"version":1,"operation":"mint","extra":1}\n', b'{}\n{}\n', b'x'*4097+b'\n'):
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
    probe.settimeout(5);probe.connect('/run/hids-dashboard-pilot/control.sock');probe.sendall(payload);probe.shutdown(socket.SHUT_WR)
    try:reply=probe.recv(4096)
    except ConnectionResetError:reply=b''
    assert b'#grant=' not in reply
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
   probe.settimeout(5);probe.connect('/run/hids-dashboard-pilot/control.sock');probe.sendall(b'{')
   check('control_slow_request_deadline',b'request denied' in probe.recv(4096))
  check('closed_control_protocol',True)
  with socket.create_connection(('127.0.0.1',18765),timeout=5) as probe:
   probe.sendall(b'POST /v0/auth/redeem HTTP/1.1\r\nHost: 127.0.0.1:18765\r\nOrigin: http://127.0.0.1:18765\r\nSec-Fetch-Site: same-origin\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n{')
   check('http_slow_body_deadline',b'403' in probe.recv(4096))
  expired_url=mint();grant_start=time.monotonic()
  # A root-created deliberately permissive test listener proves the peer check
  # independently of the actual production-mode socket's DAC rejection.
  peer_code="""import asyncio,json,os,socket,struct,sys
sys.path.insert(0,'/opt/hids-dashboard-pilot/code')
from api.pilot_service import Control
from api.pilot_sessions import Sessions
async def go():
 p=sys.argv[1];server=await asyncio.start_unix_server(Control(Sessions(),'http://127.0.0.1:18765',lambda:True).handle,path=p,limit=4096,cleanup_socket=False);os.chmod(p,0o666)
 print('ready',flush=True)
 await asyncio.sleep(5)
 server.close();await server.wait_closed()
asyncio.run(go())"""
  # /var/tmp parent permits traversal; socket is solely a synthetic test fixture.
  peer_path='/var/tmp/hids-dashboard-peer-'+run.name+'.sock'
  p=subprocess.Popen(['/usr/bin/python3','-I','-B','-c',peer_code,peer_path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  assert p.stdout.readline().strip()=='ready'
  client="import socket; s=socket.socket(socket.AF_UNIX);s.settimeout(3);s.connect("+repr(peer_path)+");s.sendall(b'{\"version\":1,\"operation\":\"mint\"}\\n');s.shutdown(socket.SHUT_WR);print(s.recv(4096).decode())"
  result=subprocess.run(['/usr/bin/python3','-B','-c',client],user=ordinary.pw_uid,group=ordinary.pw_gid,extra_groups=[],capture_output=True,text=True,timeout=5)
  check('forged_peer_uid_refused',result.returncode==0 and 'request denied' in result.stdout and '#grant=' not in result.stdout)
  p.wait(timeout=7);Path(peer_path).unlink()
  # Clean, ordinary-user headless Firefox. No browser profile or data-store grants.
  browser_log=(args.build/('browser-'+run.name+'.stderr')).open('x')
  browser=subprocess.Popen(['systemd-run','--user','--scope','--quiet','--collect',str(args.build/'venv/bin/python'),'-B',str(ROOT/'tests/integration/dashboard_browser.py'),str(args.build),run.name],user=ordinary.pw_uid,group=ordinary.pw_gid,extra_groups=[],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=browser_log,text=True,env=dict(os.environ,HOME=ordinary.pw_dir,USER=ordinary.pw_name,LOGNAME=ordinary.pw_name,XDG_RUNTIME_DIR='/run/user/'+str(ordinary.pw_uid),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(ordinary.pw_uid)+'/bus'))
  def receive(timeout=45):
   if not select.select([browser.stdout],[],[],timeout)[0]:raise AssertionError('browser response deadline')
   line=browser.stdout.readline()
   if not line:raise AssertionError('browser exited; private browser diagnostic retained')
   value=json.loads(line);assert value.get('passed',value.get('ready',False)),value;return value
  report['browser_identity']=receive();save()
  def action(kind,**kw):
   browser.stdin.write(json.dumps({'action':kind,**kw})+'\n');browser.stdin.flush();value=receive();report['browser'].append(value);save()
  action('open',url=mint(),expected='Authorized')
  action('refresh')
  action('open',url=mint(),expected='Authorized');action('race_logout')
  action('open',url=mint(),expected='Authorized');request('revoke_all');action('check',expected='Locked')
  # Real process restart invalidates both grant and session while listeners stay.
  restart_url=mint();restart_token=redeem(mint());cmd('systemctl','restart',UNITS[0])
  for _ in range(50):
   if http('/v0/pilot')[0]==403:break
   time.sleep(.1)
  check('restart_old_bearer_refused',http('/v0/pilot',headers=[('Authorization','Bearer '+restart_token)])[0]==403)
  action('open',url=restart_url,expected='Locked')
  action('open',url=mint(),expected='Authorized');action('logout')
  # The earlier idle token was revoked/restarted; use a fresh isolated session
  # for an actual five-minute idle deadline, without background touches.
  idle_token=redeem(mint());idle_start=time.monotonic();expired_url=mint();grant_start=time.monotonic()
  check('browser_acceptance',True)
  report['idle_wait_started']=time.time();save()
  while time.monotonic()-grant_start<60.2:time.sleep(.5)
  action('open',url=expired_url,expected='Locked');check('actual_grant_expiry',True)
  while time.monotonic()-idle_start<300.2:time.sleep(1)
  check('actual_idle_expiry',http('/v0/pilot',headers=[('Authorization','Bearer '+idle_token)])[0]==403)
  check('error_responses_redacted',all(secret not in http('/v0/pilot')[2].decode() for secret in secrets))
  report['result']='passed'
 except Exception as exc:
  report['result']='failed'
  report['error_type']=type(exc).__name__;report['error']=str(exc)[:160] if isinstance(exc,AssertionError) else 'private traceback retained'
  import traceback;(run/'failure.txt').write_text(traceback.format_exc())
 finally:
  if browser is not None:
   try:browser.stdin.write('{"action":"stop"}\n');browser.stdin.flush();browser.wait(timeout=15)
   except Exception:browser.kill();browser.wait()
  if created:
   journal=subprocess.run(['journalctl','-u',UNITS[0],'--no-pager','-o','cat'],capture_output=True,text=True,timeout=15).stdout
   (run/'unit-journal.txt').write_text(journal)
   report['credentials_absent_from_unit_log']=all(secret not in journal for secret in secrets)
   subprocess.run(['systemctl','stop',*UNITS],capture_output=True,timeout=20)
   subprocess.run(['systemctl','reset-failed',*UNITS],capture_output=True)
   report['pilot_stopped']=all(cmd('systemctl','show',u,'-p','ActiveState','--value')=='inactive' for u in UNITS)
   for path in created:path.unlink()
   cmd('systemctl','daemon-reload')
   parent=Path('/run/hids-dashboard-pilot')
   if parent.exists() and not any(parent.iterdir()):parent.rmdir()
  report['production_preserved']=preserved()==baseline
  if report.get('pilot_stopped') is not True or not report['production_preserved'] or not report.get('credentials_absent_from_unit_log'):report['result']='failed'
  save();os.close(lock)
  print(json.dumps({'result':report['result'],'report':str(run/'report.json'),'error':report.get('error'),'checks':len(report['checks']),'production_preserved':report['production_preserved']}),flush=True)
 return 0 if report['result']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
