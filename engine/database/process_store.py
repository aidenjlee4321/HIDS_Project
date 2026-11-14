"""Private Python-owned process store; no OS event collection or evidence expiry."""
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from engine.ingestion import process_contract as c
from engine.ingestion.m1_security import private_directory,private_file
from engine.database.m1_store import connect,check_sidecars

APP_ID=0x48505231
SCHEMA_VERSION=1
MAX_EVENTS=10000
MAX_BYTES=64*1024*1024
RESERVE=256*1024*1024
# Bound a complete-database WAL rewrite, sidecars and a small transaction cushion.
# The DB page cap is 16MiB; 64MiB total admits the worst bounded DB+WAL copies.
MAX_PAGES=4096
WRITE_RESERVE=(MAX_PAGES+2)*(4096+24)+65536
DDL="""CREATE TABLE process_events(
 ordinal INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,
 source_id TEXT NOT NULL,activation_id TEXT NOT NULL,producer_id TEXT NOT NULL,boot_id TEXT NOT NULL,
 kind TEXT NOT NULL,pid INTEGER NOT NULL,tid INTEGER NOT NULL,
 observed_at TEXT NOT NULL,received_at TEXT NOT NULL,envelope TEXT NOT NULL,digest TEXT NOT NULL);
CREATE INDEX process_kind_arrival ON process_events(kind,ordinal);
CREATE INDEX process_pid_arrival ON process_events(pid,ordinal);
CREATE TABLE process_intervals(
 activation_id TEXT NOT NULL,producer_id TEXT NOT NULL,source_id TEXT NOT NULL,boot_id TEXT NOT NULL,
 acknowledged INTEGER NOT NULL,delivery INTEGER NOT NULL,incomplete INTEGER NOT NULL,stopped INTEGER NOT NULL,
 reason TEXT NOT NULL,diagnostics TEXT NOT NULL,PRIMARY KEY(activation_id,producer_id));"""

def expected_schema():
    db=sqlite3.connect(':memory:')
    try:
        db.executescript(DDL)
        return sorted(db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall())
    finally:db.close()
EXPECTED=expected_schema()

