"""Manual HTTPS setup snapshot/draft service, never a privileged orchestrator."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import struct
import sys
from api.pilot_service import trusted,listeners
from api.pilot_sessions import Denied,closed_json
from api.setup_contract import validate_view,require
from api.setup_store import safe_read
from api.setup_sessions import SetupSessions
from api.tls_leaf import validated_context

CONFIG=Path('/etc/hids/dashboard-setup.json');VIEW=Path('/etc/hids/setup-preview/view.json')
CONTROL='/run/hids-dashboard-setup/control.sock';INSTALL=Path('/opt/hids-dashboard-setup')
CERT=Path('/etc/hids/dashboard-history-tls/leaf.pem');KEY=Path('/etc/hids/dashboard-history-tls/leaf.key')

def config():
 for p in ('/etc','/etc/hids'):trusted(p,True)
 gid=pwd.getpwnam('hids-ingest').pw_gid
 value=closed_json(safe_read(CONFIG,0,gid,0o440,2048),{'version','port','certificate_sha256','view_sha256'})
 require(type(value['version']) is int and value['version']==1 and type(value['port']) is int and value['port']==18765)
 import re
 require(all(type(value[k]) is str and re.fullmatch('[0-9a-f]{64}',value[k]) for k in ('certificate_sha256','view_sha256')));return value

def load_view(cfg):
 gid=pwd.getpwnam('hids-ingest').pw_gid
 require(VIEW.parent.resolve()==VIEW.parent);s=VIEW.parent.stat();require(s.st_uid==0 and s.st_gid==gid and stat.S_IMODE(s.st_mode)==0o750)
 for p in VIEW.parent.parents:trusted(p,True)
 raw=safe_read(VIEW,0,gid,0o440,65536);require(hashlib.sha256(raw).hexdigest()==cfg['view_sha256'])
 from api.setup_contract import FORMAT
 value=closed_json(raw,{'format','assessment_id','assessed_at','fingerprint','confirmed','sources'});return validate_view(value)

class SetupControl:
 def __init__(self,state,ready):self.state=state;self.ready=ready;self.active=0
 async def handle(self,reader,writer):
  counted=False
  try:
   _,uid,_=struct.unpack('3i',writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
   require(uid==0 and self.active<4 and self.ready());self.active+=1;counted=True
   data=await asyncio.wait_for(reader.readuntil(b'\n'),2);require(len(data)<=4096 and not await asyncio.wait_for(reader.read(1),2))
   from api.pilot_sessions import closed_json
   # Determine shape without accepting extra/duplicate keys.
   value=json.loads(data);require(type(value) is dict)
   operation=value.get('operation');keys={'version','operation','reference'} if operation in ('review','take') else {'version','operation'}
   value=closed_json(data,keys);require(type(value['version']) is int and value['version']==1)
   if operation=='mint':out=dict(version=1,url='https://127.0.0.1:18765/#grant='+self.state.mint())
   elif operation=='revoke_all':self.state.revoke_all();out=dict(version=1,revoked=True)
   elif operation in ('review','take'):out=dict(version=1,draft=self.state.review(value['reference'],consume=operation=='take'))
   else:raise Denied()
   raw=json.dumps(out,separators=(',',':')).encode()+b'\n';require(len(raw)<=4096);writer.write(raw);await asyncio.wait_for(writer.drain(),2)
  except Exception:
   try:writer.write(b'{"error":"request denied"}\n');await asyncio.wait_for(writer.drain(),1)
   except Exception:pass
  finally:
   if counted:self.active-=1
   writer.close()
   try:await asyncio.wait_for(writer.wait_closed(),1)
   except Exception:pass

async def run():
 import uvicorn
 from api.setup_app import make_app
 cfg=config();gid=pwd.getpwnam('hids-ingest').pw_gid;socks=listeners(18765,control_path=CONTROL)
 def tls():return validated_context(CERT,KEY,cfg['certificate_sha256'],gid)
 ctx=tls()
 try:view=load_view(cfg)
 except Exception:view=None
 state=SetupSessions(view,mint_check=tls);app,state=make_app('127.0.0.1:18765',INSTALL/'assets',view,state)
 conf=uvicorn.Config(app,access_log=False,log_config=None,log_level='critical',proxy_headers=False,server_header=False,date_header=False,workers=1,reload=False,limit_concurrency=16,timeout_keep_alive=2,timeout_graceful_shutdown=3,h11_max_incomplete_event_size=8192);conf.load();conf.ssl=ctx
 server=uvicorn.Server(conf);task=asyncio.create_task(server.serve(sockets=[socks['http']]))
 unix=await asyncio.start_unix_server(SetupControl(state,lambda:server.started and not server.should_exit).handle,sock=socks['control'],limit=4096,cleanup_socket=False)
 try:
  while not task.done():state.housekeeping();await asyncio.sleep(1)
  await task
 finally:
  state.revoke_all();unix.close();await unix.wait_closed();server.should_exit=True
  if not task.done():await task

def main():
 try:
  require(len(sys.argv)==1 and os.environ.get('WEB_CONCURRENCY','1')=='1' and 'UVICORN_RELOAD' not in os.environ);asyncio.run(run());return 0
 except Exception:print('HIDS setup refused or stopped',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
