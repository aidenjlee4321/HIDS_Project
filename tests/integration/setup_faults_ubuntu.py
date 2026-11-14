"""Root config crash/VFS and actual M3 control IPC, synthetic stores only."""
import json
import os
from pathlib import Path
import pwd
import grp
import socket
import subprocess
import sys
import tempfile
import time
from api.setup_contract import require,canonical,empty_record
from api.setup_store import _Store
ROOT=Path(__file__).resolve().parents[2]

M3_CHILD=r'''import json,os,signal,socket,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from engine.ingestion.m3_runtime import Runtime
from engine.ingestion.m3_service import Service
from engine.ingestion.m2_receiver import Listener,PeerPolicy
runtime=Runtime(Path(sys.argv[2]),sys.argv[3],max_activations=16,max_pages=512,position_limit=1024)
control=socket.socket(fileno=int(sys.argv[4]));data=Listener(Path(sys.argv[5]),os.getuid(),int(sys.argv[6]));stopped=[False]
signal.signal(signal.SIGTERM,lambda *_:stopped.__setitem__(0,True))
service=Service(runtime,data.sock,control,PeerPolicy(993,970),stopped=lambda:stopped[0])
print('ready',flush=True)
try:service.run()
finally:service.close();data.close();control.close();runtime.close()
'''

