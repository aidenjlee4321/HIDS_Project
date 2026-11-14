"""Bounded frozen projection of approved process fields; never collects or writes."""
import base64
import hmac
import re
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from api.history_bounds import BoundedRows
from api.history_view import FrozenView, ViewError, _private, _require, _copy, _bytes
from engine.database.process_store import APP_ID, SCHEMA_VERSION, EXPECTED
from engine.ingestion import process_contract as c
from engine.ingestion.m1_contract import uuid_valid

STORE=Path('/var/lib/hids/process/store.sqlite')
FORMAT='hids.process.history-view/1'
LIMITS=dict(events=128,intervals=128,activations=2,page_items=20,response_bytes=65536,detail_bytes=32768,serialized_view_bytes=4194304)
EVENT_COLUMNS=[('ordinal','integer',20,False)]+[(k,'text',36,False) for k in ('event_id','source_id','activation_id','producer_id','boot_id')]+[('kind','text',32,False),('pid','integer',20,False),('tid','integer',20,False),('observed_at','text',64,False),('received_at','text',64,False),('envelope','text',16384,False),('digest','text',64,False)]
INTERVAL_COLUMNS=[(k,'text',36,False) for k in ('activation_id','producer_id','source_id','boot_id')]+[(k,'integer',20,False) for k in ('acknowledged','delivery','incomplete','stopped')]+[('reason','text',32,False),('diagnostics','text',1024,False)]


def selection(value):
    _require(type(value) is list and 1<=len(value)<=2)
    seen=set()
    for scope in value:
        _require(type(scope) is dict and set(scope)=={'source_id','activation_id'})
        _require(all(uuid_valid(v) for v in scope.values()))
        pair=(scope['source_id'],scope['activation_id']);_require(pair not in seen);seen.add(pair)
    return seen


def source(row):
    return dict(adapter='linux.cn_proc',mode='live',source_id=row['source_id'],activation_id=row['activation_id'],boot_id=row['boot_id'],profile=c.PROFILE)


class ProcessView(FrozenView):
    # Reuse the history cursor's canonical, session/family/view-bound HMAC only.
    # No M4 payload validation or scope is inherited by the process projection.
    def __init__(self,rows,selected,*,truncated=False):
        try:
            pairs=selection(selected)
            _require(type(rows) is dict and set(rows)=={'events','intervals'})
            _require(type(truncated) is bool and _bytes(rows)<=LIMITS['serialized_view_bytes'])
            for key in rows:_require(type(rows[key]) is list and len(rows[key])<=128)
            intervals={}
            for row in rows['intervals']:
                _require(type(row) is dict and set(row)=={col[0] for col in INTERVAL_COLUMNS})
                s=source(row);c.scope(s,'live');producer=row['producer_id']
                _require((s['source_id'],s['activation_id']) in pairs)
                key=(s['activation_id'],producer);_require(key not in intervals)
                for flag in ('acknowledged','delivery','incomplete','stopped'):_require(type(row[flag]) is int and row[flag] in (0,1))
                _require(type(row['diagnostics']) is str and len(row['diagnostics'])<=1024)
                counts=c.decode(('{"counts":'+row['diagnostics']+'}').encode('ascii'))['counts'];_require(c.dump(counts)==row['diagnostics'])
                value=dict(protocol_version=1,message_type='status',contract_version=c.CONTRACT,source=s,producer_instance_id=producer,reason=row['reason'],diagnostic_counts=counts,**{k:bool(row[k]) for k in ('acknowledged','delivery','incomplete','stopped')})
                c.status(value,s,producer);intervals[key]=value
            events={};positions=set()
            for row in rows['events']:
                _require(type(row) is dict and set(row)=={col[0] for col in EVENT_COLUMNS})
                s=source(row);c.scope(s,'live');_require((s['source_id'],s['activation_id']) in pairs)
                ordinal=row['ordinal'];_require(type(ordinal) is int and 0<ordinal<2**63 and ordinal not in positions);positions.add(ordinal)
                raw=row['envelope'];_require(type(raw) is str and raw.isascii() and len(raw)<=c.EVENT_LIMIT)
                event=c.decode(raw.encode('ascii'));c.validate(event,s,'live',row['producer_id'])
                _require(c.dump(event)==raw and hashlib.sha256(raw.encode('ascii')).hexdigest()==row['digest'])
                _require(row['event_id']==event['event_id'] and row['event_id'] not in events)
                _require(type(row['pid']) is int and type(row['tid']) is int and (row['kind'],row['pid'],row['tid'],row['observed_at'])==(event['native']['what'],event['native']['tgid'],event['native']['tid'],event['timestamps']['observed_at']))
                c.timestamp(row['received_at'])
                interval=intervals.get((s['activation_id'],row['producer_id']))
                _require(interval is not None and interval['source']==s)
                value=dict(event_id=row['event_id'],arrival_ordinal=str(ordinal),received_at=row['received_at'],envelope=event,historical_interval=interval)
                _require(_bytes(value)<=LIMITS['detail_bytes']);events[row['event_id']]=value
            self._events=events;self._event_order=sorted(events,key=lambda k:int(events[k]['arrival_ordinal']),reverse=True)
            self._intervals=list(intervals.values());self._selected=_copy(selected);self.truncated=truncated
            self.serialized_bytes=_bytes(dict(events=events,intervals=self._intervals,selected=self._selected))
            _require(self.serialized_bytes<=LIMITS['serialized_view_bytes'])
            self.id=secrets.token_hex(16);self.loaded_at=c.utc_now();self._cursor_key=secrets.token_bytes(32)
        except Exception:raise ViewError() from None

    def summary(self):
        return dict(format=FORMAT,view_id=self.id,view_loaded_at=self.loaded_at,history_only=True,monitoring_status='not_assessed',ordering='storage_arrival_descending',truncated=self.truncated,counts=dict(events=len(self._events),intervals=len(self._intervals)),selected_activations=_copy(self._selected),historical_intervals=[{k:_copy(v[k]) for k in ('producer_instance_id','acknowledged','delivery','incomplete','stopped','reason')}|{'activation_id':v['source']['activation_id']} for v in self._intervals],limits=dict(LIMITS))

    def intervals(self):return _copy(self._intervals)

    def detail(self,kind,key):
        _require(kind=='process' and uuid_valid(key) and key in self._events)
        return _copy(self._events[key])

    def page(self,kind,session,cursor=None):
        _require(kind=='process' and type(session) is str)
        index=0;order=self._event_order
        if cursor is not None:
            try:
                _require(type(cursor) is str and re.fullmatch('[A-Za-z0-9_-]{1,512}',cursor))
                raw=base64.urlsafe_b64decode(cursor+'='*((-len(cursor))%4))
                _require(len(raw)>32 and base64.urlsafe_b64encode(raw).decode().rstrip('=')==cursor)
                payload,mac=raw[:-32],raw[-32:]
                expected=hmac.digest(self._cursor_key,hashlib.sha256(session.encode()).digest()+b'\0'+payload,'sha256')
                _require(hmac.compare_digest(mac,expected))
                value=c.decode(payload);_require(c.dump(value).encode('ascii')==payload)
                _require(set(value)=={'v','view','kind','next'} and type(value['v']) is int and value['v']==1 and value['view']==self.id and value['kind']==kind and type(value['next']) is int and 0<value['next']<len(order))
                index=value['next']
            except Exception:raise ViewError() from None
        items=[]
        for key in order[index:index+20]:
            value=self._events[key];e=value['envelope'];n=e['native'];t=e['timestamps']
            items.append(dict(event_id=key,arrival_ordinal=value['arrival_ordinal'],received_at=value['received_at'],action=e['normalized']['event']['action'],pid=n['tgid'],tid=n['tid'],observed_at=t['observed_at'],activity_wall_time=None,activity_wall_time_reason='not_emitted_by_source'))
        index+=len(items)
        result=dict(format=FORMAT,view_id=self.id,items=items,next_cursor=self._cursor(kind,index,session) if index<len(order) else None)
        _require(_bytes(result)<=LIMITS['response_bytes']);return result


