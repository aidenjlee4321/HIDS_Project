"""One-shot root metadata assessment. Never connects a source/control socket."""
import hashlib
import os
from pathlib import Path
import platform
import pwd
import grp
import stat
import subprocess
from api.setup_contract import build_view,require,sha

AUDIT_UNITS=('hids-m3.socket','hids-m3.service','hids-m3-health.service','hids-m3-health.timer')
UNITS=('auditd.service',*AUDIT_UNITS,'hids-ingest.socket','hids-ingest.service','hids-journal.service','hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket')

def unit(name):
 require(name in UNITS)
 r=subprocess.run(['/usr/bin/systemctl','show',name,'--property=LoadState,ActiveState,FragmentPath,DropInPaths'],capture_output=True,text=True,timeout=3,check=True)
 require(len(r.stdout)<=8192);return dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
def trusted_bytes(path,limit):
 path=Path(path);require(path.resolve()==path)
 for p in path.parents:
  s=p.lstat();require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022)
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  s=os.fstat(fd);require(s.st_uid==0 and stat.S_ISREG(s.st_mode) and s.st_nlink==1 and not s.st_mode&0o6022 and s.st_size<=limit)
  data=bytearray()
  while len(data)<=limit:
   chunk=os.read(fd,min(65536,limit+1-len(data)))
   if not chunk:break
   data.extend(chunk)
  require(len(data)<=limit);return bytes(data)
 finally:os.close(fd)
