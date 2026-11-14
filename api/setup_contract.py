"""D-14a bounded setup metadata/configuration contract; no source initialization."""
import copy
import datetime
import hashlib
import json
import re
import secrets
from api.pilot_sessions import Denied,closed_json

FORMAT='hids.setup-view/1'
REGISTRY={
 'audit_exec':dict(label='Audit execution',implementation='implemented',limitation='Requires existing Audit plugin configuration. Initialization does not prove execution delivery or upstream continuity.'),
 'proc_lifecycle':dict(label='Process lifecycle',implementation='runtime_unvalidated',limitation='Kernel/header metadata is not subscription or intended-account evidence. Live activation is not enabled in this build.'),
 'journal_auth':dict(label='Journal authentication',implementation='not_deployed',limitation='Component evidence is separate from installed source and intended-account access. No journal sampling or group changes occur here.'),
}
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
def sha(value):return hashlib.sha256(canonical(value).encode('ascii')).hexdigest()
# Read the exact prior catalog without rewriting immutable saved revisions.
LEGACY_REGISTRY_HASH=sha(REGISTRY)
REGISTRY['proc_lifecycle']=dict(label='Process lifecycle',implementation='implemented',limitation='Native lifecycle metadata only; no executable or user enrichment. Explicit root activation is required. ACK and delivery are independent; unsubscribe completion is unconfirmed.')
REGISTRY_HASH=sha(REGISTRY)
ACCEPTED_REGISTRY_HASHES=frozenset((LEGACY_REGISTRY_HASH,REGISTRY_HASH))
def require(value):
 if not value:raise Denied()
def clone(value):return json.loads(canonical(value))
def selected(value):
 require(type(value) is list and len(value)<=3 and all(type(s) is str and s in REGISTRY for s in value) and len(set(value))==len(value));return sorted(value)
def selection_record(value):
 require(type(value) is dict and set(value)=={'version','revision','selected','registry_sha256'})
 require(type(value['version']) is int and value['version']==1 and type(value['revision']) is int and 0<=value['revision']<=16 and value['registry_sha256'] in ACCEPTED_REGISTRY_HASHES)
 require(selected(value['selected'])==value['selected'] and (value['revision']!=0 or not value['selected']))
 require(len(canonical(value))<=4096);return clone(value)
def empty_record():return dict(version=1,revision=0,selected=[],registry_sha256=REGISTRY_HASH)
def validate_view(value):
 require(type(value) is dict and set(value)=={'format','assessment_id','assessed_at','fingerprint','confirmed','sources'})
 require(value['format']==FORMAT and type(value['assessment_id']) is str and re.fullmatch('[0-9a-f]{32}',value['assessment_id']) and type(value['fingerprint']) is str and re.fullmatch('[0-9a-f]{64}',value['fingerprint']))
 require(type(value['assessed_at']) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z',value['assessed_at']))
 datetime.datetime.strptime(value['assessed_at'],'%Y-%m-%dT%H:%M:%S.%fZ')
 selection_record(value['confirmed']);require(type(value['sources']) is list and len(value['sources'])==3)
 for item,name in zip(value['sources'],sorted(REGISTRY)):
  require(type(item) is dict and set(item)=={'id','label','implementation','preflight','checks','limitation','provenance'})
  require(item['id']==name and all(item[k]==REGISTRY[name][k] for k in ('label','implementation','limitation')) and item['preflight'] in ('eligible','blocked','unknown','unsupported'))
  require(type(item['checks']) is dict and 1<=len(item['checks'])<=16 and all(type(k) is str and re.fullmatch('[a-z_]{1,64}',k) and v in ('present','absent','unknown','inactive','active') for k,v in item['checks'].items()))
  require(item['provenance']=='recognized metadata; runtime delivery not assessed')
  if name=='journal_auth':require(item['preflight']!='eligible')
  if name=='proc_lifecycle' and item['preflight']=='eligible':require(item['checks'].get('installed_runtime')=='present' and item['checks'].get('hids_collection')=='inactive')
 require(len(canonical(value))<=65536);return clone(value)
def build_view(facts,record):
 record=selection_record(record);items=[]
 for name in sorted(REGISTRY):
  checks=clone(facts[name]['checks']);state=facts[name]['preflight']
  items.append(dict(id=name,**REGISTRY[name],preflight=state,checks=checks,provenance='recognized metadata; runtime delivery not assessed'))
 return validate_view(dict(format=FORMAT,assessment_id=secrets.token_hex(16),assessed_at=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),fingerprint=sha(facts),confirmed=record,sources=items))
def public_view(value):
 value=validate_view(value);value.pop('fingerprint');value['snapshot_only']=True;value['monitoring_status']='not_assessed';return value