class ProcessRows(BoundedRows):
    SPECS={'process_events':(128,EVENT_COLUMNS),'process_intervals':(128,INTERVAL_COLUMNS)}
    def selected(self,selected,*,validate):
        pairs=selection(selected);self.truncated=False
        _require(not self.db.in_transaction)
        where=' OR '.join('(source_id=? AND activation_id=?)' for _ in pairs)
        args=tuple(v for pair in sorted(pairs) for v in pair)
        self.db.set_progress_handler(lambda:int(self.clock()>=self.deadline),1000)
        try:
            self.db.execute('PRAGMA query_only=ON');self.db.execute('PRAGMA trusted_schema=OFF');self.db.execute('PRAGMA busy_timeout=50');self.db.execute('PRAGMA temp_store=MEMORY');self.db.execute('PRAGMA cache_size=-1024')
            self.db.execute('BEGIN');validate()
            rows=dict(events=self._read('process_events',where,args,order_by=' ORDER BY ordinal DESC',truncate=True),intervals=self._read('process_intervals',where,args,order_by=' ORDER BY rowid DESC',truncate=True))
            self.check();return rows
        finally:
            self.db.set_progress_handler(None,0)
            if self.db.in_transaction:self.db.execute('ROLLBACK')


def _load(path,selected,identity):
    db=None;started=time.monotonic()
    try:
        selection(selected);_private(path.parent,True)
        for parent in path.parent.parents:
            info=parent.lstat();_require(info.st_uid in (0,os.geteuid()) and (not info.st_mode&0o022 or info.st_uid==0 and info.st_mode&0o1000))
        _require(type(identity) is list and len(identity)==2 and all(type(n) is int and n>=0 for n in identity) and _private(path)==identity)
        _require({p.name for p in path.parent.iterdir()}<={'store.sqlite','store.sqlite-wal','store.sqlite-shm'})
        files={p:_private(p) for p in (path,Path(str(path)+'-wal'),Path(str(path)+'-shm'))}
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=.05)
        reader=ProcessRows(db);reader.deadline=started+2
        def validate():
            _require(db.execute('PRAGMA application_id').fetchone()==(APP_ID,) and db.execute('PRAGMA user_version').fetchone()==(SCHEMA_VERSION,) and db.execute('PRAGMA journal_mode').fetchone()==('wal',))
            schema=db.execute("SELECT typeof(sql),length(CAST(sql AS BLOB)),substr(sql,1,8193),substr(type,1,33),substr(name,1,65) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' LIMIT 5").fetchall()
            _require(len(schema)==len(EXPECTED) and all(t=='text' and type(n) is int and 0<n<=8192 and type(v) is str and len(v)<=8192 for t,n,v,kind,name in schema))
            _require(sorted((kind,name,v) for t,n,v,kind,name in schema)==EXPECTED)
        rows=reader.selected(selected,validate=validate);view=ProcessView(rows,selected,truncated=reader.truncated);reader.check()
        _require(all(_private(p)==before for p,before in files.items()));return view
    except Exception:raise ViewError() from None
    finally:
        if db is not None:db.close()


def load_view(selected,identity):return _load(STORE,selected,identity)
