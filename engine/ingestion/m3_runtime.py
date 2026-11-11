"""Python-owned activation state for a non-replayable Audit plugin stream."""

import os
import fcntl
import sqlite3
import uuid

from engine.database.m1_store import check_sidecars, connect, profile
from engine.ingestion.m1_contract import utc_now, uuid_valid
from engine.ingestion.m1_security import private_directory, private_file
from engine.ingestion.m3_progress import CapacityError, Progress, ProgressError, event_health as read_event_health
from engine.ingestion import m3_health

ACTIVE = ('ready', 'streaming')
SOURCE_GAPS = frozenset(('collector_input_failure', 'assembly_timeout', 'collector_capacity',
                         'incomplete_shutdown', 'current_tail_unavailable', 'collector_delivery_failure'))
CODES = frozenset(('backend_restart', 'stream_disconnected', 'partial_frame',
                   'protocol_failure', 'deadline', 'storage_failure', 'revoked',
                   'service_shutdown', 'progress_capacity')) | SOURCE_GAPS
V3_DDL = (
    'CREATE TABLE m3_source (singleton INTEGER PRIMARY KEY CHECK(singleton=1), source TEXT NOT NULL)',
    "CREATE TABLE m3_intervals (activation TEXT PRIMARY KEY, generation TEXT NOT NULL UNIQUE, lease TEXT NOT NULL UNIQUE, state TEXT NOT NULL CHECK(state IN ('ready','streaming','interrupted','revoked')), code TEXT, authorized_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE UNIQUE INDEX m3_one_active ON m3_intervals ((1)) WHERE state IN ('ready','streaming')",
)
DDL = V3_DDL + (m3_health.DDL,)


