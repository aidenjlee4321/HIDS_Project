"""Resource guards for a future read-only view; no file opening or HTTP routes.

This bounds selected SQLite values before Python materializes them. It does not
replace schema/hash/provenance validation or authorize a real-data projection.
"""
import json
import re
import sqlite3
import time

class BoundsError(ValueError):
    pass

# name, SQLite type, UTF-8 byte maximum, nullable
SPECS = {
 'm4h_bindings': (2, [('binding_key','text',64,False),('scope','text',4096,False),('directory','text',4096,False),('state','text',16384,False),('rule_plan','text',4096,False)]),
 'm4h_events': (128, [('event_key','text',64,False),('binding_key','text',64,False),('identity','text',64,False),('first_offset','integer',20,False),('envelope','text',16384,False),('content_hash','text',64,False),('imported_at','text',64,False)]),
 'm4h_evaluations': (128, [('event_key','text',64,False),('rule_id','text',128,False),('revision','text',32,False),('state','text',16,False),('reason','text',256,True),('evaluated_at','text',64,True)]),
 'm4h_alerts': (32, [('alert_id','text',64,False),('event_key','text',64,False),('rule_id','text',128,False),('revision','text',32,False),('explanation','text',4096,False),('matched_values','text',16384,False),('demo','integer',20,False),('severity','text',32,False),('created_at','text',64,False)]),
 'm4h_rules': (1, [('rule_id','text',128,False),('revision','text',32,False),('definition','text',16384,False),('content_hash','text',64,False)]),
}

class BoundedRows:
    MAX_BYTES = 4*1024*1024
    SPECS = SPECS
    def __init__(self, db, *, clock=time.monotonic):
        self.db, self.clock = db, clock
        self.deadline=clock()+2; self.used=0
    def check(self):
        if self.clock()>=self.deadline:raise BoundsError('view budget exceeded')
    def _read(self, table, where, args, *, order_by="", truncate=False):
        # Only internal callers pass the fixed predicates below. No SQL text is
        # accepted from an HTTP client or exposed as a public reader operation.
        cap, columns=self.SPECS[table]
        fields=[]
        for name,kind,size,nullable in columns:
            fields += [f'typeof({name})',f'length(CAST({name} AS BLOB))',f'substr(CAST({name} AS BLOB),1,{size+1})']
        cursor=self.db.execute('SELECT '+','.join(fields)+' FROM '+table+' WHERE '+where+order_by+' LIMIT ?',(*args,cap+1))
        result=[]
        try:
            while True:
                self.check();row=cursor.fetchone()
                if row is None:break
                if len(result)>=cap:
                    if truncate:self.truncated=True;break
                    raise BoundsError('view row limit exceeded')
                value={}
                for i,(name,kind,size,nullable) in enumerate(columns):
                    actual,length,raw=row[3*i:3*i+3]
                    if actual=='null' and nullable:value[name]=None;continue
                    if actual!=kind or type(length) is not int or not 0<=length<=size or type(raw) is not bytes or len(raw)!=length:
                        raise BoundsError('invalid or oversized field')
                    try:
                        text=raw.decode('utf-8',errors='strict')
                        value[name]=int(text) if kind=='integer' else text
                    except (ValueError,UnicodeError):raise BoundsError('invalid field encoding') from None
                self.used+=len(json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('ascii'))
                if self.used>self.MAX_BYTES:raise BoundsError('serialized view budget exceeded')
                result.append(value)
            return result
        finally:cursor.close()
    def selected(self,bindings, *, validate=None):
        if (type(bindings) is not list or not 1<=len(bindings)<=2 
            or any(type(b) is not str or not re.fullmatch('[0-9a-f]{64}',b) for b in bindings) or len(set(bindings))!=len(bindings)):
            raise BoundsError('invalid selected bindings')
        if self.db.in_transaction:raise BoundsError('dedicated read connection required')
        marks=','.join('?' for _ in bindings)
        scope='binding_key IN ('+marks+')'
        selected_events='event_key IN (SELECT event_key FROM m4h_events WHERE '+scope+')'
        result={}
        self.db.set_progress_handler(lambda:int(self.clock()>=self.deadline),1000)
        try:
            self.db.execute('PRAGMA query_only=ON');self.db.execute('PRAGMA trusted_schema=OFF');self.db.execute('PRAGMA busy_timeout=50')
            self.db.execute('BEGIN')
            if validate is not None:validate()
            result['m4h_bindings']=self._read('m4h_bindings',scope,bindings)
            if len(result['m4h_bindings'])!=len(bindings):raise BoundsError('selected binding missing')
            for table in ('m4h_events','m4h_evaluations','m4h_alerts'):
                result[table]=self._read(table,scope if table=='m4h_events' else selected_events,bindings)
            references=set()
            for row in result['m4h_bindings']:
                try:plan=json.loads(row['rule_plan'])
                except (ValueError,RecursionError):raise BoundsError('invalid plan') from None
                if type(plan) is not list or len(plan)>1:raise BoundsError('invalid plan')
                for ref in plan:
                    if type(ref) is not dict or set(ref)!={'id','revision','hash'} or any(type(ref[k]) is not str for k in ref):raise BoundsError('invalid plan')
                    if len(ref['id'])>128 or len(ref['revision'])>32 or not re.fullmatch('[0-9a-f]{64}',ref['hash']):raise BoundsError('invalid plan')
                    references.add((ref['id'],ref['revision']))
            if len(references)>1:raise BoundsError('view rule limit exceeded')
            result['m4h_rules']=self._read('m4h_rules','(rule_id,revision) IN ('+','.join('(?,?)' for _ in references)+')',tuple(v for ref in sorted(references) for v in ref)) if references else []
            self.check()
            # Include object/list framing in the final canonical byte budget.
            if len(json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('ascii'))>self.MAX_BYTES:raise BoundsError('serialized view budget exceeded')
            return result
        except sqlite3.Error:raise BoundsError('view unavailable') from None
        finally:
            self.db.set_progress_handler(None,0)
            if self.db.in_transaction:self.db.execute('ROLLBACK')
