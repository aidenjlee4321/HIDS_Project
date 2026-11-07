"""Offline synthetic contract/storage tests; no native collection or network API."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import socket
import struct
import tempfile
import unittest
from unittest.mock import patch
import uuid

from engine.ingestion.m1_contract import Framer, Invalid, canonical, decode, timestamp, utc_now, validate_event
from engine.ingestion.m1_security import ordinary_user, peer_matches, private_directory, private_file
from engine.database.m1_store import DDL, RetrievalFailure, Store, get_event, profile

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "tests/fixtures/process/m1-exec-envelope.json").read_text())


class ContractTests(unittest.TestCase):
    def test_shared_vectors(self):
        for case in json.loads((ROOT / "tests/fixtures/process/m1-contract-cases.json").read_text()):
            with self.subTest(case=case["name"]):
                try:
                    validate_event(decode(case["input"].encode()))
                    result = "valid"
                except Invalid as exc:
                    result = exc.code
                self.assertEqual(result, case["expected"])

    def test_invalid_framing_json_and_strings(self):
        for raw in (b"", b"{}\r", b"{}\n", b"\xef\xbb\xbf{}", b'{"a":"\xff"}', b'{"a":"\\ud800"}'):
            with self.subTest(raw=raw), self.assertRaises(Invalid):
                decode(raw)

    def test_split_coalesced_and_delimiter_cap(self):
        data = canonical(BASE).encode()
        framer = Framer()
        frames = []
        for byte in data + b"\n" + data + b"\n":
            frames.extend(framer.feed(bytes([byte])))
        self.assertEqual(frames, [data, data])
        self.assertEqual(list(Framer().feed(data + b"\n" + data + b"\n")), [data, data])
        for cap in (512, 65536):
            framer = Framer(cap)
            self.assertEqual(list(framer.feed(b" " * cap)), [])
            self.assertEqual(list(framer.feed(b"\n")), [b" " * cap])
            list(framer.feed(b"x" * cap))
            with self.assertRaises(Invalid):
                list(framer.feed(b"x"))
            self.assertEqual(len(framer.buffer), cap)

    def test_calendar_and_unknown_fields(self):
        timestamp("0001-01-01T00:00:00.000000Z")
        timestamp("2000-02-29T00:00:00.000000Z")
        for section in ("source", "native", "timestamps"):
            event = copy.deepcopy(BASE)
            event[section]["extra"] = None
            with self.assertRaises(Invalid):
                validate_event(event)

    def test_peer_uid_gid_pid_policy_without_changing_identities(self):
        class Peer:
            def __init__(self, values):
                self.values = values
            def getsockopt(self, *_args):
                return struct.pack('3i', *self.values)
        uid, gid = os.getuid(), os.getgid()
        with patch('engine.ingestion.m1_security.sys.platform', 'linux'), patch.object(socket, 'SO_PEERCRED', 17, create=True):
            self.assertTrue(peer_matches(Peer((42, uid, gid)), 42))
            for values in ((43, uid, gid), (42, uid+1, gid), (42, uid, gid+1)):
                self.assertFalse(peer_matches(Peer(values), 42))


class StorageTests(unittest.TestCase):
    def setUp(self):
        os.umask(0o077)
        self.directory = Path(tempfile.mkdtemp(prefix="hids-m1-unit-", dir="/private/tmp" if os.path.isdir('/private/tmp') else '/tmp'))
        self.path = self.directory / "pilot ?#%é.sqlite"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()

    def put(self, event=None):
        return self.store.put(event or copy.deepcopy(BASE), utc_now())

    def test_round_trip_and_duplicate_preserve_times(self):
        self.assertEqual(self.put(), "stored")
        before = self.store.conn.execute("SELECT * FROM pilot_events").fetchone()
        self.assertEqual(self.put(), "duplicate")
        self.assertEqual(self.store.conn.execute("SELECT * FROM pilot_events").fetchone(), before)
        self.assertEqual(get_event(self.path, BASE["event_id"]), BASE)
        self.store.close()
        self.assertEqual(get_event(self.path, BASE["event_id"]), BASE)
        self.assertIsNone(get_event(self.path, str(uuid.uuid4())))

    def test_collision_and_unsupported_versions_preserve_row(self):
        self.put()
        original = self.store.conn.execute("SELECT * FROM pilot_events").fetchone()
        for key, value, code in (("native", {**BASE["native"], "pid": 5}, "id_conflict"),
                                 ("protocol_version", 2, "unsupported_version"),
                                 ("contract_version", "unsupported", "unsupported_version")):
            event = copy.deepcopy(BASE)
            event[key] = value
            with self.assertRaises(Invalid) as result:
                self.put(event)
            self.assertEqual(result.exception.code, code)
            self.assertEqual(self.store.conn.execute("SELECT * FROM pilot_events").fetchone(), original)

    def test_fail_before_commit_and_after_commit_uncertainty(self):
        for stage, count in (("before_insert", 0), ("before_commit", 0), ("after_commit", 1)):
            with self.subTest(stage=stage):
                event = copy.deepcopy(BASE)
                event["event_id"] = str(uuid.uuid4())
                def fault(at):
                    if at == stage:
                        raise sqlite3.OperationalError("injected")
                self.store.fault = fault
                with self.assertRaises(sqlite3.Error):
                    self.put(event)
                self.assertFalse(self.store.conn.in_transaction)
                found = get_event(self.path, event["event_id"])
                self.assertEqual(found is not None, bool(count))
                self.store.fault = lambda at: None
                self.assertEqual(self.put(event), "duplicate" if count else "stored")

    def test_clock_failure_rolls_back(self):
        self.store.clock = lambda: "invalid"
        with self.assertRaises(Invalid):
            self.put()
        self.assertIsNone(get_event(self.path, BASE["event_id"]))

    def test_capacity_and_duplicate_at_capacity(self):
        self.put()
        for _ in range(99):
            event = copy.deepcopy(BASE)
            event["event_id"] = str(uuid.uuid4())
            self.put(event)
        self.assertEqual(self.put(), "duplicate")
        event["event_id"] = str(uuid.uuid4())
        with self.assertRaises(Invalid) as result:
            self.put(event)
        self.assertEqual(result.exception.code, "capacity_exceeded")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM pilot_events").fetchone()[0], 100)

    def test_profiles_sidecars_readonly_and_reopen(self):
        self.put()
        for suffix in ("", "-wal", "-shm"):
            private_file(Path(str(self.path) + suffix))
        conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            profile(conn, reader=True)
            for name, value in (("synchronous", 2), ("busy_timeout", 1000), ("wal_autocheckpoint", 0), ("journal_size_limit", 1048576)):
                self.assertEqual(conn.execute("PRAGMA " + name).fetchone()[0], value)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM pilot_events")
        finally:
            conn.close()
        self.store.conn.execute("PRAGMA busy_timeout=7")
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.conn.execute("PRAGMA busy_timeout").fetchone()[0], 1000)
        self.assertEqual(self.store.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_retrieval_failure_does_not_undo_commit(self):
        self.put()
        with patch('engine.database.m1_store.profile', side_effect=RuntimeError('injected')):
            with self.assertRaises(RetrievalFailure):
                get_event(self.path, BASE["event_id"])
        self.assertEqual(get_event(self.path, BASE["event_id"]), BASE)
        self.store.conn.execute("UPDATE pilot_events SET envelope_json='{}'")
        with self.assertRaises(RetrievalFailure):
            get_event(self.path, BASE["event_id"])

    def test_duplicate_does_not_ack_invalid_stored_metadata(self):
        self.put()
        self.store.conn.execute("UPDATE pilot_events SET received_at='invalid'")
        with self.assertRaises(Invalid):
            self.put()
        self.assertFalse(self.store.conn.in_transaction)

    def test_startup_failure_and_unexpected_schema(self):
        self.store.close()
        with self.assertRaises(sqlite3.OperationalError):
            Store(self.path, fault=lambda stage: (_ for _ in ()).throw(sqlite3.OperationalError('injected')))
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA user_version=99")
        conn.close()
        with self.assertRaises(RuntimeError):
            Store(self.path)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA user_version=1")
        conn.execute("CREATE TABLE sqlitex_unexpected (value TEXT)")
        conn.commit()
        conn.close()
        with self.assertRaises(RuntimeError):
            Store(self.path)

    def test_busy_database_does_not_create_event(self):
        lock = sqlite3.connect(self.path, isolation_level=None)
        try:
            lock.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):
                self.put()
        finally:
            lock.execute('ROLLBACK')
            lock.close()
        self.assertIsNone(get_event(self.path, BASE['event_id']))

    def test_sqlite_full_is_bounded_and_transaction_rolls_back(self):
        pages = self.store.conn.execute('PRAGMA page_count').fetchone()[0]
        self.store.conn.execute('PRAGMA max_page_count='+str(pages))
        failed = False
        for _ in range(100):
            event = copy.deepcopy(BASE)
            event['event_id'] = str(uuid.uuid4())
            try:
                self.put(event)
            except sqlite3.OperationalError:
                failed = True
                self.assertFalse(self.store.conn.in_transaction)
                self.assertIsNone(get_event(self.path, event['event_id']))
                break
        self.assertTrue(failed)

    def test_filesystem_and_identity_rejection(self):
        private_directory(self.directory)
        link = self.directory / 'linked.sqlite'
        link.symlink_to(self.path)
        with self.assertRaises(PermissionError):
            Store(link)
        os.chmod(self.path, 0o644)
        with self.assertRaises(PermissionError):
            Store(self.path)
        os.chmod(self.path, 0o600)
        with patch('os.getuid', return_value=0), self.assertRaises(PermissionError):
            ordinary_user()


if __name__ == '__main__':
    unittest.main()