class Store:
    def __init__(self,path,source,mode='live',*,max_events=MAX_EVENTS,max_bytes=MAX_BYTES,
                 minimum_free=RESERVE,space=None,fault=lambda stage:None):
        c.scope(source,mode);self.source=dict(source);self.mode=mode;self.path=Path(path);self.conn=None;self.last_commit=None
        c.require(type(max_events) is int and 1<=max_events<=MAX_EVENTS)
        c.require(type(max_bytes) is int and 2*WRITE_RESERVE<max_bytes<=MAX_BYTES)
        c.require(type(minimum_free) is int and 0<=minimum_free<2**63)
        self.max_events=max_events;self.max_bytes=max_bytes;self.minimum_free=minimum_free
        self.space=space or self.available;self.fault=fault
        private_directory(self.path.parent)
        # All files in the dedicated private store directory are accounted; no
        # deletion/unknown-file exemption. Separate stores use separate directories.
        fresh=not os.path.lexists(self.path)
        self.admit()
        if fresh:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600);os.close(fd)
        private_file(self.path,writable=True);check_sidecars(self.path)
        try:
            self.conn=connect(self.path)
            self.conn.execute('PRAGMA trusted_schema=OFF');self.conn.execute('PRAGMA busy_timeout=50')
            self.conn.execute('PRAGMA temp_store=MEMORY');self.conn.execute('PRAGMA cache_size=-1024')
            if not fresh:self.schema()
            if fresh:c.require(self.conn.execute('PRAGMA journal_mode=WAL').fetchone()==('wal',))
            else:c.require(self.conn.execute('PRAGMA journal_mode').fetchone()==('wal',))
            c.require(self.conn.execute('PRAGMA page_size').fetchone()==(4096,))
            c.require(self.conn.execute('PRAGMA max_page_count='+str(MAX_PAGES)).fetchone()==(MAX_PAGES,))
            self.conn.execute('PRAGMA synchronous=FULL');self.conn.execute('PRAGMA wal_autocheckpoint=64')
            self.conn.execute('PRAGMA journal_size_limit=0')
            if fresh:
                self.conn.executescript('BEGIN IMMEDIATE;'+DDL+'PRAGMA application_id='+str(APP_ID)+';PRAGMA user_version=1;COMMIT;')
            self.schema();check_sidecars(self.path);self.admit()
        except BaseException:self.close();raise
    def available(self):
        s=os.statvfs(self.path.parent)
        if s.f_flag&os.ST_RDONLY:raise OSError('filesystem_read_only')
        return s.f_bavail*s.f_frsize
    def admit(self):
        size=0
        for p in self.path.parent.iterdir():
            s=p.lstat()
            c.require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'capacity_exceeded')
            size+=max(s.st_size,s.st_blocks*512)
        free=self.space();c.require(type(free) is int and free>=0,'capacity_exceeded')
        c.require(size+WRITE_RESERVE<=self.max_bytes and free>=self.minimum_free+WRITE_RESERVE,'capacity_exceeded')
    def schema(self):
        c.require(self.conn.execute('PRAGMA application_id').fetchone()==(APP_ID,))
        c.require(self.conn.execute('PRAGMA user_version').fetchone()==(SCHEMA_VERSION,))
        actual=sorted(self.conn.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall())
        c.require(actual==EXPECTED)
    def put(self,event,received_at=None):
        self.last_commit=None
        c.validate(event,self.source,self.mode);text=c.dump(event);received_at=c.utc_now() if received_at is None else received_at;c.timestamp(received_at)
        digest=hashlib.sha256(text.encode('ascii')).hexdigest()
        # Resolve known commits before admission: a duplicate is not a new write.
        row=self.conn.execute('SELECT envelope,digest,ordinal FROM process_events WHERE event_id=?',(event['event_id'],)).fetchone()
        if row is not None:
            c.require(row[:2]==(text,digest),'id_conflict');return 'duplicate',row[2]
        self.admit();self.conn.execute('BEGIN IMMEDIATE')
        try:
            c.require(self.conn.execute('SELECT count(*) FROM process_events').fetchone()[0]<self.max_events,'capacity_exceeded')
            self.fault('before_insert');s=event['source'];n=event['native']
            cur=self.conn.execute('INSERT INTO process_events(event_id,source_id,activation_id,producer_id,boot_id,kind,pid,tid,observed_at,received_at,envelope,digest) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (event['event_id'],s['source_id'],s['activation_id'],event['producer_instance_id'],s['boot_id'],n['what'],n['tgid'],n['tid'],event['timestamps']['observed_at'],received_at,text,digest))
            ordinal=cur.lastrowid;self.fault('before_commit');self.conn.execute('COMMIT')
            self.last_commit=(event['event_id'],digest);self.fault('after_commit')
            check_sidecars(self.path);return 'stored',ordinal
        except BaseException:
            if self.conn.in_transaction:self.conn.execute('ROLLBACK')
            raise
    def committed(self,event):
        """Resolve a possible prior commit with reads only; never retry an insert."""
        c.validate(event,self.source,self.mode)
        c.require(not self.conn.in_transaction)
        private_directory(self.path.parent);private_file(self.path,writable=True);check_sidecars(self.path)
        text=c.dump(event);digest=hashlib.sha256(text.encode('ascii')).hexdigest()
        # Do not turn a failed fsync/COMMIT into success based on cached reads.
        # Resolution here is only for a failure *after* SQLite returned COMMIT OK.
        if self.last_commit!=(event['event_id'],digest):return None
        row=self.conn.execute('SELECT envelope,digest,ordinal FROM process_events WHERE event_id=?',(event['event_id'],)).fetchone()
        if row is None:return None
        c.require(row[:2]==(text,digest),'id_conflict')
        return row[2]
    def interval(self,value,producer):
        c.status(value,self.source,producer,self.mode);self.admit();self.conn.execute('BEGIN IMMEDIATE')
        try:
            # Bounded interval history; never overwrite unrelated activations.
            prior=self.conn.execute('SELECT acknowledged,delivery,incomplete,stopped FROM process_intervals WHERE activation_id=? AND producer_id=?',(self.source['activation_id'],producer)).fetchone()
            if prior:
                c.require(not prior[3] or value['stopped'])
                bits=[int(bool(old or value[k])) for old,k in zip(prior,('acknowledged','delivery','incomplete','stopped'))]
                self.conn.execute('UPDATE process_intervals SET acknowledged=?,delivery=?,incomplete=?,stopped=?,reason=?,diagnostics=? WHERE activation_id=? AND producer_id=?',(*bits,value['reason'],c.dump(value['diagnostic_counts']),self.source['activation_id'],producer))
            else:
                c.require(self.conn.execute('SELECT count(*) FROM process_intervals').fetchone()[0]<self.max_events,'capacity_exceeded')
                self.conn.execute('INSERT INTO process_intervals VALUES (?,?,?,?,?,?,?,?,?,?)',(self.source['activation_id'],producer,self.source['source_id'],self.source['boot_id'],*(int(value[k]) for k in ('acknowledged','delivery','incomplete','stopped')),value['reason'],c.dump(value['diagnostic_counts'])))
            self.conn.execute('COMMIT')
        except BaseException:
            if self.conn.in_transaction:self.conn.execute('ROLLBACK')
            raise
    def close(self):
        if self.conn is not None:self.conn.close();self.conn=None
