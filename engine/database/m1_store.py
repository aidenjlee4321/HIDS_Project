"""Python-owned, disposable M1 SQLite model. Never writes real security data."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from engine.ingestion.m1_contract import Invalid, canonical, decode, timestamp, utc_now, uuid_valid, validate_event
from engine.ingestion.m1_security import private_directory, private_file

DDL = """CREATE TABLE pilot_events (
    event_id TEXT NOT NULL PRIMARY KEY,
    contract_version TEXT NOT NULL,
    source_adapter TEXT NOT NULL,
    source_mode TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    storage_attempt_at TEXT NOT NULL,
    CHECK (contract_version = 'm1.process-exec/0.1.0'),
    CHECK (source_adapter = 'linux.cn_proc'),
    CHECK (source_mode = 'sanitized_fixture')
)"""


class RetrievalFailure(RuntimeError):
    pass


def connect(path, reader=False):
    options = {"isolation_level": None, "timeout": 1}
    # Pin the wrapper mode explicitly where available (Python >= 3.12), rather
    # than depending on a future default. SQL BEGIN/COMMIT remain authoritative.
    if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        options["autocommit"] = sqlite3.LEGACY_TRANSACTION_CONTROL
    if reader:
        return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, **options)
    return sqlite3.connect(path, **options)


def profile(conn, reader=False, fresh=False):
    if sqlite3.sqlite_version_info < (3, 22, 0):
        raise RuntimeError("sqlite_version_unsupported")
    mode = conn.execute("PRAGMA main.journal_mode=WAL" if fresh else "PRAGMA main.journal_mode").fetchone()[0]
    if mode != "wal":
        raise RuntimeError("wal_required")
    for name, value in (("main.synchronous", 2), ("busy_timeout", 1000),
                        ("wal_autocheckpoint", 0 if reader else 1000),
                        ("main.journal_size_limit", 1048576)):
        conn.execute(f"PRAGMA {name}={value}")  # Internal constant allowlist, not user SQL.
        if conn.execute(f"PRAGMA {name}").fetchone()[0] != value:
            raise RuntimeError("connection_profile_failed")


def schema(conn):
    entries = conn.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
    if conn.execute("PRAGMA user_version").fetchone()[0] != 1 or entries != [("table", "pilot_events", DDL)]:
        raise RuntimeError("unexpected_pilot_schema")


def check_sidecars(path):
    for suffix in ("-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists() or p.is_symlink():
            private_file(p)


class Store:
    def __init__(self, path, clock=utc_now, fault=lambda stage: None, cancelled=lambda: False):
        self.path = Path(path)
        private_directory(self.path.parent)
        self.conn = None
        self.clock, self.fault, self.cancelled = clock, fault, cancelled
        fresh = not self.path.exists() and not self.path.is_symlink()
        if fresh:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        private_file(self.path, writable=True)
        check_sidecars(self.path)
        try:
            self.conn = connect(self.path)
            if not fresh:
                schema(self.conn)
            self.fault("startup")
            profile(self.conn, fresh=fresh)
            if fresh:
                self.conn.execute("BEGIN IMMEDIATE")
                self.conn.execute(DDL)
                self.conn.execute("PRAGMA user_version=1")
                self.conn.execute("COMMIT")
            schema(self.conn)
            check_sidecars(self.path)
        except BaseException:
            self.close()
            raise

    def put(self, event, received_at):
        validate_event(event)
        text = canonical(event)
        timestamp(received_at)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute("SELECT * FROM pilot_events WHERE event_id=?", (event["event_id"],)).fetchone()
            if row is not None:
                if row[4] != text:
                    raise Invalid("id_conflict")
                if row[:4] != (event["event_id"], event["contract_version"], event["source"]["adapter"], event["source"]["mode"]):
                    raise RuntimeError("stored_row_invalid")
                timestamp(row[5])
                timestamp(row[6])
                result = "duplicate"
            else:
                if self.conn.execute("SELECT count(*) FROM pilot_events").fetchone()[0] >= 100:
                    raise Invalid("capacity_exceeded")
                observed = self.clock()
                timestamp(observed)
                self.fault("before_insert")
                self.conn.execute("INSERT INTO pilot_events VALUES (?,?,?,?,?,?,?)",
                                  (event["event_id"], event["contract_version"], event["source"]["adapter"],
                                   event["source"]["mode"], text, received_at, observed))
                result = "stored"
            self.fault("before_commit")
            if self.cancelled():
                raise InterruptedError("shutdown_requested")
            self.conn.execute("COMMIT")
            self.fault("after_commit")  # Test seam: commit may have succeeded before an exception.
            check_sidecars(self.path)
            return result
        except BaseException:
            if self.conn.in_transaction:
                try:
                    self.conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None


def get_event(path, event_id):
    """Read-only retrieval; failure is never evidence of non-commit."""
    if not uuid_valid(event_id):
        raise RetrievalFailure("invalid_lookup_id")
    conn = None
    try:
        path = Path(path)
        private_directory(path.parent)
        private_file(path)
        check_sidecars(path)
        conn = connect(path, reader=True)
        profile(conn, reader=True)
        schema(conn)
        row = conn.execute("SELECT * FROM pilot_events WHERE event_id=?", (event_id,)).fetchone()
        if row is None:
            return None
        obj = validate_event(decode(row[4].encode("ascii")))
        if (row[:4] != (obj["event_id"], obj["contract_version"], obj["source"]["adapter"], obj["source"]["mode"])
                or obj["event_id"] != event_id or canonical(obj) != row[4]):
            raise ValueError("stored_content_mismatch")
        timestamp(row[5])
        timestamp(row[6])
        check_sidecars(path)
        return obj
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        raise RetrievalFailure("retrieval_failure") from exc
    finally:
        if conn is not None:
            conn.close()
