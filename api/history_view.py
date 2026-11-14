"""Approved bounded M4 v2 projection. No collection, writes, evaluation or repair."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
import unicodedata

from api.history_bounds import BoundedRows
from engine.detection.m4_handoff import FORMAT, decoded, scope_uuid
from engine.detection.m4_pilot import canonical, digest
from engine.detection.m4_schema import DDL_V2
from engine.detection.m4_rules import REFERENCE, validate_rule
from engine.ingestion.m3_progress import _canonical_execution
from engine.ingestion.m3_event import observation, stamp
from engine.ingestion.m1_contract import utc_now

STORE = Path('/var/lib/hids/m4/store')
APP_ID = 0x48344c31
FORMAT_VIEW = 'hids.m4.history-view/1'
LIMITS = dict(events=128,evaluations=128,findings=32,rules=1,bindings=2,page_items=20,response_bytes=65536,detail_bytes=32768,serialized_view_bytes=4194304)

class ViewError(ValueError):
    def __init__(self):super().__init__('history view unavailable')


def _require(value):
    if not value:raise ViewError()


def _json(text):
    _require(type(text) is str and text.isascii() and len(text)<=16384)
    value=decoded(text);_require(canonical(value)==text);return value


def _hash(kind,value):return digest('hids.m4.live.'+kind+'/1',value)

def _hex(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None

def _copy(value):return json.loads(canonical(value))

def _bytes(value):return len(canonical(value).encode('ascii'))


def escaped(value):
    raw=base64.b64decode(value,validate=True)
    text=raw.decode('utf-8',errors='surrogateescape');out=[]
    for ch in text:
        n=ord(ch)
        if 0xdc80<=n<=0xdcff:out.append('\\x%02x'%(n-0xdc00))
        elif unicodedata.category(ch).startswith('C') or ch in ('\u2028','\u2029'):
            out.append(('\\x%02x' if n<256 else '\\u%04x')%n)
        elif ch=='\\':out.append('\\\\')
        else:out.append(ch)
    rendered=''.join(out)
    return dict(text=rendered[:256],truncated=len(rendered)>256)


class FrozenView:
    """Finite validated in-memory view. Every returned object is a fresh copy."""
    def __init__(self,rows):
        try:
            self._build(rows)
            self.id=secrets.token_hex(16);self.loaded_at=utc_now();self._cursor_key=secrets.token_bytes(32)
            _require(len(self._cursor_key)==32)
        except Exception:raise ViewError() from None

    def _build(self,rows):
        _require(set(rows)=={'m4h_bindings','m4h_events','m4h_rules','m4h_evaluations','m4h_alerts'})
        for table,cap in (('m4h_bindings',2),('m4h_events',128),('m4h_rules',1),('m4h_evaluations',128),('m4h_alerts',32)):
            _require(type(rows[table]) is list and len(rows[table])<=cap)
        _require(1<=len(rows['m4h_bindings'])<=2 and _bytes(rows)<=LIMITS['serialized_view_bytes'])
        bindings={};plans={}
        for row in rows['m4h_bindings']:
            key=row['binding_key'];scope=_json(row['scope']);plan=_json(row['rule_plan']);state=_json(row['state'])
            _require(set(scope)=={'source','activation','generation'})
            for v in scope.values():scope_uuid(v)
            _require(_hex(key) and key==digest('hids.m4.live.binding/1',scope) and key not in bindings and row['directory']=='/var/lib/hids/m3')
            _require(plan in ([],[REFERENCE]))
            _require(set(state)=={'boundary','settled','target','after','seen_frontier','seen_scanned','fingerprint'})
            for name in ('boundary','settled','after','seen_frontier','seen_scanned'):_require(type(state[name]) is int)
            _require(0<=state['boundary']<=state['settled']<=state['seen_frontier']<=state['seen_scanned']<2**63)
            _require(state['boundary']-1<=state['after']<max(state['seen_scanned'],state['boundary']))
            _require(state['target'] is None or type(state['target']) is int and state['settled']<=state['target']<=state['seen_frontier'])
            fp=state['fingerprint'];_require(type(fp) is list and len(fp)==3)
            for pair in fp:_require(type(pair) is list and len(pair)==2 and all(type(n) is int and n>=0 for n in pair))
            bindings[key]=scope;plans[key]=plan
        rules={}
        for row in rows['m4h_rules']:
            definition=validate_rule(_json(row['definition']));ref=dict(id=row['rule_id'],revision=row['revision'],hash=row['content_hash'])
            _require(ref==REFERENCE and _hash('rule',definition)==row['content_hash'] and (row['rule_id'],row['revision']) not in rules)
            rules[(row['rule_id'],row['revision'])]=(definition,ref)
        needed={(p['id'],p['revision']) for plan in plans.values() for p in plan}
        _require(set(rules)==needed)
        events={};native={};positions=set()
        for row in rows['m4h_events']:
            key=row['event_key'];binding=row['binding_key'];event=_json(row['envelope'])
            _require(set(event)=={'format','origin','source','activation','generation','identity','first_offset','execution','metadata'})
            _require(binding in bindings and _hex(key) and key not in events and event['format']==FORMAT and event['origin']=='audit_plugin')
            _require({k:event[k] for k in ('source','activation','generation')}==bindings[binding])
            _require(type(event['identity']) is str and re.fullmatch(r'[0-9]{1,20}\.[0-9]{1,9}:[0-9]{1,20}',event['identity']) and event['identity']==row['identity'])
            state=_json(next(r['state'] for r in rows['m4h_bindings'] if r['binding_key']==binding))
            _require(state['boundary']<=event['first_offset']<=state['after'] and event['first_offset']<state['seen_scanned'])
            _require(type(event['first_offset']) is int and 0<=event['first_offset']<2**63 and event['first_offset']==row['first_offset'])
            _require((binding,event['identity']) not in positions and (binding,event['first_offset']) not in positions)
            positions.update(((binding,event['identity']),(binding,event['first_offset'])))
            _require(key==_hash('event',[event[k] for k in ('source','activation','generation','identity')]) and row['content_hash']==_hash('content',event))
            _canonical_execution(event['execution']);meta=event['metadata']
            _require(type(meta) is dict and set(meta)=={'format','arch','profile','first_observed_unix_ns','received_at','persistence_started_at'} and type(meta['format']) is int and meta['format']==1)
            values=(meta['arch'],meta['profile'],meta['first_observed_unix_ns'])
            if values!=(None,None,None):observation(dict(version=1,arch=values[0],profile=values[1],first_observed_unix_ns=values[2]))
            stamp(meta['received_at']);stamp(meta['persistence_started_at']);stamp(row['imported_at'])
            execution=_copy(event['execution']);execution['result']=str(execution['result'])
            metadata=_copy(meta)
            if metadata['first_observed_unix_ns'] is not None:metadata['first_observed_unix_ns']=str(metadata['first_observed_unix_ns'])
            events[key]=dict(event_id=key,content_hash=row['content_hash'],binding_key=binding,scope=bindings[binding],native_identity=event['identity'],first_offset=str(event['first_offset']),execution=execution,metadata=metadata,imported_at=row['imported_at'],evaluations=[])
            native[key]=event
        evaluations={}
        reasons={'matched':'all_predicates_equal','no_match':'predicate_not_equal','unable':'source_profile_unavailable','error':'evaluation_failed'}
        for row in rows['m4h_evaluations']:
            key=row['event_key'];pair=(row['rule_id'],row['revision']);identity=(key,*pair)
            _require(key in events and pair in rules and identity not in evaluations and rules[pair][1] in plans[events[key]['binding_key']])
            state=row['state'];_require(state in ('pending','matched','no_match','unable','error'))
            if state=='pending':_require(row['reason'] is None and row['evaluated_at'] is None)
            else:_require(row['reason']==reasons[state]);stamp(row['evaluated_at'])
            item=dict(rule_id=pair[0],revision=pair[1],rule_hash=rules[pair][1]['hash'],state=state,reason=row['reason'],evaluated_at=row['evaluated_at'])
            events[key]['evaluations'].append(item);evaluations[identity]=item
        for key,event in events.items():
            expected={(p['id'],p['revision']) for p in plans[event['binding_key']]}
            _require({(v['rule_id'],v['revision']) for v in event['evaluations']}==expected)
            event['evaluation_state']='unevaluated' if not expected else event['evaluations'][0]['state']
        findings={};matched=set()
        for row in rows['m4h_alerts']:
            key=row['event_key'];pair=(row['rule_id'],row['revision']);identity=(key,*pair);finding=row['alert_id']
            _require(_hex(finding) and finding not in findings and identity in evaluations and evaluations[identity]['state']=='matched' and identity not in matched)
            _require(finding==_hash('alert',list(identity)) and type(row['demo']) is int and row['demo']==0 and row['severity']=='informational')
            rule,ref=rules[pair];values=_json(row['matched_values']);execution=native[key]['execution']
            _require(canonical(values)==canonical({p['field']:execution[p['field']] for p in rule['all_of']}) and canonical(values)==canonical({p['field']:p['eq'] for p in rule['all_of']}))
            explanation=rule['explanation']+(' Audit login identity is unavailable.' if execution['auid'] is None else '')
            _require(row['explanation']==explanation and len(explanation.encode())<=4096);stamp(row['created_at'])
            findings[finding]=dict(finding_id=finding,event_id=key,rule_id=pair[0],revision=pair[1],rule_hash=ref['hash'],severity='informational',created_at=row['created_at'],explanation=explanation,matched_values=values,rule=rule)
            matched.add(identity)
        _require(matched=={key for key,value in evaluations.items() if value['state']=='matched'})
        self._events=events;self._findings=findings
        self._event_order=sorted(events,key=lambda k:(events[k]['imported_at'],k),reverse=True)
        self._finding_order=sorted(findings,key=lambda k:(findings[k]['created_at'],k),reverse=True)
        self._counts=dict(events=len(events),findings=len(findings),evaluations=len(evaluations),bindings=len(bindings),rules=len(rules),unevaluated=sum(e['evaluation_state']=='unevaluated' for e in events.values()),pending=sum(v['state']=='pending' for v in evaluations.values()))
        for value in (*events.values(),*findings.values()):_require(_bytes(value)<=LIMITS['detail_bytes'])
        self.serialized_bytes=_bytes(dict(events=events,findings=findings))
        _require(self.serialized_bytes<=LIMITS['serialized_view_bytes'])

    def summary(self):
        return dict(format=FORMAT_VIEW,view_id=self.id,view_loaded_at=self.loaded_at,history_only=True,monitoring_status='not_assessed',counts=_copy(self._counts),limits=dict(LIMITS))

    def detail(self,kind,key):
        _require(kind in ('events','findings') and _hex(key))
        mapping=self._events if kind=='events' else self._findings
        _require(key in mapping);return _copy(mapping[key])

    def _cursor(self,kind,index,session):
        payload=canonical(dict(v=1,view=self.id,kind=kind,next=index)).encode('ascii')
        mac=hmac.digest(self._cursor_key,hashlib.sha256(session.encode()).digest()+b'\0'+payload,'sha256')
        return base64.urlsafe_b64encode(payload+mac).decode().rstrip('=')

    def page(self,kind,session,cursor=None):
        _require(kind in ('events','findings') and type(session) is str)
        order=self._event_order if kind=='events' else self._finding_order;index=0
        if cursor is not None:
            try:
                _require(type(cursor) is str and re.fullmatch('[A-Za-z0-9_-]{1,512}',cursor))
                raw=base64.urlsafe_b64decode(cursor+'='*((-len(cursor))%4));_require(len(raw)>32 and base64.urlsafe_b64encode(raw).decode().rstrip('=')==cursor)
                payload,mac=raw[:-32],raw[-32:];expected=hmac.digest(self._cursor_key,hashlib.sha256(session.encode()).digest()+b'\0'+payload,'sha256')
                _require(hmac.compare_digest(mac,expected));value=_json(payload.decode('ascii'))
                _require(set(value)=={'v','view','kind','next'} and type(value['v']) is int and value['v']==1 and value['view']==self.id and value['kind']==kind and type(value['next']) is int and 0<value['next']<len(order))
                index=value['next']
            except Exception:raise ViewError() from None
        items=[]
        while index<len(order) and len(items)<20:
            value=self.detail(kind,order[index])
            if kind=='events':
                e=value['execution'];value=dict(event_id=value['event_id'],imported_at=value['imported_at'],exe_preview=escaped(e['exe_base64']),pid=e['pid'],ppid=e['ppid'],uid=e['uid'],euid=e['euid'],success=e['success'],result=e['result'],evaluation_state=value['evaluation_state'])
            else:value.pop('rule')
            candidate=items+[value];next_index=index+1
            result=dict(format=FORMAT_VIEW,view_id=self.id,items=candidate,next_cursor=self._cursor(kind,next_index,session) if next_index<len(order) else None)
            if _bytes(result)>LIMITS['response_bytes']:
                _require(items);break
            items=candidate;index=next_index
        return dict(format=FORMAT_VIEW,view_id=self.id,items=items,next_cursor=self._cursor(kind,index,session) if index<len(order) else None)


def _private(path,directory=False):
    _require(path.is_absolute() and path.resolve()==path)
    info=path.lstat()
    _require(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==(0o700 if directory else 0o600))
    _require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink==1)
    return [info.st_dev,info.st_ino]


def _load(path,bindings,identity):
    db=None;started=time.monotonic()
    try:
        _private(path.parent,True)
        for parent in path.parent.parents:
            info=parent.lstat();_require(info.st_uid in (0,os.geteuid()) and (not info.st_mode&0o022 or info.st_uid==0 and info.st_mode&stat.S_ISVTX))
        _require(_private(path)==identity and type(identity) is list and len(identity)==2 and all(type(n) is int and n>=0 for n in identity))
        _require({p.name for p in path.parent.iterdir()}<={'handoff.sqlite','handoff.sqlite-wal','handoff.sqlite-shm','writer.lock'})
        files={p:_private(p) for p in (path,Path(str(path)+'-wal'),Path(str(path)+'-shm'))}
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=.05)
        reader=BoundedRows(db,clock=time.monotonic);reader.deadline=started+2
        def validate():
            _require(db.execute('PRAGMA application_id').fetchone()==(APP_ID,) and db.execute('PRAGMA user_version').fetchone()==(2,) and db.execute('PRAGMA journal_mode').fetchone()==('wal',))
            schema=db.execute("SELECT length(CAST(sql AS BLOB)),substr(sql,1,8193) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' LIMIT 6").fetchall()
            _require(len(schema)==5 and all(type(n) is int and n<=8192 and type(v) is str and len(v)<=8192 for n,v in schema))
            _require(sorted(v for n,v in schema)==sorted(s.strip() for s in DDL_V2.split(';') if s.strip()))
        rows=reader.selected(bindings,validate=validate);view=FrozenView(rows);reader.check()
        _require(all(_private(p)==before for p,before in files.items()))
        return view
    except Exception:raise ViewError() from None
    finally:
        if db is not None:db.close()


def load_view(bindings,identity):
    return _load(STORE/'handoff.sqlite',bindings,identity)
