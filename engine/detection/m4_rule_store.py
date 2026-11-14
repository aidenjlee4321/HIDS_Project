"""Version-2 real-data persistence with immutable prospective rule plans."""
import json
from engine.detection.m4_live import LiveSource,LiveStore
from engine.detection.m4_handoff import FORMAT,decoded
from engine.detection.m4_pilot import Invalid,canonical,digest
from engine.detection.m4_rules import validate_rule,evaluate
from engine.detection.m4_schema import DDL_V2
from engine.ingestion.m1_contract import utc_now


class RuleStore(LiveStore):
    SCHEMA_VERSION=2
    SCHEMA_DDL=DDL_V2

    def select_evaluations(self,source,rules):
        if type(source) is not LiveSource:raise Invalid('selected real source required')
        rules=[validate_rule(r) for r in rules]
        plan=canonical([dict(id=r['id'],revision=r['revision'],hash=digest(self.domain('rule'),r)) for r in rules])
        row=self.db.execute('SELECT rule_plan FROM m4h_bindings WHERE binding_key=?',(source.key,)).fetchone()
        if row and row[0]!=plan:raise Invalid('frozen rule plan changed; select a new activation')
        self.evaluation_binding=source.key

    def binding_pending(self,key):
        return self.db.execute("SELECT count(*) FROM m4h_evaluations v JOIN m4h_events e USING(event_key) WHERE v.state='pending' AND e.binding_key=?",(key,)).fetchone()[0]

    def import_page(self,source,rules=(),*,limit=64):
        if type(source) is not LiveSource or len(rules)>1:raise Invalid('selected real source and approved rule required')
        rules=[validate_rule(r) for r in rules]
        plan=canonical([dict(id=r['id'],revision=r['revision'],hash=digest(self.domain('rule'),r)) for r in rules])
        old=self.db.execute('SELECT scope,directory,state,rule_plan FROM m4h_bindings WHERE binding_key=?',(source.key,)).fetchone()
        if old and old[:2]!=(canonical(source.scope),str(source.directory)):raise Invalid('binding changed')
        if old and old[3]!=plan:raise Invalid('frozen rule plan changed; select a new activation')
        events,state=source.read_page(json.loads(old[2]) if old else None,limit=limit)
        with self.transaction():
            self.db.execute('INSERT OR IGNORE INTO m4h_bindings(binding_key,scope,directory,state,rule_plan) VALUES (?,?,?,?,?)',
                (source.key,canonical(source.scope),str(source.directory),canonical(state),plan))
            for r in rules:
                definition=canonical(r)
                previous=self.db.execute('SELECT definition FROM m4h_rules WHERE rule_id=? AND revision=?',(r['id'],r['revision'])).fetchone()
                if previous and previous!=(definition,):raise Invalid('immutable rule conflict')
                self.db.execute('INSERT OR IGNORE INTO m4h_rules VALUES (?,?,?,?)',(r['id'],r['revision'],definition,digest(self.domain('rule'),r)))
            for event in events:
                key=digest(self.domain('event'),[event[k] for k in ('source','activation','generation','identity')])
                envelope=canonical(event)
                previous=self.db.execute('SELECT envelope FROM m4h_events WHERE event_key=?',(key,)).fetchone()
                if previous and previous!=(envelope,):raise Invalid('immutable event conflict')
                self.db.execute('INSERT OR IGNORE INTO m4h_events VALUES (?,?,?,?,?,?,?)',
                    (key,source.key,event['identity'],event['first_offset'],envelope,digest(self.domain('content'),event),utc_now()))
                for r in rules:self.db.execute("INSERT OR IGNORE INTO m4h_evaluations VALUES (?,?,?,'pending',NULL,NULL)",(key,r['id'],r['revision']))
            self.db.execute('UPDATE m4h_bindings SET state=? WHERE binding_key=?',(canonical(state),source.key))
        return len(events)

    def evaluate_pending(self,*,limit=64):
        if type(limit) is not int or not 1<=limit<=64:raise Invalid('invalid evaluation budget')
        binding=getattr(self,'evaluation_binding',None)
        if binding is None:
            work=self.db.execute("SELECT event_key,rule_id,revision FROM m4h_evaluations WHERE state='pending' ORDER BY rowid LIMIT ?",(limit,)).fetchall()
        else:
            work=self.db.execute("SELECT v.event_key,v.rule_id,v.revision FROM m4h_evaluations v JOIN m4h_events e USING(event_key) WHERE v.state='pending' AND e.binding_key=? ORDER BY v.rowid LIMIT ?",(binding,limit)).fetchall()
        for key,rule_id,revision in work:
            with self.transaction():
                row=self.db.execute('''SELECT e.envelope,e.content_hash,r.definition,r.content_hash,b.rule_plan
                    FROM m4h_events e JOIN m4h_bindings b USING(binding_key),m4h_rules r
                    WHERE e.event_key=? AND r.rule_id=? AND r.revision=?''',(key,rule_id,revision)).fetchone()
                try:
                    event,rule=decoded(row[0]),validate_rule(decoded(row[2]))
                    reference=dict(id=rule_id,revision=revision,hash=row[3])
                    if (event['format']!=FORMAT or event['origin']!='audit_plugin' or
                        digest(self.domain('event'),[event[k] for k in ('source','activation','generation','identity')])!=key or
                        digest(self.domain('content'),event)!=row[1] or digest(self.domain('rule'),rule)!=row[3] or
                        rule['id']!=rule_id or rule['revision']!=revision or reference not in json.loads(row[4])):
                        raise Invalid('stored rule/event plan conflict')
                    state,reason,values=evaluate(event['execution'],event['metadata']['profile'],rule)
                except Exception:state,reason,values='error','evaluation_failed',{}
                when=utc_now()
                self.db.execute('UPDATE m4h_evaluations SET state=?,reason=?,evaluated_at=? WHERE event_key=? AND rule_id=? AND revision=?',
                    (state,reason,when,key,rule_id,revision))
                if state=='matched':
                    explanation=rule['explanation']
                    if event['execution']['auid'] is None:explanation+=' Audit login identity is unavailable.'
                    self.db.execute('INSERT INTO m4h_alerts VALUES (?,?,?,?,?,?,0,?,?)',
                        (digest(self.domain('alert'),[key,rule_id,revision]),key,rule_id,revision,explanation,canonical(values),rule['severity'],when))
        return len(work)

    def binding_count(self,key):
        return self.db.execute('SELECT count(*) FROM m4h_events WHERE binding_key=?',(key,)).fetchone()[0]
