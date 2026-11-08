"""Separate M2 writer. No M1 schema migration, OS reading or activation from events."""
import json
import os
from pathlib import Path
import sqlite3
from engine.database.m1_store import connect, profile, check_sidecars, RetrievalFailure
from engine.ingestion.m1_contract import Invalid, timestamp, utc_now, uuid_valid
from engine.ingestion.m1_security import private_directory, private_file
from engine.ingestion.m2_contract import canonical, decode, frame, validate_event, MAX_REVISION

DDL = (
    'CREATE TABLE activations (activation TEXT PRIMARY KEY, source TEXT NOT NULL, state TEXT NOT NULL, authorized_at TEXT NOT NULL)',
    'CREATE TABLE progress (source TEXT PRIMARY KEY, activation TEXT NOT NULL, authorized INTEGER NOT NULL CHECK(authorized IN (0,1)), state TEXT NOT NULL, revision INTEGER NOT NULL, cursor TEXT, boundary_start TEXT, boundary_end TEXT)',
    'CREATE TABLE dispositions (event_id TEXT PRIMARY KEY, source TEXT NOT NULL, cursor TEXT NOT NULL, kind TEXT NOT NULL, canonical TEXT NOT NULL, envelope TEXT NOT NULL, revision INTEGER NOT NULL, received_at TEXT NOT NULL, stored_at TEXT NOT NULL, UNIQUE(source,cursor), UNIQUE(source,revision))',
    'CREATE TABLE gaps (id INTEGER PRIMARY KEY, source TEXT NOT NULL, activation TEXT NOT NULL, revision INTEGER NOT NULL, cursor TEXT, code TEXT NOT NULL, observed_at TEXT NOT NULL)',
)
GAPS = frozenset('unanchored_restart_gap cursor_gap access_denied read_failure invalid_identity delivery_unconfirmed protocol_failure'.split())


