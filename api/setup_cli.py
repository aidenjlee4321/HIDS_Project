"""Root terminal setup review/confirmation. No authority from a browser bearer."""
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import struct
import sys
from api.setup_contract import require,clone,selected,selection_record
from api.pilot_sessions import closed_json,digest
from api.setup_service import CONTROL,config

def request(operation,reference=None):
 require(os.getuid()==0 and os.geteuid()==0 and operation in ('mint','revoke_all','review','take'))
 config();p=Path(CONTROL)
 for parent in p.parents:
  s=parent.lstat();require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022)
 require(p.resolve()==p and stat.S_IMODE(p.parent.stat().st_mode)==0o700)
 s=p.lstat();require(s.st_uid==0 and stat.S_ISSOCK(s.st_mode) and stat.S_IMODE(s.st_mode)==0o600)
 body=dict(version=1,operation=operation)
 if operation in ('review','take'):digest(reference);body['reference']=reference
 else:require(reference is None)
 with socket.socket(socket.AF_UNIX) as c:
  c.settimeout(3);c.connect(str(p));_,uid,_=struct.unpack('3i',c.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));require(uid in (0,pwd.getpwnam('hids-ingest').pw_uid))
  c.sendall(json.dumps(body).encode()+b'\n');c.shutdown(socket.SHUT_WR);data=bytearray()
  while True:
   block=c.recv(4097-len(data))
   if not block:break
   data.extend(block);require(len(data)<=4096)
 value=closed_json(data,{'version','url'} if operation=='mint' else {'version','revoked'} if operation=='revoke_all' else {'version','draft'})
 require(type(value['version']) is int and value['version']==1)
 if operation=='mint':
  prefix='https://127.0.0.1:18765/#grant=';require(type(value['url']) is str and value['url'].startswith(prefix));digest(value['url'][len(prefix):]);return value['url']
 if operation=='revoke_all':require(value['revoked'] is True);return True
 draft=value['draft'];require(type(draft) is dict and set(draft)=={'assessment_id','fingerprint','confirmed','selected'});selection_record(draft['confirmed']);require(selected(draft['selected'])==draft['selected']);return clone(draft)

def main():
 try:
  require(os.getuid()==0 and os.geteuid()==0 and sys.stdin.isatty() and sys.stdout.isatty() and len(sys.argv)==2)
  op=sys.argv[1];require(op in ('mint','revoke_all','review','confirm/start','stop'))
  if op in ('mint','revoke_all'):print(request(op));return 0
  from api.setup_manager import root_lock,manager
  if op=='stop':
   require(input('Stop only HIDS instances owned by this setup? Type STOP: ')=='STOP')
   with root_lock():print(json.dumps(manager().stop()))
   return 0
  reference=input('Private draft review reference: ').strip();draft=request('review',reference)
  # Fixed allowlisted IDs are safe terminal text; never echo raw provider errors.
  print('Selected sources: '+(', '.join(draft['selected']) or 'none'))
  print('Saved choices do not resume collection after restart. No logging settings change.')
  if op=='review':return 0
  require(input('Save these choices and initialize only eligible selected HIDS sources? Type CONFIRM: ')=='CONFIRM')
  with root_lock():
   taken=request('take',reference);require(taken==draft);print(json.dumps(manager().confirm(taken)))
  return 0
 except Exception:
  print('HIDS setup refused or outcome unconfirmed; no automatic retry.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
