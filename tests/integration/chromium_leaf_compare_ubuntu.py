"""Bounded synthetic comparison with temporary exact-path AppArmor permission."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
API_SERVER = r'''import asyncio,json,os,socket,ssl,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from api.pilot_app import make_app
from api.pilot_service import Control
from api.tls_leaf import validated_context
import uvicorn
async def main():
 tcp=socket.socket(fileno=int(sys.argv[2]));control_socket=socket.socket(fileno=int(sys.argv[3]))
 authority='127.0.0.1:'+str(tcp.getsockname()[1]);fixture=Path(sys.argv[4])
 ctx=validated_context(fixture/'valid.pem',fixture/'valid.key',sys.argv[5],int(sys.argv[6]))
 app,state=make_app(authority,Path('/opt/hids-dashboard-pilot/assets'),scheme='https')
 config=uvicorn.Config(app,access_log=False,log_config=None,log_level='critical',proxy_headers=False,server_header=False,date_header=False,workers=1,reload=False,timeout_keep_alive=2,timeout_graceful_shutdown=3,limit_concurrency=16,h11_max_incomplete_event_size=8192)
 config.load();config.ssl=ctx
 server=uvicorn.Server(config);task=asyncio.create_task(server.serve(sockets=[tcp]))
 unix=await asyncio.start_unix_server(Control(state,'https://'+authority,lambda:server.started and not server.should_exit).handle,sock=control_socket,limit=4096,cleanup_socket=False)
 try:
  for _ in range(100):
   if server.started:break
   if task.done():await task;raise RuntimeError('API refused')
   await asyncio.sleep(.05)
  assert server.started
  print(json.dumps({'ready':True,'uid':os.getuid(),'groups':os.getgroups()}),flush=True)
  await asyncio.to_thread(sys.stdin.readline)
 finally:
  state.revoke_all();server.should_exit=True;unix.close();await unix.wait_closed();await task
asyncio.run(main())
'''

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--browser-build',type=Path,required=True);parser.add_argument('--tools',type=Path,required=True);parser.add_argument('--expected-manifest',required=True);parser.add_argument('--api',action='store_true');args=parser.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path.insert(0,str(ROOT/'scripts'));import dev;dev.verify(ROOT,args.expected_manifest)
 sys.path.insert(0,str(ROOT/'tests/integration'));import tls_acceptance_ubuntu as tls;import dashboard_pilot_ubuntu as lab
 lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 before=lab.preserved();assert all(x=='inactive' for x in before['units'].values())
 namespace=Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns');namespace_before=namespace.read_text()
 # Record the actual normal NSS locations without creating/changing either.
 normal={}
 for directory in (Path('/home/ivy/.pki/nssdb'),Path('/home/ivy/.local/share/pki/nssdb')):
  normal[str(directory)]={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob('*') if p.is_file()} if directory.exists() else None
 root=Path(tempfile.mkdtemp(prefix='hids-browser-leaf.',dir='/opt'));root.chmod(0o755)
 profile_name='hids-browser-leaf-'+root.name.split('.')[-1].replace('_','x');loaded=False;server=None;api_server=None
 report={'result':'running','synthetic_only':True,'source_manifest':args.expected_manifest}
 def normal_now():
  return {str(d):{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in d.glob('*') if p.is_file()} if d.exists() else None for d in map(Path,normal)}
 try:
  browsers=list((args.browser_build/'browsers').glob('chromium-*/chrome-linux-arm64'));assert len(browsers)==1
  shutil.copytree(browsers[0],root/'browser',symlinks=True)
  for parent,dirs,files in os.walk(root/'browser'):
   Path(parent).chmod(0o755)
   for name in dirs+files:
    p=Path(parent)/name
    if p.is_symlink():
     assert str(p.resolve()).startswith(str(root/'browser')+'/');os.chown(p,0,0,follow_symlinks=False)
    elif p.is_file():p.chmod(0o755 if p.stat().st_mode&0o111 else 0o644)
  binary=root/'browser/chrome';report['browser_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
  profile=root/'apparmor.profile';profile.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile '+profile_name+' '+str(binary)+' flags=(unconfined) {\n userns,\n}\n')
  subprocess.run(['/usr/sbin/apparmor_parser','--skip-cache','--replace',str(profile)],check=True,capture_output=True);loaded=True
  assert profile_name in Path('/sys/kernel/security/apparmor/profiles').read_text()
  fixture=Path('/opt/hids-tls-synthetic.8m5rf1fp');backend=pwd.getpwnam('hids-ingest');user=pwd.getpwnam('ivy')
  fingerprint=hashlib.sha256(subprocess.check_output(['/usr/bin/openssl','x509','-in',str(fixture/'valid.pem'),'-outform','DER'])).hexdigest()
  server=subprocess.Popen(['/usr/bin/python3','-B','-c',tls.SERVER,str(fixture/'code'),str(fixture),str(backend.pw_gid),fingerprint],user=backend.pw_uid,group=backend.pw_gid,extra_groups=[],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'server.stderr').open('x'),text=True)
  ports=json.loads(server.stdout.readline());report['ports']=ports
  work=Path(tempfile.mkdtemp(prefix='leaf-test.',dir=args.browser_build));os.chown(work,user.pw_uid,user.pw_gid);work.chmod(0o700)
  for name in ('valid','expired'):
   p=work/(name+'.pem');shutil.copyfile(fixture/(name+'.pem'),p);os.chown(p,user.pw_uid,user.pw_gid);p.chmod(0o600)
  command={}
  if args.api:
   code=root/'api-code/api';code.mkdir(parents=True)
   for source in (ROOT/'api').glob('*.py'):shutil.copyfile(source,code/source.name)
   for parent,dirs,files in os.walk(root/'api-code'):
    Path(parent).chmod(0o755)
    for name in files:(Path(parent)/name).chmod(0o644)
   private=root/'control';private.mkdir(mode=0o700)
   tcp=socket.socket();tcp.bind(('127.0.0.1',0));tcp.listen(8);port=tcp.getsockname()[1]
   control=socket.socket(socket.AF_UNIX);control.bind(str(private/'auth.sock'));(private/'auth.sock').chmod(0o600);control.listen(8)
   api_server=subprocess.Popen(['/opt/hids-dashboard-pilot/venv/bin/python','-I','-B','-c',API_SERVER,str(root/'api-code'),str(tcp.fileno()),str(control.fileno()),str(fixture),fingerprint,str(backend.pw_gid)],pass_fds=(tcp.fileno(),control.fileno()),user=backend.pw_uid,group=backend.pw_gid,extra_groups=[],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'api.stderr').open('x'),text=True)
   tcp.close();control.close();identity=json.loads(api_server.stdout.readline());assert identity['ready'] and identity['uid']==backend.pw_uid and set(identity['groups'])<={backend.pw_gid}
   report['api_identity']=identity;ports['api']=port
   with socket.socket(socket.AF_UNIX) as client:
    client.settimeout(3);client.connect(str(private/'auth.sock'));peer=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));assert peer[1] in (0,backend.pw_uid)
    client.sendall(b'{"version":1,"operation":"mint"}\n');client.shutdown(socket.SHUT_WR)
    data=bytearray()
    while True:
     block=client.recv(4096)
     if not block:break
     data.extend(block);assert len(data)<=4096
   grant=json.loads(data);assert grant['version']==1 and grant['url'].startswith('https://127.0.0.1:'+str(port)+'/#grant=')
   command={'url':grant['url']}
  env=dict(os.environ,PLAYWRIGHT_BROWSERS_PATH=str(args.browser_build/'browsers'))
  child=subprocess.run([str(args.browser_build/'venv/bin/python'),'-B',str(ROOT/'tests/integration/chromium_leaf_browser.py'),str(work),str(args.tools),json.dumps(ports),str(binary)],user=user.pw_uid,group=user.pw_gid,extra_groups=[],env=env,input=json.dumps(command)+'\n',stdout=(root/'browser.stdout').open('x'),stderr=(root/'browser.stderr').open('x'),text=True,timeout=120)
  result=json.loads((work/'report.json').read_text());report['browser']=result;report['browser_report']=str(work/'report.json')
  assert child.returncode==0 and result['passed'],'browser comparison failed'
  report['result']='passed'
 except Exception as exc:
  report['result']='failed';report['error_type']=type(exc).__name__;report['error']=str(exc)[:150] if isinstance(exc,AssertionError) else 'private failure retained'
  import traceback;(root/'failure.txt').write_text(traceback.format_exc())
 finally:
  if api_server:
   try:api_server.stdin.write('stop\n');api_server.stdin.flush();api_server.wait(timeout=8)
   except Exception:api_server.kill();api_server.wait()
   report['api_server_stopped']=api_server.returncode==0
  if server:
   try:server.stdin.write('stop\n');server.stdin.flush();server.wait(timeout=8)
   except Exception:server.kill();server.wait()
   report['tls_server_stopped']=server.returncode==0
  if loaded:
   result=subprocess.run(['/usr/sbin/apparmor_parser','--skip-cache','--remove',str(root/'apparmor.profile')],capture_output=True)
   report['temporary_profile_removed']=result.returncode==0 and profile_name not in Path('/sys/kernel/security/apparmor/profiles').read_text()
  report['global_namespace_policy_unchanged']=namespace.read_text()==namespace_before
  report['normal_nss_unchanged']=normal_now()==normal
  report['production_preserved']=lab.preserved()==before
  if args.api and report.get('api_server_stopped') is not True:report['result']='failed'
  if not all(report.get(k) is True for k in ('tls_server_stopped','temporary_profile_removed','global_namespace_policy_unchanged','normal_nss_unchanged','production_preserved')):report['result']='failed'
  p=root/'report.json';p.write_text(json.dumps(report,indent=2));p.chmod(0o600);os.close(lock)
  print(json.dumps({'result':report['result'],'report':str(p),'error':report.get('error'),'production_preserved':report['production_preserved']}),flush=True)
 return 0 if report['result']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