def run_faults(root,code_root):
 require(os.getuid()==0);gid=pwd.getpwnam('hids-ingest').pw_gid;results={}
 # All deaths occur before manager activation, using the actual immutable writer.
 for point in ('before_file_sync','before_publish','after_publish','after_directory_sync'):
  d=root/point;d.mkdir(mode=0o750);os.chown(d,0,gid)
  child="import os,signal,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from api.setup_store import _Store;store=_Store(Path(sys.argv[2]),0,int(sys.argv[3]),fault=lambda p:os.kill(os.getpid(),signal.SIGKILL) if p==sys.argv[4] else None);store.save([],0);raise AssertionError('kill point missed')"
  p=subprocess.run(['/usr/bin/python3','-I','-B','-c',child,str(code_root),str(d),str(gid),point],capture_output=True,timeout=10);require(p.returncode==-9)
  latest=_Store(d,0,gid).load();require(latest['revision']==(0 if point in ('before_file_sync','before_publish') else 1));results[point]=True
 # Real read-only and ENOSPC happen only in a private mount namespace/tmpfs.
 vfs=r'''import os,sys,subprocess,errno
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from api.setup_store import _Store
root=Path(sys.argv[2]);kind=sys.argv[3];gid=int(sys.argv[4])
if kind=='full':subprocess.run(['/usr/bin/mount','-t','tmpfs','-o','size=64k,nr_inodes=64','tmpfs',str(root)],check=True)
d=root/'choices';d.mkdir(mode=0o750);os.chown(d,0,gid);store=_Store(d,0,gid)
if kind=='readonly':
 subprocess.run(['/usr/bin/mount','--bind',str(d),str(d)],check=True);subprocess.run(['/usr/bin/mount','-o','remount,bind,ro',str(d)],check=True)
else:
 fd=os.open(root/'filler',os.O_CREAT|os.O_WRONLY,0o600)
 try:
  try:
   while True:os.write(fd,bytes(4096))
  except OSError as e:assert e.errno==errno.ENOSPC
 finally:os.close(fd)
try:store.save([],0)
except OSError as e:assert e.errno==(errno.EROFS if kind=='readonly' else errno.ENOSPC)
else:raise AssertionError('VFS failure not exercised')
assert store.load()['revision']==0
print('passed')
'''
 for kind in ('readonly','full'):
  d=root/('vfs-'+kind);d.mkdir(mode=0o700)
  p=subprocess.run(['/usr/bin/unshare','--mount','--propagation','private','--','/usr/bin/python3','-I','-B','-c',vfs,str(code_root),str(d),kind,str(gid)],capture_output=True,text=True,timeout=15)
  (root/(kind+'.stderr')).write_text(p.stderr);require(p.returncode==0 and p.stdout.strip()=='passed');require(not (d/'filler').exists());results['private_'+kind]=True
 # Real source-control messages/credentials against the actual M3 Service. Unit
 # starts/stops are an internal stub; no host M3 unit or native reader is started.
 import engine.ingestion.m3_control as client
 from api.setup_manager import AuditAdapter
 backend=pwd.getpwnam('hids-ingest');ipc=grp.getgrnam('hids-ipc').gr_gid
 d=root/'m3-ipc';d.mkdir(mode=0o755);state=d/'state';state.mkdir(mode=0o700);os.chown(state,backend.pw_uid,backend.pw_gid)
 data=d/'data';data.mkdir(mode=0o750);os.chown(data,backend.pw_uid,ipc)
 control=d/'control';control.mkdir(mode=0o755);endpoint=control/'control.sock'
 sock=socket.socket(socket.AF_UNIX);sock.bind(str(endpoint));endpoint.chmod(0o600);sock.listen(8)
 source='44444444-4444-4444-8444-444444444444'
 child=subprocess.Popen(['/usr/bin/python3','-I','-B','-c',M3_CHILD,str(code_root),str(state),source,str(sock.fileno()),str(data/'data.sock'),str(ipc)],pass_fds=(sock.fileno(),),user=backend.pw_uid,group=backend.pw_gid,extra_groups=[ipc],stdout=subprocess.PIPE,stderr=(root/'m3.stderr').open('x'),text=True)
 original=client.ENDPOINT;client.ENDPOINT=endpoint
 class StubUnits(AuditAdapter):
  def __init__(self):self.running=False;self.calls=[]
  def active(self,name):return self.running
  def command(self,*args):self.calls.append(args);self.running=args[0]=='start'
  def owned_readers_absent(self,entry):return True  # This fixture has no native reader.
 try:
  require(child.stdout.readline().strip()=='ready');sock.close();adapter=StubUnits();entry=dict(source=source,activation='55555555-5555-4555-8555-555555555555',generation=None,state='intent')
  require(adapter.initialize(entry)=='initialized_delivery_unproven');require(entry['generation'] is not None);results['actual_root_m3_activate_ipc']=True
  wrong=dict(entry,activation='66666666-6666-4666-8666-666666666666');before=list(adapter.calls)
  try:adapter.stop(wrong)
  except Exception:results['unowned_m3_scope_refused']=True
  else:raise AssertionError('wrong scope accepted')
  require(adapter.calls==before);require(adapter.stop(entry));results['actual_root_m3_deactivate_ipc']=True
  require(client.request(dict(version=3,command='status'))['interval']['state']=='revoked')
 finally:
  client.ENDPOINT=original
  if child.poll() is None:child.terminate()
  child.wait(timeout=8);require(child.returncode==0)
 # Deliberately public synthetic socket tests the peer check independently
 # of the real control socket's root-only directory and permissions.
 peer=root/'peer.sock';listener=socket.socket(socket.AF_UNIX);listener.bind(str(peer));peer.chmod(0o666);listener.listen(8)
 peer_code=r"""import asyncio,json,os,socket,sys
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[1]+'/tests/unit')
from api.setup_sessions import SetupSessions
from api.setup_service import SetupControl
from test_setup import fixture
async def main():
 state=SetupSessions(fixture());server=await asyncio.start_unix_server(SetupControl(state,lambda:True).handle,sock=socket.socket(fileno=int(sys.argv[2])),cleanup_socket=False)
 print('ready',flush=True)
 await asyncio.to_thread(sys.stdin.readline);state.revoke_all();server.close();await server.wait_closed()
asyncio.run(main())
"""
 server=subprocess.Popen(['/usr/bin/python3','-I','-B','-c',peer_code,str(code_root),str(listener.fileno())],pass_fds=(listener.fileno(),),user=backend.pw_uid,group=backend.pw_gid,extra_groups=[],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'peer.stderr').open('x'),text=True)
 try:
  require(server.stdout.readline().strip()=='ready');listener.close()
  # Use a structured generated script to preserve the wire newline exactly.
  probe="import socket,json,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);s.sendall((json.dumps(dict(version=1,operation='mint'))+chr(10)).encode());s.shutdown(socket.SHUT_WR);v=json.loads(s.recv(4096));assert set(v)=={'error'};print('denied')"
  ordinary=pwd.getpwnam('ivy');negative=subprocess.run(['/usr/bin/python3','-B','-c',probe,str(peer)],user=ordinary.pw_uid,group=ordinary.pw_gid,extra_groups=[],capture_output=True,text=True,timeout=5);require(negative.returncode==0 and negative.stdout.strip()=='denied');results['ordinary_peer_denied_even_public_synthetic_socket']=True
  with socket.socket(socket.AF_UNIX) as c:
   c.settimeout(3);c.connect(str(peer));c.sendall((json.dumps(dict(version=1,operation='mint'))+'\n').encode());c.shutdown(socket.SHUT_WR);value=json.loads(c.recv(4096));require(set(value)=={'version','url'});results['root_peer_permitted']=True
 finally:
  server.stdin.write('stop\n');server.stdin.flush();server.wait(timeout=5);require(server.returncode==0)
 return results
