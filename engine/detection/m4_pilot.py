"""Opt-in synthetic M4 pilot. No live source, M3 database or executable rules."""
import base64
import binascii
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid

from engine.ingestion.m1_contract import utc_now
from engine.ingestion.m3_event import PROFILE
from engine.ingestion.m3_progress import _canonical_execution, ProgressError

APPLICATION_ID = 0x48345031
STORE_VERSION = 1
FIELDS = frozenset(('exe_base64', 'uid', 'auid', 'success'))
TABLES = {'m4p_events', 'm4p_rules', 'm4p_evaluations', 'm4p_alerts'}


class Invalid(ValueError):
    """Invalid fixture, rule, conflicting identity or incompatible store."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def digest(domain, value):
    return hashlib.sha256(domain.encode('ascii') + b'\0' + canonical(value).encode('ascii')).hexdigest()


def load_json(path):
    """Bounded JSON input, with duplicate keys and non-JSON constants rejected."""
    def pairs(items):
        result = dict(items)
        if len(result) != len(items):
            raise Invalid('duplicate JSON key')
        return result
    def constant(_):
        raise Invalid('invalid JSON constant')
    with Path(path).open('rb') as stream:
        raw = stream.read(32769)
    if len(raw) > 32768:
        raise Invalid('pilot input exceeds 32 KiB')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise Invalid('invalid pilot JSON') from None
    # Python JSON recursion limits differ across versions. Enforce our own bound.
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 16 or nodes > 2048:
            raise Invalid('pilot JSON nesting/node bound exceeded')
        children = item.values() if type(item) is dict else item if type(item) is list else ()
        pending.extend((child, depth + 1) for child in children)
    return value


def validate_event(value):
    fields = {'version', 'synthetic', 'profile', 'source', 'activation', 'generation', 'identity', 'execution'}
    if type(value) is not dict or value.keys() != fields:
        raise Invalid('invalid fixture envelope')
    if type(value['version']) is not int or value['version'] != 1 or value['synthetic'] is not True:
        raise Invalid('synthetic version-1 fixtures only')
    if value['profile'] != PROFILE:
        raise Invalid('unsupported source profile')
    for field in ('source', 'activation', 'generation'):
        item = value[field]
        try:
            if type(item) is not str or str(uuid.UUID(item)) != item:
                raise Invalid('noncanonical scope UUID')
        except (ValueError, AttributeError):
            raise Invalid('invalid scope UUID') from None
    if type(value['identity']) is not str or not re.fullmatch(r'[0-9]{1,20}\.[0-9]{1,9}:[0-9]{1,20}', value['identity']):
        raise Invalid('invalid native identity')
    try:
        _canonical_execution(value['execution'])
    except ProgressError as exc:
        raise Invalid(str(exc)) from None
    # Copy through canonical JSON so later caller mutation cannot change validation.
    return json.loads(canonical(value))


def event_key(event):
    return digest('hids.m4.fixture.event/1', [event[k] for k in ('source', 'activation', 'generation', 'identity')])


def validate_rule(value):
    fields = {'version', 'id', 'revision', 'profile', 'demo', 'severity', 'required', 'all_of', 'explanation'}
    if type(value) is not dict or value.keys() != fields:
        raise Invalid('invalid rule shape')
    if type(value['version']) is not int or value['version'] != 1 or value['profile'] != PROFILE:
        raise Invalid('unsupported rule version/profile')
    if value['demo'] is not True or value['severity'] != 'informational':
        raise Invalid('informational demo rules only')
    for field in ('id', 'revision'):
        if type(value[field]) is not str or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}', value[field]):
            raise Invalid('invalid rule identity')
    text = value['explanation']
    if type(text) is not str or not 1 <= len(text) <= 512 or any(ord(c) < 32 for c in text):
        raise Invalid('invalid fixed explanation')
    required = value['required']
    if (type(required) is not list or not 1 <= len(required) <= 4 or
            any(type(k) is not str or k not in FIELDS for k in required) or len(set(required)) != len(required)):
        raise Invalid('invalid required fields')
    predicates = value['all_of']
    if type(predicates) is not list or not 1 <= len(predicates) <= 4:
        raise Invalid('invalid predicate count')
    used = set()
    for predicate in predicates:
        if type(predicate) is not dict or predicate.keys() != {'field', 'eq'}:
            raise Invalid('only field/eq predicates are supported')
        field = predicate['field']
        if type(field) is not str or field not in required or field in used:
            raise Invalid('unsupported, undeclared or repeated predicate field')
        used.add(field)
        item = predicate['eq']
        if field == 'success':
            if type(item) is not bool:
                raise Invalid('success requires a Boolean')
        elif field in ('uid', 'auid'):
            if type(item) is not int or not 0 <= item < 2**32:
                raise Invalid('UID requires uint32')
        else:
            if type(item) is not str or not 0 < len(item) <= 5464:
                raise Invalid('invalid encoded executable')
            try:
                raw = base64.b64decode(item, validate=True)
            except (ValueError, binascii.Error):
                raise Invalid('invalid encoded executable') from None
            if not 0 < len(raw) <= 4096 or b'\0' in raw or base64.b64encode(raw).decode('ascii') != item:
                raise Invalid('invalid encoded executable')
    return json.loads(canonical(value))


def evaluate(execution, rule):
    """Pure, one-event evaluation: no store, history, I/O or executable expressions."""
    _canonical_execution(execution)
    rule = validate_rule(rule)
    if any(execution.get(field) is None for field in rule['required']):
        return 'unable', 'required_value_unknown', {}
    if not all(execution[p['field']] == p['eq'] for p in rule['all_of']):
        return 'no_match', 'predicate_not_equal', {}
    return 'matched', 'all_predicates_equal', {p['field']: execution[p['field']] for p in rule['all_of']}


DDL = '''
CREATE TABLE m4p_events (
 event_key TEXT PRIMARY KEY, source TEXT NOT NULL, activation TEXT NOT NULL,
 generation TEXT NOT NULL, identity TEXT NOT NULL, profile TEXT NOT NULL,
 payload TEXT NOT NULL, payload_hash TEXT NOT NULL, received_at TEXT NOT NULL,
 UNIQUE(source,activation,generation,identity));
CREATE TABLE m4p_rules (
 rule_id TEXT NOT NULL, revision TEXT NOT NULL, definition TEXT NOT NULL,
 definition_hash TEXT NOT NULL, PRIMARY KEY(rule_id,revision));
CREATE TABLE m4p_evaluations (
 event_key TEXT NOT NULL REFERENCES m4p_events(event_key), rule_id TEXT NOT NULL,
 revision TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN
 ('pending','matched','no_match','unable','error')), reason TEXT, evaluated_at TEXT,
 PRIMARY KEY(event_key,rule_id,revision),
 FOREIGN KEY(rule_id,revision) REFERENCES m4p_rules(rule_id,revision));
CREATE TABLE m4p_alerts (
 alert_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, rule_id TEXT NOT NULL,
 revision TEXT NOT NULL, explanation TEXT NOT NULL, matched_values TEXT NOT NULL,
 demo INTEGER NOT NULL CHECK(demo=1), severity TEXT NOT NULL CHECK(severity='informational'),
 created_at TEXT NOT NULL, UNIQUE(event_key,rule_id,revision),
 FOREIGN KEY(event_key,rule_id,revision) REFERENCES m4p_evaluations(event_key,rule_id,revision));
'''


class Store:
    """One writer, explicit create/open, fresh private fixture stores only.

    Callers must use a trusted canonical parent. Same-UID/root compromise is outside
    this offline prototype's protection. No production migration/retention is provided.
    """
    def __init__(self, directory, *, create=False):
        self.db = None
        self.lock = None
        self.directory = Path(os.path.abspath(directory))
        if self.directory.resolve() != self.directory:
            raise Invalid('canonical store path required')
        if create:
            self.directory.mkdir(mode=0o700)  # Exclusive: never adopt existing data.
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Invalid('store directory must be owner-private 0700')
        self.path = self.directory / 'pilot.sqlite'
        self._files()
        if not create and not self.path.exists():
            raise Invalid('missing prototype database')
        try:
            self.lock = os.open(self.directory / 'writer.lock', os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else 0), 0o600)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if create:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                os.close(fd)
            else:
                # Verify identity read-only BEFORE enabling writes, WAL or schema changes.
                probe = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
                try:
                    self._identity(probe)
                finally:
                    probe.close()
            self.db = sqlite3.connect(self.path, isolation_level=None, timeout=1)
            self.db.execute('PRAGMA foreign_keys=ON')
            if self.db.execute('PRAGMA journal_mode=WAL').fetchone()[0] != 'wal':
                raise Invalid('WAL required')
            self.db.execute('PRAGMA synchronous=FULL')
            if create:
                self.db.executescript('BEGIN IMMEDIATE;\n' + DDL +
                    f'PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version={STORE_VERSION}; COMMIT;')
            self._identity(self.db)
            self._files()
        except BaseException:
            self.close()
            raise

    def _files(self):
        allowed = {'pilot.sqlite', 'pilot.sqlite-wal', 'pilot.sqlite-shm', 'writer.lock'}
        for file in self.directory.iterdir():
            info = file.lstat()
            if (file.name not in allowed or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise Invalid('unexpected or unsafe prototype file')

    @staticmethod
    def _identity(db):
        if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                db.execute('PRAGMA user_version').fetchone()[0] != STORE_VERSION or
                {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} != TABLES):
            raise Invalid('not a compatible M4 prototype store')

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def receive(self, envelope, definition):
        event, rule = validate_event(envelope), validate_rule(definition)
        key = event_key(event)
        payload, snapshot = canonical(event), canonical(rule)
        payload_hash = digest('hids.m4.fixture.payload/1', event)
        rule_hash = digest('hids.m4.fixture.rule/1', rule)
        with self.transaction():
            existing = self.db.execute('SELECT definition FROM m4p_rules WHERE rule_id=? AND revision=?', (rule['id'], rule['revision'])).fetchone()
            if existing is not None and existing[0] != snapshot:
                raise Invalid('rule revision conflict')
            self.db.execute('INSERT OR IGNORE INTO m4p_rules VALUES (?,?,?,?)', (rule['id'], rule['revision'], snapshot, rule_hash))
            existing = self.db.execute('SELECT payload FROM m4p_events WHERE event_key=?', (key,)).fetchone()
            if existing is not None and existing[0] != payload:
                raise Invalid('event identity conflict')
            self.db.execute('INSERT OR IGNORE INTO m4p_events VALUES (?,?,?,?,?,?,?,?,?)',
                (key, event['source'], event['activation'], event['generation'], event['identity'], event['profile'], payload, payload_hash, utc_now()))
            self.db.execute("INSERT OR IGNORE INTO m4p_evaluations VALUES (?,?,?,'pending',NULL,NULL)", (key, rule['id'], rule['revision']))
        return key

    def evaluate(self, key, rule_id, revision):
        args = (key, rule_id, revision)
        with self.transaction():
            row = self.db.execute('''SELECT v.state,e.payload,e.payload_hash,r.definition,r.definition_hash
                FROM m4p_evaluations v JOIN m4p_events e USING(event_key)
                JOIN m4p_rules r USING(rule_id,revision)
                WHERE v.event_key=? AND v.rule_id=? AND v.revision=?''', args).fetchone()
            if row is None:
                raise Invalid('unknown evaluation')
            if row[0] != 'pending':
                return row[0]
            try:
                event, rule = validate_event(json.loads(row[1])), validate_rule(json.loads(row[3]))
                if (event_key(event) != key or rule['id'] != rule_id or rule['revision'] != revision or
                        digest('hids.m4.fixture.payload/1', event) != row[2] or digest('hids.m4.fixture.rule/1', rule) != row[4]):
                    raise Invalid('stored snapshot conflict')
            except (ValueError, ProgressError, RecursionError, TypeError):
                state, reason, values = 'error', 'stored_snapshot_invalid', {}
            else:
                try:
                    state, reason, values = evaluate(event['execution'], rule)
                except Exception:
                    state, reason, values = 'error', 'evaluation_failed', {}
            when = utc_now()
            self.db.execute('UPDATE m4p_evaluations SET state=?,reason=?,evaluated_at=? WHERE event_key=? AND rule_id=? AND revision=?', (state, reason, when, *args))
            if state == 'matched':
                alert = digest('hids.m4.fixture.alert/1', list(args))
                self.db.execute('INSERT INTO m4p_alerts VALUES (?,?,?,?,?,?,1,?,?)',
                    (alert, *args, rule['explanation'], canonical(values), rule['severity'], when))
        return state

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