class Store:
    def __init__(self,path,*,max_records,max_pages,clock=utc_now,fault=lambda stage:None):
        if type(max_records) is not int or not 1<=max_records<=MAX_REVISION or type(max_pages) is not int or max_pages<16:
            raise ValueError('explicit_storage_budget_required')
        self.path=Path(path);self.conn=None;self.clock=clock;self.fault=fault;self.max_records=max_records
        private_directory(self.path.parent)
        fresh=not self.path.exists() and not self.path.is_symlink()
        if fresh:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd)
        private_file(self.path,writable=True);check_sidecars(self.path)
        try:
            self.conn=connect(self.path)
            fault('startup')
            profile(self.conn,fresh=fresh)
            self.conn.execute('PRAGMA max_page_count='+str(max_pages))
            if self.conn.execute('PRAGMA max_page_count').fetchone()[0]!=max_pages:
                raise RuntimeError('storage_budget_below_existing_size')
            if fresh:
                self.conn.execute('BEGIN IMMEDIATE')
                for sql in DDL:self.conn.execute(sql)
                self.conn.execute('PRAGMA user_version=2');self.conn.execute('COMMIT')
            self.schema(self.conn)
            check_sidecars(self.path)
        except BaseException:
            self.close();raise

    @staticmethod
    def schema(conn):
        actual=conn.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' ORDER BY name").fetchall()
        if conn.execute('PRAGMA user_version').fetchone()[0]!=2 or sorted(x[0] for x in actual)!=sorted(DDL):
            raise RuntimeError('unexpected_m2_schema')

    def transaction(self,operation):
        try:
            self.conn.execute('BEGIN IMMEDIATE');result=operation()
            self.fault('before_commit');self.conn.execute('COMMIT');self.fault('after_commit')
            check_sidecars(self.path);return result
        except BaseException:
            if self.conn.in_transaction:
                try:self.conn.execute('ROLLBACK')
                except sqlite3.Error:pass
            raise

    def activate(self,source,activation,*,authorized=False):
        # Trusted control caller only; never dispatched from event frames.
        if not authorized or not uuid_valid(source) or not uuid_valid(activation):raise PermissionError('activation_authority')
        def operation():
            if self.conn.execute('SELECT 1 FROM activations WHERE activation=?',(activation,)).fetchone():raise Invalid('inactive_source')
            row=self.conn.execute('SELECT revision,authorized FROM progress WHERE source=?',(source,)).fetchone()
            if row and row[1]:raise Invalid('reader_busy')
            revision=row[0] if row else 0
            observed=self.clock();timestamp(observed)
            self.conn.execute('INSERT INTO activations VALUES (?,?,?,?)',(activation,source,'authorized',observed))
            self.conn.execute('INSERT INTO progress VALUES (?,?,1,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET activation=excluded.activation,authorized=1,state=excluded.state,cursor=NULL,boundary_start=NULL,boundary_end=NULL',
                              (source,activation,'initializing',revision,None,None,None))
        self.transaction(operation)

    def progress(self,source,activation):
        row=self.conn.execute('SELECT activation,authorized,state,revision,cursor,boundary_start,boundary_end FROM progress WHERE source=?',(source,)).fetchone()
        if not row or row[0]!=activation or not row[1]:raise Invalid('inactive_source')
        return dict(zip(('activation_id','authorized','state','revision','cursor','boundary_start','boundary_end'),row))

    def boundary(self,source,activation,cursor,started,ended):
        from engine.ingestion.m2_contract import event_id
        if cursor is not None:event_id(source,cursor)
        timestamp(started);timestamp(ended)
        def operation():
            p=self.progress(source,activation)
            if p['state']!='initializing':
                if p['state'] in ('anchored','empty_unanchored') and p['cursor']==cursor and p['boundary_start']==started and p['boundary_end']==ended:
                    return  # Lost boundary ACK, not a new tail choice.
                raise Invalid('stale_revision')
            self.conn.execute('UPDATE progress SET state=?,cursor=?,boundary_start=?,boundary_end=? WHERE source=?',
                              ('anchored' if cursor is not None else 'empty_unanchored',cursor,started,ended,source))
        self.transaction(operation)

    def revoke(self,source,activation):
        def operation():
            self.progress(source,activation)
            self.conn.execute('UPDATE progress SET authorized=0,state=? WHERE source=?',('revoked',source))
            self.conn.execute('UPDATE activations SET state=? WHERE activation=?',('revoked',activation))
        self.transaction(operation)

    def gap(self,source,activation,code):
        if code not in GAPS:raise ValueError('gap_code')
        observed=self.clock();timestamp(observed)
        def operation():
            p=self.progress(source,activation)
            self.conn.execute('INSERT INTO gaps(source,activation,revision,cursor,code,observed_at) VALUES (?,?,?,?,?,?)',
                              (source,activation,p['revision'],p['cursor'],code,observed))
            self.conn.execute('UPDATE progress SET state=? WHERE source=?',('gap',source))
        self.transaction(operation)

    def note_interruption(self,source,activation,code):
        if code not in ('reader_disconnected','lease_expired','ingest_shutdown'):
            raise ValueError('interruption_code')
        observed=self.clock();timestamp(observed)
        def operation():
            p=self.progress(source,activation)
            self.conn.execute('INSERT INTO gaps(source,activation,revision,cursor,code,observed_at) VALUES (?,?,?,?,?,?)',
                              (source,activation,p['revision'],p['cursor'],code,observed))
        self.transaction(operation)

    def put(self,event,received_at):
        validate_event(event);timestamp(received_at)
        stable=canonical(event);envelope=frame(event).decode('ascii')[:-1]
        def operation():
            source=event['source_id'];p=self.progress(source,event['activation_id'])
            if p['state'] not in ('anchored','empty_unanchored'):raise Invalid('inactive_source')
            row=self.conn.execute('SELECT source,cursor,kind,canonical,envelope,revision,received_at,stored_at FROM dispositions WHERE event_id=?',(event['event_id'],)).fetchone()
            if row:
                if row[0]!=source or row[1]!=event['cursor'] or row[3]!=stable:raise Invalid('id_conflict')
                old=validate_event(decode(row[4].encode('ascii')))
                if canonical(old)!=row[3] or old['event_id']!=event['event_id'] or old['message_type']!=row[2]:raise RuntimeError('invalid_stored_record')
                timestamp(row[6]);timestamp(row[7]);revision=row[5]
                if type(revision) is not int or not 1<=revision<=p['revision']:raise RuntimeError('invalid_stored_revision')
                result='rejected_record' if row[2]=='journal_rejection' else 'duplicate'
            else:
                if event['expected_revision']!=p['revision'] or p['revision']==MAX_REVISION:raise Invalid('stale_revision')
                if self.conn.execute('SELECT count(*) FROM dispositions').fetchone()[0]>=self.max_records:
                    raise sqlite3.OperationalError('configured_storage_capacity')
                revision=p['revision']+1;stored=self.clock();timestamp(stored)
                self.fault('before_insert')
                self.conn.execute('INSERT INTO dispositions VALUES (?,?,?,?,?,?,?,?,?)',
                                  (event['event_id'],source,event['cursor'],event['message_type'],stable,envelope,revision,received_at,stored))
                self.fault('after_insert')
                updated=self.conn.execute('UPDATE progress SET revision=?,cursor=?,state=? WHERE source=? AND activation=? AND revision=? AND authorized=1',
                                          (revision,event['cursor'],'anchored',source,event['activation_id'],p['revision']))
                if updated.rowcount!=1:raise Invalid('stale_revision')
                self.fault('after_checkpoint')
                result='stored' if event['message_type']=='journal_event' else 'rejected_record'
            return {'protocol_version':2,'message_type':'ack','event_id':event['event_id'],'result':result,
                    'checkpoint_revision':revision,'code':event.get('reason')}
        return self.transaction(operation)

    def close(self):
        if self.conn is not None:self.conn.close();self.conn=None


def get_event(path,event_id):
    conn=None
    try:
        path=Path(path);private_directory(path.parent);private_file(path);check_sidecars(path)
        conn=connect(path,reader=True);profile(conn,reader=True);Store.schema(conn)
        row=conn.execute('SELECT envelope,canonical FROM dispositions WHERE event_id=?',(event_id,)).fetchone()
        if row is None:return None
        event=validate_event(decode(row[0].encode('ascii')))
        if event['event_id']!=event_id or canonical(event)!=row[1]:raise ValueError('invalid_stored_record')
        check_sidecars(path);return event
    except (OSError,ValueError,RuntimeError,sqlite3.Error) as exc:raise RetrievalFailure('retrieval_failure') from exc
    finally:
        if conn is not None:conn.close()
