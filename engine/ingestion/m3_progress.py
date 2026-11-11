"""Offline progress ledger for one externally verified activation and generation."""

import base64
import binascii
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class ProgressError(ValueError):
    """The requested transition conflicts with durable source state."""


class CapacityError(ProgressError):
    """An explicit metadata budget prevents further source progress."""


def _timeout_evidence(value):
    numbers = {'first_active_ms', 'last_active_ms', 'observed_active_ms',
               'observed_monotonic_ms', 'paused_ms', 'inactivity_limit_ms', 'lifetime_limit_ms'}
    if type(value) is not dict or value.keys() != numbers | {'policy', 'reason'}:
        raise ProgressError('invalid timeout evidence')
    if type(value['policy']) is not int or value['policy'] != 1 or value['reason'] not in (
            'inactivity', 'lifetime'):
        raise ProgressError('invalid timeout policy')
    if any(type(value[key]) is not int or not 0 <= value[key] < 2**63 for key in numbers):
        raise ProgressError('invalid timeout timing')
    first, last, active, mono, paused, inactivity, lifetime = (
        value[key] for key in ('first_active_ms', 'last_active_ms', 'observed_active_ms',
                              'observed_monotonic_ms', 'paused_ms', 'inactivity_limit_ms', 'lifetime_limit_ms'))
    if not (first <= last <= active <= mono and paused == mono-active and inactivity and lifetime):
        raise ProgressError('inconsistent timeout timing')
    if active-(first if value['reason'] == 'lifetime' else last) < (
            lifetime if value['reason'] == 'lifetime' else inactivity):
        raise ProgressError('deadline has not expired')
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _canonical_execution(execution):
    """Independently validate the closed offline event shape."""
    integers = {"syscall", "pid", "ppid", "uid", "euid", "suid", "fsuid", "path_count"}
    optional = {"auid", "session"}
    flags = {"success", "cwd_present", "proctitle_present"}
    encoded = {"exe_base64": 4096, "comm_base64": 256}
    if type(execution) is not dict or execution.keys() != (
        integers | optional | flags | encoded.keys() | {"result"}
    ):
        raise ProgressError("invalid execution shape")
    for field in integers | optional:
        value = execution[field]
        if field in optional and value is None:
            continue
        if type(value) is not int or not 0 <= value < 2**32:
            raise ProgressError("invalid execution number")
    if execution["pid"] == 0 or execution["syscall"] not in (221, 281):
        raise ProgressError("invalid execution identity")
    if any(type(execution[field]) is not bool for field in flags):
        raise ProgressError("invalid execution flag")
    result = execution["result"]
    if type(result) is not int or not -(2**63) <= result <= 0 or (
        execution["success"] != (result == 0)
    ):
        raise ProgressError("invalid execution outcome")
    for field, limit in encoded.items():
        value = execution[field]
        if type(value) is not str or not 0 < len(value) <= 4 * ((limit + 2) // 3):
            raise ProgressError("invalid executable encoding")
        try:
            raw = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise ProgressError("invalid executable encoding") from None
        if not 0 < len(raw) <= limit or b"\0" in raw or base64.b64encode(raw).decode() != value:
            raise ProgressError("invalid executable encoding")
    return json.dumps(execution, sort_keys=True, separators=(",", ":"))


class Progress:
    """Persist sanitized admission and final disposition before advancing.

    The owner supplies a private SQLite database and serializes operations.
    Live lease, source verification, and rotation belong to the caller.
    """

    def __init__(self, path, activation, generation, boundary, *, position_limit=65536,
                 max_pages=None):
        if type(position_limit) is not int or position_limit < 1:
            raise ProgressError("invalid position limit")
        self.position_limit = position_limit
        if type(boundary) is not int or not 0 <= boundary < 2**63:
            raise ProgressError("invalid boundary")
        if Path(path).name in ("", ":memory:"):
            raise ProgressError("durable database path required")
        if max_pages is not None and (type(max_pages) is not int or max_pages < 32):
            raise ProgressError("invalid page budget")
        self.db = sqlite3.connect(path, isolation_level=None, timeout=1)
        try:
            if self.db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
                raise ProgressError("WAL unavailable")
            self.db.execute("PRAGMA synchronous=FULL")
            if max_pages is not None:
                actual = self.db.execute(f"PRAGMA max_page_count={max_pages}").fetchone()[0]
                if actual != max_pages:
                    raise ProgressError("page budget below existing database size")
            with self._transaction():
                self.db.execute("""CREATE TABLE IF NOT EXISTS m3_cursor (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    activation TEXT NOT NULL, generation TEXT NOT NULL,
                    boundary INTEGER NOT NULL, scanned INTEGER NOT NULL,
                    frontier INTEGER NOT NULL
                )""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS m3_stream_start (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1)
                )""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS m3_disposition (
                    identity TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK(state IN ('open','rejected','interrupted'))
                )""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS m3_positions (
                    begin INTEGER PRIMARY KEY, end INTEGER NOT NULL, identity TEXT NOT NULL,
                    CHECK(end > begin)
                )""")
                self.db.execute("""CREATE INDEX IF NOT EXISTS m3_positions_identity
                    ON m3_positions(identity)""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS m3_eoe (
                    identity TEXT PRIMARY KEY, begin INTEGER NOT NULL
                )""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS m3_execution (
                    identity TEXT PRIMARY KEY, first_offset INTEGER NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )""")
                self.db.execute('CREATE TABLE IF NOT EXISTS m3_resources (identity TEXT PRIMARY KEY, evidence TEXT NOT NULL)')
                self.db.execute('CREATE TABLE IF NOT EXISTS m3_timeouts (identity TEXT PRIMARY KEY, evidence TEXT NOT NULL)')
                self.db.execute('CREATE TABLE IF NOT EXISTS m3_late_positions (begin INTEGER PRIMARY KEY, eoe INTEGER NOT NULL CHECK(eoe IN (0,1)), final_state TEXT NOT NULL)')
                scope = (activation, generation, boundary)
                self.db.execute("INSERT OR IGNORE INTO m3_cursor VALUES (1,?,?,?,?,?)",
                                (*scope, boundary, boundary))
                if self.db.execute(
                    "SELECT activation,generation,boundary FROM m3_cursor"
                ).fetchone() != scope:
                    raise ProgressError("source scope mismatch")
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def positions(self):
        return self.db.execute("SELECT scanned,frontier FROM m3_cursor").fetchone()

    def stream_started(self):
        return self.db.execute('SELECT 1 FROM m3_stream_start').fetchone() == (1,)

    def start_stream(self):
        with self._transaction():
            if self.positions() != (0, 0):
                raise ProgressError('source boundary must precede admission')
            self.db.execute('INSERT OR IGNORE INTO m3_stream_start VALUES (1)')
        return 'boundary'

    def register(self, identity, begin, end, *, eoe=False):
        """Return the durable classification. Only 'admit' permits assembly."""
        if not re.fullmatch(r"[0-9]{1,20}\.[0-9]{1,9}:[0-9]{1,20}", identity):
            raise ProgressError("invalid native identity")
        if (type(eoe) is not bool or type(begin) is not int or type(end) is not int
                or not 0 <= begin < end < 2**63):
            raise ProgressError("invalid source position")
        with self._transaction():
            scanned, _ = self.positions()
            if begin < scanned:
                existing = self.db.execute(
                    "SELECT end,identity FROM m3_positions WHERE begin=?", (begin,)
                ).fetchone()
                stored_eoe = self.db.execute(
                    "SELECT 1 FROM m3_eoe WHERE identity=? AND begin=?", (identity, begin)
                ).fetchone()
                late = self.db.execute('SELECT eoe FROM m3_late_positions WHERE begin=?', (begin,)).fetchone()
                if late is not None:
                    stored_eoe = bool(late[0])
                if existing != (end, identity) or (eoe != bool(stored_eoe) and
                                                   (late is not None or self._state(identity) != "interrupted")):
                    raise ProgressError("conflicting position replay")
                return "replay"
            if begin != scanned:
                raise ProgressError("noncontiguous registration")
            if self.db.execute("SELECT COUNT(*) FROM m3_positions").fetchone()[0] >= self.position_limit:
                raise CapacityError("progress capacity exhausted")
            self.db.execute("INSERT OR IGNORE INTO m3_disposition VALUES (?, 'open')", (identity,))
            state = self._state(identity)
            if state == "open" and self.db.execute(
                "SELECT 1 FROM m3_eoe WHERE identity=?", (identity,)
            ).fetchone():
                raise ProgressError("new position for finalized identity")
            if eoe and state == "open":
                self.db.execute("INSERT INTO m3_eoe VALUES (?,?)", (identity, begin))
            self.db.execute("INSERT INTO m3_positions VALUES (?,?,?)", (begin, end, identity))
            self.db.execute("UPDATE m3_cursor SET scanned=?", (end,))
            if state in ('accepted', 'rejected', 'interrupted'):
                self.db.execute('INSERT INTO m3_late_positions VALUES (?,?,?)', (begin, int(eoe), state))
                self._advance()
                return "suppressed"
            return "admit"

    def timeout(self, identity, evidence):
        """Durably reject one expired assembly without closing unrelated events."""
        payload = _timeout_evidence(evidence)
        with self._transaction():
            existing = self.db.execute('SELECT evidence FROM m3_timeouts WHERE identity=?', (identity,)).fetchone()
            if existing is not None:
                if existing != (payload,):
                    raise ProgressError('conflicting timeout retry')
                return 'timed_out'
            if self._state(identity) != 'open' or self.db.execute(
                    'SELECT 1 FROM m3_eoe WHERE identity=?', (identity,)).fetchone():
                raise ProgressError('identity is not eligible for timeout')
            self.db.execute('INSERT INTO m3_timeouts VALUES (?,?)', (identity, payload))
            self.db.execute("UPDATE m3_disposition SET state='rejected' WHERE identity=?", (identity,))
            self._advance()
            return 'timed_out'

    def event_health(self):
        return event_health(self.db)

    def resource(self, identity, evidence):
        from engine.ingestion.m3_resource import validate
        payload = validate(evidence)
        with self._transaction():
            existing = self.db.execute('SELECT evidence FROM m3_resources WHERE identity=?', (identity,)).fetchone()
            if existing is not None:
                if existing != (payload,):
                    raise ProgressError('conflicting resource incident')
                return 'resource_recorded'
            if self._state(identity) != 'open':
                raise ProgressError('identity is not eligible for resource discard')
            trigger = self.db.execute('SELECT end,identity FROM m3_positions WHERE begin=?', (evidence['trigger_begin'],)).fetchone()
            if trigger is None or trigger[0] != evidence['trigger_end'] or self.positions()[0] != trigger[0]:
                raise ProgressError('resource trigger is not the admitted tail')
            same = trigger[1] == identity
            if evidence['incoming_for_event'] != same:
                raise ProgressError('resource trigger owner mismatch')
            length = evidence['trigger_end']-evidence['trigger_begin']
            count, size = self.db.execute('SELECT COUNT(*),SUM(end-begin) FROM m3_positions WHERE identity=?', (identity,)).fetchone()
            if (count != evidence['event_records_before']+int(same) or
                    size != evidence['event_bytes_before']+(length if same else 0)):
                raise ProgressError('resource event ownership accounting mismatch')
            self.db.execute('INSERT INTO m3_resources VALUES (?,?)', (identity,payload))
            # Incident durability does not resolve an incomplete event. Its known
            # positions continue blocking until EOE, timeout or interruption.
            return 'resource_recorded'

    def _state(self, identity):
        row = self.db.execute(
            """SELECT CASE WHEN e.identity IS NULL THEN d.state ELSE 'accepted' END
               FROM m3_disposition d LEFT JOIN m3_execution e USING(identity)
               WHERE d.identity=?""", (identity,),
        ).fetchone()
        return row[0] if row else None

    def accept(self, identity, execution):
        """Commit the validated fixture event and its checkpoint together."""
        payload = _canonical_execution(execution)
        with self._transaction():
            existing = self.db.execute(
                "SELECT payload FROM m3_execution WHERE identity=?", (identity,)
            ).fetchone()
            if existing is not None:
                if existing != (payload,):
                    raise ProgressError("conflicting execution retry")
                return "duplicate"
            if self.db.execute("SELECT 1 FROM m3_resources WHERE identity=?", (identity,)).fetchone():
                raise ProgressError("discarded identity cannot be accepted")
            if self._state(identity) != "open" or not self.db.execute(
                "SELECT 1 FROM m3_eoe WHERE identity=?", (identity,)
            ).fetchone():
                raise ProgressError("execution is not eligible for acceptance")
            first_offset, = self.db.execute(
                "SELECT MIN(begin) FROM m3_positions WHERE identity=?", (identity,)
            ).fetchone()
            self.db.execute("INSERT INTO m3_execution VALUES (?,?,?)",
                            (identity, first_offset, payload))
            self._advance()
            return "accepted"

    def reject(self, identity):
        """Atomically reject a known identity and resolve its owned positions."""
        with self._transaction():
            state = self._state(identity)
            if state == "open":
                if self.db.execute('SELECT 1 FROM m3_resources WHERE identity=?', (identity,)).fetchone() and not self.db.execute(
                        'SELECT 1 FROM m3_eoe WHERE identity=?', (identity,)).fetchone():
                    raise ProgressError('resource discard requires EOE or timeout')
                self.db.execute(
                    "UPDATE m3_disposition SET state='rejected' WHERE identity=?", (identity,)
                )
            elif state != "rejected":
                raise ProgressError("identity cannot be rejected")
            self._advance()

    def recover(self):
        """Call before admitting new input after an interrupted collector."""
        with self._transaction():
            self.db.execute("""UPDATE m3_disposition SET state='interrupted'
                WHERE state='open' AND identity NOT IN (SELECT identity FROM m3_execution)""")
            self._advance()

    def _advance(self):
        scanned, frontier = self.positions()
        blocker, = self.db.execute(
            """SELECT MIN(p.begin) FROM m3_positions p
               JOIN m3_disposition d ON d.identity=p.identity
               WHERE p.begin>=? AND d.state='open'
                 AND NOT EXISTS (SELECT 1 FROM m3_execution e WHERE e.identity=d.identity)""", (frontier,),
        ).fetchone()
        self.db.execute("UPDATE m3_cursor SET frontier=?", (scanned if blocker is None else blocker,))

    def close(self):
        self.db.close()


def event_health(db):
    resources = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m3_resources'").fetchone()
    return {'timeouts': db.execute('SELECT COUNT(*) FROM m3_timeouts').fetchone()[0],
            'late_records': db.execute('SELECT COUNT(*) FROM m3_late_positions').fetchone()[0],
            'resource_incidents': db.execute('SELECT COUNT(*) FROM m3_resources').fetchone()[0] if resources else None,
            'discarding': db.execute("SELECT COUNT(*) FROM m3_resources r JOIN m3_disposition d USING(identity) WHERE d.state='open'").fetchone()[0] if resources else None}
