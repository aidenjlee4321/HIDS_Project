"""Approved handoff implementation under synthetic-only acceptance.

No installed production entry point or automatic collection activation. Source
reads use mode=ro and require existing private WAL/SHM. Destination is independent.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

from engine.detection.m4_pilot import canonical, digest, evaluate, validate_rule, Invalid
from engine.ingestion.m1_contract import utc_now
from engine.ingestion.m3_event import observation, stamp, PROFILE
from engine.ingestion.m3_progress import _canonical_execution, ProgressError
from engine.ingestion.m3_runtime import DDL as CONTROL_DDL
from engine.ingestion import m3_storage

LEDGER_SCHEMA = '29b7f0c82dc42c236616fc3db07f2ed3ab60a69b97a502fbb240502563515e68'
FORMAT = 'm4.audit-exec-handoff/1'
APP_ID = 0x48344831


def scope_uuid(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise Invalid('invalid scope')
    except (ValueError, AttributeError):
        raise Invalid('invalid scope') from None
    return value


def private(path, *, directory=False):
    p = Path(path)
    if not p.is_absolute() or p.resolve() != p:
        raise Invalid('noncanonical source/destination path')
    s = p.lstat()
    if (not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)) or
            s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != (0o700 if directory else 0o600) or
            (not directory and s.st_nlink != 1)):
        raise Invalid('unsafe source/destination access')
    return [s.st_dev, s.st_ino]


def decoded(text):
    def pairs(items):
        result = dict(items)
        if len(result) != len(items): raise Invalid('duplicate stored JSON key')
        return result
    if type(text) is not str or len(text) > 16384:
        raise Invalid('invalid stored payload size')
    def constant(_): raise Invalid('invalid JSON constant')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError):
        raise Invalid('invalid stored payload') from None


class Source:
    """One explicitly selected immutable source/activation/generation binding."""
    ORIGIN = 'synthetic_lab'
    BINDING_DOMAIN = 'hids.m4.handoff.binding/1'

    def directory_policy(self):
        if not self.directory.parent.name.startswith('hids-m4-handoff.'):
            raise Invalid('isolated synthetic lab source required')

    def __init__(self, directory, source, activation, generation):
        self.directory = Path(directory)
        self.directory_policy()
        self.scope = {k: scope_uuid(v) for k, v in zip(('source', 'activation', 'generation'), (source, activation, generation))}
        self.key = digest(self.BINDING_DOMAIN, self.scope)

    @contextmanager
    def reader(self, path):
        before = private(path)
        # Do not let SQLite create missing source sidecars on a writable lab path.
        private(Path(str(path) + '-wal')); private(Path(str(path) + '-shm'))
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=.05)
        deadline = time.monotonic() + .25
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            if connection.execute('PRAGMA journal_mode').fetchone() != ('wal',):
                raise Invalid('source WAL required')
            connection.execute('BEGIN')
            yield connection, before
            if private(path) != before:
                raise Invalid('source file replaced')
        finally:
            connection.set_progress_handler(None, 0)
            try:
                if connection.in_transaction: connection.execute('ROLLBACK')
            finally:
                connection.close()

    def read_page(self, state=None, *, limit=64):
        if type(limit) is not int or not 1 <= limit <= 64: raise Invalid('invalid page size')
        directory_id = private(self.directory, directory=True)
        control = self.directory / 'control.sqlite'
        ledger = self.directory / (self.scope['activation'] + '.sqlite')
        with self.reader(control) as (db, control_id):
            schema = sorted(r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"))
            if schema != sorted(CONTROL_DDL) or db.execute('PRAGMA user_version').fetchone() != (4,):
                raise Invalid('unsupported control schema')
            if db.execute('SELECT singleton,source FROM m3_source').fetchall() != [(1, self.scope['source'])]:
                raise Invalid('source identity mismatch')
            if db.execute('SELECT generation FROM m3_intervals WHERE activation=?', (self.scope['activation'],)).fetchall() != [(self.scope['generation'],)]:
                raise Invalid('unselected activation/generation')
        with self.reader(ledger) as (db, ledger_id):
            rows = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name").fetchall()
            if hashlib.sha256(canonical(rows).encode()).hexdigest() != LEDGER_SCHEMA or db.execute('PRAGMA user_version').fetchone() != (0,):
                raise Invalid('unsupported ledger schema')
            cursors = db.execute('SELECT singleton,activation,generation,boundary,scanned,frontier FROM m3_cursor').fetchall()
            if len(cursors) != 1: raise Invalid('invalid cursor count')
            singleton, activation, generation, boundary, scanned, frontier = cursors[0]
            if (singleton != 1 or (activation, generation) != (self.scope['activation'], self.scope['generation']) or
                    any(type(v) is not int for v in (boundary, scanned, frontier)) or not 0 <= boundary <= frontier <= scanned < 2**63):
                raise Invalid('ledger scope/position mismatch')
            fingerprint = [directory_id, control_id, ledger_id]
            if state is None:
                state = dict(boundary=boundary, settled=boundary, target=None, after=boundary-1,
                             seen_frontier=frontier, seen_scanned=scanned, fingerprint=fingerprint)
            if (state['fingerprint'] != fingerprint or state['boundary'] != boundary or
                    frontier < state['seen_frontier'] or scanned < state['seen_scanned']):
                raise Invalid('source replacement or position regression')
            target = frontier if state['target'] is None else state['target']
            rows = db.execute('''SELECT e.identity,e.first_offset,e.payload,m.identity,m.format,m.arch,
                m.collector_profile,m.first_observed_unix_ns,m.received_at,m.persistence_started_at,d.state,
                (SELECT MIN(begin) FROM m3_positions p WHERE p.identity=e.identity),
                EXISTS(SELECT 1 FROM m3_eoe x WHERE x.identity=e.identity),
                EXISTS(SELECT 1 FROM m3_resources x WHERE x.identity=e.identity),
                EXISTS(SELECT 1 FROM m3_rejections x WHERE x.identity=e.identity),
                EXISTS(SELECT 1 FROM m3_timeouts x WHERE x.identity=e.identity)
                FROM m3_execution e LEFT JOIN m3_event_metadata m USING(identity)
                LEFT JOIN m3_disposition d USING(identity)
                WHERE e.first_offset>=? AND e.first_offset>? ORDER BY e.first_offset LIMIT ?''',
                (state['settled'], state['after'], limit)).fetchall()
            events = []
            for row in rows:
                identity, offset, payload, meta_identity, version, arch, profile, observed, received, started, disposition, first, eoe, resource, rejected, timeout = row
                if (type(identity) is not str or not re.fullmatch(r'[0-9]{1,20}\.[0-9]{1,9}:[0-9]{1,20}', identity) or
                        type(offset) is not int or not boundary <= offset < scanned or offset != first or
                        meta_identity != identity or version != 1 or disposition != 'open' or
                        not eoe or resource or rejected or timeout):
                    raise Invalid('contradictory/missing accepted-event witness')
                execution = decoded(payload)
                _canonical_execution(execution)
                if (arch, profile, observed) != (None, None, None):
                    observation(dict(version=1, arch=arch, profile=profile, first_observed_unix_ns=observed))
                stamp(received); stamp(started)
                events.append(dict(format=FORMAT, origin=self.ORIGIN, **self.scope,
                    identity=identity, first_offset=offset, execution=execution,
                    metadata=dict(format=version, arch=arch, profile=profile, first_observed_unix_ns=observed,
                                  received_at=received, persistence_started_at=started)))
            next_state = dict(state, seen_frontier=frontier, seen_scanned=scanned)
            if rows: next_state.update(target=target, after=rows[-1][1])
            else: next_state.update(settled=target, target=None, after=target-1)
        if private(self.directory, directory=True) != directory_id or private(control) != control_id:
            raise Invalid('source binding replaced')
        return events, next_state


DDL = '''
CREATE TABLE m4h_bindings(binding_key TEXT PRIMARY KEY, scope TEXT NOT NULL, directory TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE m4h_events(event_key TEXT PRIMARY KEY, binding_key TEXT NOT NULL REFERENCES m4h_bindings,
 identity TEXT NOT NULL, first_offset INTEGER NOT NULL, envelope TEXT NOT NULL, content_hash TEXT NOT NULL,
 imported_at TEXT NOT NULL, UNIQUE(binding_key,identity), UNIQUE(binding_key,first_offset));
CREATE TABLE m4h_rules(rule_id TEXT NOT NULL,revision TEXT NOT NULL,definition TEXT NOT NULL,content_hash TEXT NOT NULL,
 PRIMARY KEY(rule_id,revision));
CREATE TABLE m4h_evaluations(event_key TEXT NOT NULL REFERENCES m4h_events,rule_id TEXT NOT NULL,revision TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','matched','no_match','unable','error')),reason TEXT,evaluated_at TEXT,
 PRIMARY KEY(event_key,rule_id,revision),FOREIGN KEY(rule_id,revision) REFERENCES m4h_rules);
CREATE TABLE m4h_alerts(alert_id TEXT PRIMARY KEY,event_key TEXT NOT NULL,rule_id TEXT NOT NULL,revision TEXT NOT NULL,
 explanation TEXT NOT NULL,matched_values TEXT NOT NULL,demo INTEGER NOT NULL CHECK(demo=1),
 severity TEXT NOT NULL CHECK(severity='informational'),created_at TEXT NOT NULL,
 UNIQUE(event_key,rule_id,revision),FOREIGN KEY(event_key,rule_id,revision) REFERENCES m4h_evaluations);
'''
TABLES = {'m4h_bindings','m4h_events','m4h_rules','m4h_evaluations','m4h_alerts'}


class Store:
    """Explicitly synthetic-lab destination. No production migration/live switch."""
    GUARD_TYPE = m3_storage.Guard
    APPLICATION_ID = APP_ID
    SCHEMA_VERSION = 1
    SCHEMA_DDL = DDL
    LAB_ONLY = True
    DOMAIN = 'hids.m4.handoff'

    def domain(self, kind):
        return self.DOMAIN + '.' + kind + '/1'

    def __init__(self, directory, *, create=False, max_pages, storage, lab_only):
        if lab_only is not self.LAB_ONLY: raise Invalid('live handoff not enabled')
        if type(max_pages) is not int or not 64 <= max_pages <= 4096: raise Invalid('invalid lab page budget')
        self.directory = Path(directory); self.db = None; self.lock = None
        if not self.directory.is_absolute() or self.directory.resolve() != self.directory:
            raise Invalid('canonical destination required')
        if create: self.directory.mkdir(mode=0o700)
        private(self.directory, directory=True)
        self.path = self.directory / 'handoff.sqlite'
        self.guard = self.GUARD_TYPE(self.directory, max_pages, 1, storage)
        self._files()
        try:
            self.lock = os.open(self.directory/'writer.lock', os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else 0), 0o600)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if create:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600); os.close(fd)
            else:
                probe = sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
                try: self._identity(probe)
                finally: probe.close()
            self.guard.before(self.path)
            self.db = m3_storage.connect(self.path, self.guard)
            self.db.execute('PRAGMA foreign_keys=ON')
            if self.db.execute('PRAGMA journal_mode=WAL').fetchone() != ('wal',): raise Invalid('destination WAL required')
            self.db.execute('PRAGMA synchronous=FULL')
            if self.db.execute(f'PRAGMA max_page_count={max_pages}').fetchone() != (max_pages,): raise Invalid('destination capacity too small')
            if create:
                self.db.executescript('BEGIN IMMEDIATE;'+self.SCHEMA_DDL+f'PRAGMA application_id={self.APPLICATION_ID};PRAGMA user_version={self.SCHEMA_VERSION};COMMIT;')
            self._identity(self.db); self._files()
        except BaseException:
            self.close(); raise

    @classmethod
    def _identity(cls, db):
        if (db.execute('PRAGMA application_id').fetchone() != (cls.APPLICATION_ID,) or db.execute('PRAGMA user_version').fetchone() != (cls.SCHEMA_VERSION,) or
                sorted(r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'")) !=
                sorted(statement.strip() for statement in cls.SCHEMA_DDL.split(';') if statement.strip())):
            raise Invalid('incompatible handoff store')

    def _files(self):
        allowed = {'writer.lock','handoff.sqlite','handoff.sqlite-wal','handoff.sqlite-shm'}
        for path in self.directory.iterdir():
            if path.name not in allowed: raise Invalid('unexpected destination file')
            private(path)

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def import_page(self, source, rules=(), *, limit=64):
        if len(rules) > 8: raise Invalid('too many lab rules')
        rules = [validate_rule(rule) for rule in rules]
        old = self.db.execute('SELECT scope,directory,state FROM m4h_bindings WHERE binding_key=?',(source.key,)).fetchone()
        if old and old[:2] != (canonical(source.scope),str(source.directory)): raise Invalid('binding changed')
        state = json.loads(old[2]) if old else None
        events, next_state = source.read_page(state, limit=limit)
        with self.transaction():
            self.db.execute('INSERT OR IGNORE INTO m4h_bindings VALUES (?,?,?,?)',
                (source.key,canonical(source.scope),str(source.directory),canonical(next_state)))
            for rule in rules:
                definition = canonical(rule)
                previous = self.db.execute('SELECT definition FROM m4h_rules WHERE rule_id=? AND revision=?',(rule['id'],rule['revision'])).fetchone()
                if previous and previous != (definition,): raise Invalid('rule revision conflict')
                self.db.execute('INSERT OR IGNORE INTO m4h_rules VALUES (?,?,?,?)',
                    (rule['id'],rule['revision'],definition,digest(self.domain('rule'),rule)))
            for event in events:
                key = digest(self.domain('event'),[event[k] for k in ('source','activation','generation','identity')])
                envelope = canonical(event)
                previous = self.db.execute('SELECT envelope FROM m4h_events WHERE event_key=?',(key,)).fetchone()
                if previous and previous != (envelope,): raise Invalid('immutable event conflict')
                self.db.execute('INSERT OR IGNORE INTO m4h_events VALUES (?,?,?,?,?,?,?)',
                    (key,source.key,event['identity'],event['first_offset'],envelope,digest(self.domain('content'),event),utc_now()))
                for rule in rules:
                    self.db.execute("INSERT OR IGNORE INTO m4h_evaluations VALUES (?,?,?,'pending',NULL,NULL)",(key,rule['id'],rule['revision']))
            self.db.execute('UPDATE m4h_bindings SET state=? WHERE binding_key=?',(canonical(next_state),source.key))
        return len(events)

    def evaluate_pending(self, *, limit=64):
        if type(limit) is not int or not 1 <= limit <= 64: raise Invalid('invalid evaluation budget')
        pending = self.db.execute("SELECT event_key,rule_id,revision FROM m4h_evaluations WHERE state='pending' ORDER BY rowid LIMIT ?",(limit,)).fetchall()
        for key, rule_id, revision in pending:
            with self.transaction():
                envelope, content_hash, definition, rule_hash = self.db.execute('''SELECT e.envelope,e.content_hash,r.definition,r.content_hash
                    FROM m4h_events e,m4h_rules r WHERE e.event_key=? AND r.rule_id=? AND r.revision=?''',(key,rule_id,revision)).fetchone()
                try:
                    event, rule = decoded(envelope), validate_rule(decoded(definition))
                    if (event['format'] != FORMAT or event['origin'] != 'synthetic_lab' or rule['id'] != rule_id or rule['revision'] != revision or
                            digest(self.domain('event'),[event[k] for k in ('source','activation','generation','identity')]) != key or
                            digest(self.domain('content'),event) != content_hash or digest(self.domain('rule'),rule) != rule_hash):
                        raise Invalid('stored snapshot conflict')
                    _canonical_execution(event['execution'])
                    if event['metadata']['profile'] is None: state,reason,values='unable','source_profile_unknown',{}
                    else: state,reason,values=evaluate(event['execution'],rule)
                except Exception:
                    state,reason,values='error','evaluation_failed',{}
                when=utc_now()
                self.db.execute('UPDATE m4h_evaluations SET state=?,reason=?,evaluated_at=? WHERE event_key=? AND rule_id=? AND revision=?',
                    (state,reason,when,key,rule_id,revision))
                if state=='matched':
                    self.db.execute('INSERT INTO m4h_alerts VALUES (?,?,?,?,?,?,1,?,?)',
                        (digest(self.domain('alert'),[key,rule_id,revision]),key,rule_id,revision,rule['explanation'],canonical(values),rule['severity'],when))
        return len(pending)

    def summary(self):
        return dict(lab_only=self.LAB_ONLY,events=self.db.execute('SELECT count(*) FROM m4h_events').fetchone()[0],
            pending=self.db.execute("SELECT count(*) FROM m4h_evaluations WHERE state='pending'").fetchone()[0],
            alerts=self.db.execute('SELECT count(*) FROM m4h_alerts').fetchone()[0],
            unevaluated=self.db.execute('SELECT count(*) FROM m4h_events e WHERE NOT EXISTS (SELECT 1 FROM m4h_evaluations v WHERE v.event_key=e.event_key)').fetchone()[0],
            evaluations=dict(self.db.execute('SELECT state,count(*) FROM m4h_evaluations GROUP BY state').fetchall()))

    def close(self):
        if self.db is not None: self.db.close(); self.db=None
        if self.lock is not None: os.close(self.lock); self.lock=None

    def __enter__(self): return self
    def __exit__(self,*_): self.close()


class Worker:
    """Fair bounded lab scheduler; each binding releases source reads per page."""
    def __init__(self, store, sources, rules=(), *, clock=time.monotonic, page_limit=64):
        if not 1 <= len(sources) <= 8 or len({s.key for s in sources}) != len(sources): raise Invalid('invalid selected bindings')
        if type(page_limit) is not int or not 1 <= page_limit <= 64: raise Invalid('invalid page limit')
        self.page_limit=page_limit
        self.store,self.sources,self.rules,self.clock=store,sources,rules,clock
        self.retry={}; self.status={}

    def step(self):
        for source in self.sources:
            failures, until=self.retry.get(source.key,(0,0))
            if self.clock()<until: continue
            try:
                count=self.store.import_page(source,self.rules,limit=self.page_limit)
            except (Invalid,ProgressError): code='source_invalid'
            except (OSError,sqlite3.Error): code='source_or_destination_unavailable'
            except m3_storage.StoragePressure: code='destination_pressure'
            else:
                self.retry.pop(source.key,None);self.status[source.key]='imported' if count else 'idle';continue
            failures=min(failures+1,5)
            self.retry[source.key]=(failures,self.clock()+min(30,2**failures))
            self.status[source.key]=code
        self.store.evaluate_pending()
        return dict(self.store.summary(),bindings=dict(self.status))