def assess(record):return build_view(facts(),record)
def process_metadata(units,options):
 checks=dict(kernel_option='present' if options.get('CONFIG_PROC_EVENTS')=='y' and options.get('CONFIG_CONNECTOR')=='y' else 'unknown',installed_runtime='absent',hids_collection='active' if any(units[name].get('ActiveState')!='inactive' for name in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket')) else 'inactive',runtime_delivery='unknown')
 witness={}
 try:
  from engine.ingestion import process_control as p
  p.runtime_directory();cfg=p.configuration();role=pwd.getpwnam('hids-process');backend=pwd.getpwnam('hids-ingest')
  require(role.pw_uid>0 and role.pw_uid!=backend.pw_uid and role.pw_shell=='/usr/sbin/nologin' and sorted(os.getgrouplist(role.pw_name,role.pw_gid))==[role.pw_gid])
  witness['units']={}
  for name in (p.UNIT,*p.PARTS):
   require(units[name].get('LoadState')=='loaded');fragment=units[name].get('FragmentPath','');witness['units'][name]=dict(fragment=hashlib.sha256(trusted_bytes(fragment,16384)).hexdigest(),dropins={path:hashlib.sha256(trusted_bytes(path,16384)).hexdigest() for path in units[name].get('DropInPaths','').split()})
  manifest=trusted_bytes('/opt/hids-process-pipeline/code-manifest.json',16384)
  import json
  files=json.loads(manifest);require(type(files) is dict and 1<=len(files)<=128)
  require({'engine/ingestion/process_control.py','engine/ingestion/process_backend.py','engine/ingestion/process_receiver.py','engine/ingestion/process_contract.py','engine/database/process_store.py'}<=set(files))
  for name,digest in files.items():
   require(type(name) is str and name.endswith('.py') and '..' not in name.split('/') and not name.startswith('/'))
   require(hashlib.sha256(trusted_bytes('/opt/hids-process-pipeline/code/'+name,1024*1024)).hexdigest()==digest)
  witness.update(config=cfg,code_manifest=hashlib.sha256(manifest).hexdigest(),role=[role.pw_uid,role.pw_gid])
  require(units[p.UNIT].get('LoadState')=='loaded')
  require(not p.GRANT.exists())
  checks['installed_runtime']='present'
 except Exception:pass
 eligible=checks['installed_runtime']=='present' and checks['hids_collection']=='inactive' and checks['kernel_option']=='present'
 return dict(preflight='eligible' if eligible else 'blocked',checks=checks),witness

def facts():
 require(os.getuid()==0 and os.geteuid()==0)
 units={u:unit(u) for u in UNITS};accounts={};artifacts={};plugins={};valid_plugin=False;safe=True
 for name in ('hids-audit','hids-ingest','hids-journal','hids-process'):
  try:
   p=pwd.getpwnam(name);accounts[name]=[p.pw_uid,p.pw_gid,sorted(os.getgrouplist(name,p.pw_gid))]
  except KeyError:accounts[name]=None
 for name in ('hids-audit-plugin','hids-audit-launcher','hids-m3-health'):
  try:artifacts[name]=hashlib.sha256(trusted_bytes('/usr/lib/hids/'+name,32*1024*1024)).hexdigest()
  except Exception:artifacts[name]=None;safe=False
 for u in UNITS:
  fragment=units[u].get('FragmentPath','')
  if u in AUDIT_UNITS:
   try:artifacts[u]=hashlib.sha256(trusted_bytes(fragment,16384)).hexdigest()
   except Exception:artifacts[u]=None;safe=False
 try:
  from engine.ingestion.m3_service import load_config
  raw=trusted_bytes('/etc/hids/m3.json',4096);artifacts['m3_config']=hashlib.sha256(raw).hexdigest()
  import json,uuid
  cfg=load_config('/etc/hids/m3.json');require(str(uuid.UUID(cfg['source_id']))==cfg['source_id'])
 except Exception:safe=False;artifacts['m3_config']=None
 try:
  directory=Path('/etc/audit/plugins.d');require(directory.resolve()==directory);s=directory.stat();require(s.st_uid==0 and not s.st_mode&0o022)
  for n,p in enumerate(sorted(directory.glob('*.conf'))):
   require(n<32);raw=trusted_bytes(p,8192);plugins[p.name]=hashlib.sha256(raw).hexdigest();fields={}
   for line in raw.decode('ascii').splitlines():
    line=line.split('#',1)[0].strip()
    if not line:continue
    k,sep,v=line.partition('=');require(sep and k.strip() not in fields);fields[k.strip()]=v.strip()
   if fields.get('path')=='/usr/lib/hids/hids-audit-launcher':
    require(not valid_plugin);valid_plugin=fields.get('active')=='yes' and fields.get('direction')=='out' and fields.get('type')=='always' and fields.get('format')=='string' and not fields.get('args','')
 except Exception:safe=False
 options={}
 try:
  for line in trusted_bytes('/boot/config-'+platform.release(),1024*1024).decode().splitlines():
   if line.startswith(('CONFIG_CONNECTOR=','CONFIG_PROC_EVENTS=')):
    k,v=line.split('=',1);options[k]=v
 except Exception:pass
 access=False
 try:
  from engine.ingestion.m3_service import identities
  reader,ingest,ipc=identities()
  access=subprocess.run(['/usr/bin/setpriv','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','--reuid',str(reader.pw_uid),'--regid',str(reader.pw_gid),'--groups',str(ipc),'/usr/bin/test','-x','/usr/lib/hids/hids-audit-plugin'],stdin=subprocess.DEVNULL,capture_output=True,timeout=3).returncode==0
 except Exception:pass
 inactive=all(units[u].get('ActiveState')=='inactive' for u in UNITS if u!='auditd.service')
 eligible=safe and access and valid_plugin and inactive and units['auditd.service'].get('ActiveState')=='active' and all(accounts.get(s) and accounts[s][0]>0 for s in ('hids-audit','hids-ingest')) and accounts['hids-audit'][0]!=accounts['hids-ingest'][0]
 process,process_witness=process_metadata(units,options)
 checks=dict(audit_service='active' if units['auditd.service'].get('ActiveState')=='active' else 'inactive',hids_plugin='present' if valid_plugin else 'absent',trusted_installation='present' if safe else 'unknown',hids_collection='inactive' if inactive else 'active',reader_execute_access='present' if access else 'unknown',runtime_delivery='unknown')
 return dict(audit_exec=dict(preflight='eligible' if eligible else 'blocked',checks=checks),proc_lifecycle=process,journal_auth=dict(preflight='unsupported',checks=dict(controller_adapter='absent',existing_hids_service='present' if units['hids-journal.service'].get('LoadState')=='loaded' else 'absent',intended_account_access='unknown')),witness=dict(units=units,accounts=accounts,artifacts=artifacts,plugins=plugins,kernel=platform.release(),options=options,process=process_witness))
