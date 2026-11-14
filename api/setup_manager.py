"""One-shot UID-0 configuration/activation coordinator. Never used by HTTP."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import pwd
import secrets
import select
import signal
import math
import stat
import subprocess
import time
import uuid
from api.setup_contract import require,selected,selection_record,REGISTRY_HASH,canonical,clone
from api.setup_store import root_store,safe_read
from api import setup_preflight

RUNTIME=Path('/run/hids-setup')
HELD=('intent','initialized_delivery_unproven','initialization_unconfirmed','stop_unconfirmed')

@contextlib.contextmanager
def root_lock():
 require(os.getuid()==0 and os.geteuid()==0)
 p=RUNTIME;s=p.lstat();require(p.resolve()==p and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700 and stat.S_ISDIR(s.st_mode))
 fd=os.open(p/'control.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,0o600)
 try:
  s=os.fstat(fd);require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
 finally:os.close(fd)

class Ownership:
 def load(self):
  path=RUNTIME/'owned.json'
  if not path.exists():return dict(version=1,revision=0,instances={})
  from api.pilot_sessions import closed_json
  value=closed_json(safe_read(path,0,0,0o600,4096),{'version','revision','instances'})
  require(type(value['version']) is int and value['version']==1 and type(value['revision']) is int and 0<=value['revision']<=16 and type(value['instances']) is dict and set(value['instances'])<={'audit_exec','proc_lifecycle'})
  for entry in value['instances'].values():
   require(type(entry) is dict and set(entry)=={'activation','source','generation','state'} and entry['state'] in (*HELD,'stopped','initialization_failed'))
   for key in ('activation','source','generation'):
    require(key=='generation' and entry[key] is None or type(entry[key]) is str and str(uuid.UUID(entry[key]))==entry[key])
  return value
 def write(self,value):
  raw=canonical(value).encode();require(len(raw)<=4096);p=RUNTIME/('pending-'+secrets.token_hex(16));fd=os.open(p,os.O_WRONLY|os.O_EXCL|os.O_CREAT|os.O_NOFOLLOW,0o600)
  try:
   offset=0
   while offset<len(raw):n=os.write(fd,raw[offset:]);require(n>0);offset+=n
   os.fsync(fd);os.rename(p,RUNTIME/'owned.json');d=os.open(RUNTIME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
   try:os.fsync(d)
   finally:os.close(d)
  finally:
   os.close(fd)
   if p.exists():p.unlink()

class AuditAdapter:
 def command(self,*args):return subprocess.run(['/usr/bin/systemctl',*args],check=True,capture_output=True,timeout=8)
 def active(self,name):return setup_preflight.unit(name).get('ActiveState')!='inactive'
 def prepare(self):
  # Configuration only; no receiver constructor, socket or source initialization.
  from engine.ingestion.m3_service import load_config
  return dict(activation=str(uuid.uuid4()),source=load_config('/etc/hids/m3.json')['source_id'],generation=None,state='intent')
 def initialize(self,entry):
  from engine.ingestion.m3_control import request
  require(all(not self.active(u) for u in setup_preflight.AUDIT_UNITS))
  self.command('start','hids-m3.socket','hids-m3.service')
  status=request(dict(version=3,command='status'));require(status.get('result')=='status' and status.get('source')==entry['source'])
  interval=status.get('interval');require(interval is None or interval.get('state') in ('interrupted','revoked'))
  result=request(dict(version=3,command='activate',source=entry['source'],activation=entry['activation']));require(result==dict(version=3,result='activated',activation=entry['activation']))
  status=request(dict(version=3,command='status'));interval=status.get('interval');require(status.get('result')=='status' and status.get('source')==entry['source'] and interval and interval.get('activation')==entry['activation'])
  entry['generation']=interval['generation'];require(str(uuid.UUID(entry['generation']))==entry['generation']);self.command('start','hids-m3-health.timer');return 'initialized_delivery_unproven'
 def owned_readers_absent(self,entry):
  # Post-confirmation cleanup of this exact HIDS activation only. No unrelated
  # process arguments are read/retained; no source payload, signal or remediation.
  uid=pwd.getpwnam('hids-audit').pw_uid
  for p in Path('/proc').iterdir():
   if not p.name.isdigit():continue
   try:
    if p.stat().st_uid!=uid:continue
    if os.readlink(p/'exe') not in ('/usr/lib/hids/hids-audit-plugin','/usr/lib/hids/hids-audit-plugin (deleted)'):continue
    with (p/'cmdline').open('rb') as f:raw=f.read(2049)
    require(len(raw)<=2048);args=raw.split(b'\0')
    if len(args)>3 and args[2].decode('ascii')==entry['activation']:return False
   except (FileNotFoundError,ProcessLookupError):continue
  return True
 def stop(self,entry):
  from engine.ingestion.m3_control import request
  if self.active('hids-m3.service'):
   status=request(dict(version=3,command='status'));interval=status.get('interval')
   require(status.get('result')=='status' and status.get('source')==entry['source'])
   if interval is not None and interval.get('activation')==entry['activation']:
    require(entry['generation'] is None or interval.get('generation')==entry['generation'])
    response=request(dict(version=3,command='deactivate',source=entry['source'],activation=entry['activation']));require(response==dict(version=3,result='deactivated',activation=entry['activation']))
    status=request(dict(version=3,command='status'));require(status.get('reader_connected') is False and status.get('interval',{}).get('activation')==entry['activation'] and status['interval'].get('state')=='revoked')
   else:
    # An unmatched interval is not ours to stop, even if currently inactive.
    raise ValueError('owned source outcome unconfirmed')
  end=time.monotonic()+3
  while not self.owned_readers_absent(entry):
   require(time.monotonic()<end);time.sleep(.05)
  self.command('stop','hids-m3-health.timer','hids-m3-health.service','hids-m3.service','hids-m3.socket')
  return all(not self.active(u) for u in setup_preflight.AUDIT_UNITS)

class ProcessAdapter:
 @contextlib.contextmanager
 def owner_lock(self):
  from engine.ingestion import process_control as p
  require(os.getuid()==os.geteuid()==0);p.runtime_directory()
  fd=os.open(p.RUNTIME/'owner.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
  try:
   s=os.fstat(fd);require(s.st_uid==0 and stat.S_ISREG(s.st_mode) and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600)
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
  finally:os.close(fd)
 def cancel_pending(self,entry):
  from engine.ingestion import process_control as p
  with self.owner_lock():
   try:grant=p.c.decode(p.trusted(p.GRANT,4096,0o600))
   except FileNotFoundError:return False
   p.c.keys(grant,'version source_id activation_id generation expires')
   require(type(grant['version']) is int and grant['version']==1 and type(grant['expires']) in (int,float) and math.isfinite(grant['expires']) and grant['expires']>0)
   require(all(grant[k]==entry[e] for k,e in (('source_id','source'),('activation_id','activation'),('generation','generation'))))
   p.GRANT.unlink() # Revoke only this unconsumed one-use authorization, not history.
   fd=os.open(p.RUNTIME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
   try:os.fsync(fd)
   finally:os.close(fd)
   # Revocation is safe under the consuming runtime's lock even if an unknown
   # component is active/failed. That does not prove those components stopped.
   return all(setup_preflight.unit(u).get('ActiveState')=='inactive' for u in (p.UNIT,*p.PARTS))
 def prepare(self):
  from engine.ingestion.process_control import configuration
  return dict(activation=str(uuid.uuid4()),source=configuration()['source_id'],generation=str(uuid.uuid4()),state='intent')
 def initialize(self,entry):
  from engine.ingestion import process_control as p
  require(setup_preflight.unit(p.UNIT).get('ActiveState')=='inactive')
  p.authorize(entry)
  subprocess.run(['/usr/bin/systemctl','start',p.UNIT],check=True,capture_output=True,timeout=8)
  end=time.monotonic()+5
  while time.monotonic()<end:
   try:
    state=json.loads(p.trusted(p.STATUS,4096,0o600))
    if not all(state[k]==entry[k] for k in ('source','activation','generation')):
     require(state['state'] in ('stopped','failed'))
     time.sleep(.05);continue
    if state['state']=='initialized_delivery_unproven':return 'initialized_delivery_unproven'
    if state['state'] in ('failed','stopped'):return 'initialization_failed'
   except FileNotFoundError:pass
   time.sleep(.05)
  return 'initialization_unconfirmed'
 def stop(self,entry):
  from engine.ingestion import process_control as p
  try:
   if self.cancel_pending(entry):return True
  except BlockingIOError:pass # An active owner is checked by live invocation below.
  state=json.loads(p.trusted(p.STATUS,4096,0o600))
  require(all(state[k]==entry[k] for k in ('source','activation','generation')))
  scope=p.runtime_scope()
  if scope['ActiveState']=='active':
   import re
   require(state.get('version')==2 and type(state.get('runtime_pid')) is int and state['runtime_pid']>0 and type(state.get('runtime_invocation')) is str and re.fullmatch('[0-9a-f]{32}',state['runtime_invocation']))
   require(state['runtime_pid']==scope['MainPID'] and state['runtime_invocation']==scope['InvocationID'])
   fd=os.pidfd_open(scope['MainPID'])
   try:
    require(p.runtime_scope()==scope)
    signal.pidfd_send_signal(fd,signal.SIGTERM)
    require(bool(select.select([fd],[],[],15)[0]))
   finally:os.close(fd)
  with self.owner_lock():
   deadline=time.monotonic()+2;scope=p.runtime_scope()
   while scope['ActiveState'] not in ('inactive','failed'):
    require(scope['InvocationID']==state.get('runtime_invocation') and time.monotonic()<deadline)
    time.sleep(.02);scope=p.runtime_scope()
   require(scope['MainPID']==0)
   # The runtime cleans its own parts before exit. Unknown leftovers are never
   # stopped merely because an older status file names this activation.
   require(all(setup_preflight.unit(u).get('ActiveState')=='inactive' for u in p.PARTS))
   state=json.loads(p.trusted(p.STATUS,4096,0o600));require(all(state[k]==entry[k] for k in ('source','activation','generation')))
   if scope['ActiveState']=='failed':
    require(state.get('runtime_invocation')==scope['InvocationID'])
    subprocess.run(['/usr/bin/systemctl','reset-failed',p.UNIT],check=True,capture_output=True,timeout=3)
   return state['state'] in ('stopped','failed') and not state.get('forced',True)

class _Manager:
 # Internal injected dependencies are for synthetic tests only. Production CLI
 # fixes root store, fresh assessor, ownership journal and Audit implementation.
 def __init__(self,store,ownership,assess,adapters):self.store=store;self.ownership=ownership;self.assess=assess;self.adapters=adapters
 def confirm(self,draft):
  require(type(draft) is dict and set(draft)=={'assessment_id','fingerprint','confirmed','selected'})
  current=self.store.load();require(selection_record(draft['confirmed'])==current)
  owned=self.ownership.load();require(not any(e['state'] in HELD for e in owned['instances'].values()))
  view=self.assess(current);require(view['fingerprint']==draft['fingerprint'])
  # Metadata guard prevents takeover even for an empty proposed selection.
  audit=next(s for s in view['sources'] if s['id']=='audit_exec');require(audit['checks'].get('hids_collection')=='inactive')
  values=selected(draft['selected']);eligible={s['id'] for s in view['sources'] if s['preflight']=='eligible'};require(set(values)<=eligible and set(values)<=set(self.adapters))
  record=self.store.save(values,current['revision'])
  owned=dict(version=1,revision=record['revision'],instances={});self.ownership.write(owned)
  states={}
  for source in values:
   adapter=self.adapters[source]
   try:entry=adapter.prepare()
   except Exception:states[source]='initialization_failed';continue
   owned['instances'][source]=entry;self.ownership.write(owned)
   try:entry['state']=adapter.initialize(entry)
   except Exception:entry['state']='initialization_unconfirmed'
   require(entry['state'] in ('initialized_delivery_unproven','initialization_unconfirmed','initialization_failed'));self.ownership.write(owned);states[source]=entry['state']
  return dict(confirmed=record,states=states,collecting='not_collecting' if not values else 'initialization_reported')
 def stop(self):
  owned=self.ownership.load()
  for source,entry in owned['instances'].items():
   if entry['state'] not in (*HELD,'initialization_failed'):continue
   entry['state']='stop_unconfirmed';self.ownership.write(owned)
   try:confirmed=self.adapters[source].stop(entry) is True
   except Exception:confirmed=False
   entry['state']='stopped' if confirmed else 'stop_unconfirmed';self.ownership.write(owned)
  return {s:e['state'] for s,e in owned['instances'].items()}

def manager():
 require(os.getuid()==0 and os.geteuid()==0)
 return _Manager(root_store(),Ownership(),setup_preflight.assess,{'audit_exec':AuditAdapter(),'proc_lifecycle':ProcessAdapter()})