def private_database(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    private_file(path, writable=True)
    check_sidecars(path)


class Runtime:
    def __init__(self, directory, source, *, max_activations, max_pages, position_limit):
        if not uuid_valid(source):
            raise ProgressError('invalid source identity')
        if type(max_activations) is not int or not 1 <= max_activations <= 65536:
            raise ProgressError('invalid activation budget')
        if type(max_pages) is not int or not 32 <= max_pages < 2147483647:
            raise ProgressError('invalid page budget')
        if type(position_limit) is not int or not 1 <= position_limit <= 65536:
            raise ProgressError('invalid position budget')
        self.directory = private_directory(directory)
        self.source = source
        self.max_activations, self.max_pages = max_activations, max_pages
        self.position_limit = position_limit
        self.progress = None
        self.db = None
        self.lock = None
        self.path = self.directory / 'control.sqlite'
        fresh = not self.path.exists() and not self.path.is_symlink()
        try:
            lock_path = self.directory / 'writer.lock'
            self.lock = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            private_file(lock_path, writable=True)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            private_database(self.path)
            self.db = connect(self.path)
            profile(self.db, fresh=fresh)
            if self.db.execute(f'PRAGMA max_page_count={max_pages}').fetchone()[0] != max_pages:
                raise ProgressError('control page budget below existing database size')
            if fresh:
                self.db.execute('BEGIN IMMEDIATE')
                for sql in DDL:
                    self.db.execute(sql)
                self.db.execute('INSERT INTO m3_source VALUES (1,?)', (source,))
                self.db.execute('PRAGMA user_version=4')
                self.db.execute('COMMIT')
            actual = self.db.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
            if sorted(row[0] for row in actual) == sorted(V3_DDL) and self.db.execute('PRAGMA user_version').fetchone() == (3,):
                self.db.execute('BEGIN IMMEDIATE')
                try:
                    self.db.execute(m3_health.DDL)
                    self.db.execute('PRAGMA user_version=4')
                    self.db.execute('COMMIT')
                except BaseException:
                    if self.db.in_transaction:
                        self.db.execute('ROLLBACK')
                    raise
                actual = self.db.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
            if sorted(row[0] for row in actual) != sorted(DDL) or self.db.execute('PRAGMA user_version').fetchone() != (4,):
                raise ProgressError('unexpected M3 control schema')
            if self.db.execute('SELECT source FROM m3_source').fetchall() != [(source,)]:
                raise ProgressError('control source mismatch')
            # Even a clean-looking stream cannot prove continuity across a backend
            # restart. Reconcile its durable rows before recording the interruption.
            for activation, generation in self.db.execute(
                    "SELECT activation,generation FROM m3_intervals WHERE state IN ('ready','streaming')").fetchall():
                self.progress = self.open_progress(activation, generation)
                self.interrupt('backend_restart')
        except BaseException:
            self.close()
            raise

    def current(self):
        row = self.db.execute('SELECT activation,generation,lease,state,code,authorized_at,updated_at FROM m3_intervals ORDER BY rowid DESC LIMIT 1').fetchone()
        fields = ('activation', 'generation', 'lease', 'state', 'code', 'authorized_at', 'updated_at')
        return dict(zip(fields, row)) if row else None

    def open_progress(self, activation, generation, *, create=False):
        if not uuid_valid(activation) or not uuid_valid(generation):
            raise ProgressError('invalid interval scope')
        path = self.directory / f'{activation}.sqlite'
        if not create and not path.exists():
            raise ProgressError('missing activation database')
        private_database(path)
        return Progress(path, activation, generation, 0,
                        position_limit=self.position_limit, max_pages=self.max_pages)

    def activate(self, activation):
        if not uuid_valid(activation):
            raise ProgressError('invalid activation identity')
        current = self.current()
        if current and current['state'] in ACTIVE:
            if current['activation'] == activation:
                return current
            raise ProgressError('source already active')
        if self.progress is not None:
            raise ProgressError('runtime requires explicit restart after reconciliation failure')
        if self.db.execute('SELECT 1 FROM m3_intervals WHERE activation=?', (activation,)).fetchone():
            raise ProgressError('activation already ended')
        # Count orphan files as well as committed intervals. A crash between ledger
        # creation and control commit must never permit unbounded orphan growth.
        if len(list(self.directory.glob('*.sqlite'))) - 1 >= self.max_activations:
            raise CapacityError('activation capacity exhausted')
        path = self.directory / f'{activation}.sqlite'
        if path.exists() or path.is_symlink():
            raise ProgressError('uncommitted activation file')
        generation, lease = str(uuid.uuid4()), str(uuid.uuid4())
        progress = self.open_progress(activation, generation, create=True)
        try:
            observed = utc_now()
            self.db.execute('INSERT INTO m3_intervals VALUES (?,?,?, ?,NULL,?,?)',
                            (activation, generation, lease, 'ready', observed, observed))
        except BaseException:
            progress.close()
            raise
        self.progress = progress
        return self.current()

    def claim(self):
        current = self.current()
        if not current or current['state'] != 'ready' or self.progress is None:
            raise ProgressError('reader lease unavailable')
        self.db.execute("UPDATE m3_intervals SET state='streaming',updated_at=? WHERE activation=? AND state='ready'",
                        (utc_now(), current['activation']))
        return {key: current[key] for key in ('activation', 'generation', 'lease')}

    def interrupt(self, code):
        if code not in CODES:
            raise ProgressError('invalid interruption code')
        current = self.current()
        if not current or current['state'] not in ACTIVE:
            return
        # Reconciliation may be retried after a crash. No later startup opens this
        # authorization for accepted input, even if the control update did not commit.
        try:
            if self.progress is not None:
                self.progress.recover()
        except Exception:
            # The control database can retain the failure even when the event
            # database cannot reconcile. Its unresolved rows stay unresolved.
            self.db.execute("UPDATE m3_intervals SET state='interrupted',code='storage_failure',updated_at=? WHERE activation=?",
                            (utc_now(), current['activation']))
            raise
        self.db.execute('UPDATE m3_intervals SET state=?,code=?,updated_at=? WHERE activation=?',
                        ('revoked' if code == 'revoked' else 'interrupted', code, utc_now(), current['activation']))
        if self.progress is not None:
            self.progress.close()
            self.progress = None

    def revoke(self, activation):
        current = self.current()
        if not current or current['activation'] != activation:
            raise ProgressError('stale activation')
        if current['state'] in ACTIVE:
            self.interrupt('revoked')
        elif current['state'] != 'revoked':
            self.db.execute("UPDATE m3_intervals SET state='revoked',updated_at=? WHERE activation=?",
                            (utc_now(), activation))

    def status(self):
        current = self.current()
        try:
            upstream = m3_health.status(self.db, current)
        except (sqlite3.Error, ProgressError):
            upstream = None
        event_health = None
        ready = False
        evidence_unavailable = False
        try:
            if self.progress is not None:
                event_health = self.progress.event_health()
                ready = bool(current and current['state'] == 'streaming' and self.progress.stream_started())
            elif current is not None:
                # Read committed history after revocation/restart without opening
                # a writer or reconstructing interrupted native payloads.
                path = self.directory / (current['activation'] + '.sqlite')
                private_file(path, writable=True)
                history = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=.1)
                try:
                    if history.execute('SELECT activation,generation FROM m3_cursor').fetchone() != (
                            current['activation'], current['generation']):
                        raise ProgressError('event health scope mismatch')
                    event_health = read_event_health(history)
                finally:
                    history.close()
        except (OSError, sqlite3.Error, ProgressError):
            evidence_unavailable = True
        return {'source': self.source, 'interval': current,
                'source_ready': ready,
                # A live, authorized reader proves no upstream queue continuity.
                # The unprivileged service does not observe these host counters.
                'upstream_loss': {key: upstream[key] if upstream is not None else 'unknown'
                                  for key in ('kernel', 'dispatcher')},
                'upstream_health': upstream,
                'event_health': event_health,
                'possible_gap': bool(evidence_unavailable or (upstream and (any(upstream['summary']['incidents'].values()) or upstream['freshness'] == 'stale')) or
                                     (current and current['code'] not in (None, 'revoked')) or
                                     (event_health and (event_health['timeouts'] or event_health['resource_incidents'])))}

    def close(self):
        if self.progress is not None:
            self.progress.close()
            self.progress = None
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
