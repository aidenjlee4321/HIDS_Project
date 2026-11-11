import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from engine.ingestion.m3_progress import Progress, ProgressError


class ProgressTests(unittest.TestCase):
    A = "1.001:1"
    B = "1.001:2"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "progress.sqlite"
        self.ledger = self.open_ledger()
        self.addCleanup(lambda: self.ledger.close())

    def open_ledger(self):
        return Progress(self.path, "activation", "generation", 100)

    def test_interleaving_and_idempotent_rejection(self):
        self.assertEqual(self.ledger.register(self.A, 100, 110), "admit")
        self.ledger.register(self.B, 110, 120)
        self.ledger.register(self.A, 120, 130)
        self.ledger.reject(self.A)
        self.assertEqual(self.ledger.positions(), (130, 110))
        self.ledger.reject(self.A)
        self.assertEqual(self.ledger.register(self.A, 120, 130), "replay")
        self.assertEqual(self.ledger.register(self.A, 130, 140), 'suppressed')
        self.ledger.reject(self.B)
        self.assertEqual(self.ledger.positions(), (140, 140))

    def timeout_evidence(self, **changes):
        evidence = dict(policy=1, reason='lifetime', first_active_ms=0, last_active_ms=20,
                        observed_active_ms=100, observed_monotonic_ms=150, paused_ms=50,
                        inactivity_limit_ms=50, lifetime_limit_ms=100)
        evidence.update(changes)
        return evidence

    def test_timeout_preserves_independent_execution_and_suppresses_late_eoe(self):
        self.ledger.register(self.A, 100, 110)
        self.ledger.register(self.B, 110, 120)
        self.ledger.register(self.B, 120, 130, eoe=True)
        self.ledger.accept(self.B, self.execution())
        self.assertEqual(self.ledger.positions(), (130, 100))
        evidence = self.timeout_evidence()
        self.assertEqual(self.ledger.timeout(self.A, evidence), 'timed_out')
        self.assertEqual(self.ledger.timeout(self.A, evidence), 'timed_out')
        self.assertEqual(self.ledger.positions(), (130, 130))
        self.assertEqual(self.ledger.register(self.A, 130, 140, eoe=True), 'suppressed')
        self.assertEqual(self.ledger.register(self.A, 130, 140, eoe=True), 'replay')
        with self.assertRaises(ProgressError):
            self.ledger.register(self.A, 130, 140, eoe=False)
        with self.assertRaises(ProgressError):
            self.ledger.accept(self.A, self.execution())
        self.ledger.close()
        self.ledger = self.open_ledger()
        self.ledger.recover()
        self.assertEqual(self.ledger.event_health(), {'timeouts': 1, 'late_records': 1, 'resource_incidents': 0, 'discarding': 0, 'rejected_groups': 1, 'rejection_details': 1, 'observed_executions': 0})
        self.assertEqual(self.ledger.positions(), (140, 140))
        self.assertEqual(self.ledger.db.execute('SELECT identity FROM m3_execution').fetchall(), [(self.B,)])
        with self.assertRaises(ProgressError):
            self.ledger.timeout(self.A, self.timeout_evidence(observed_active_ms=101, paused_ms=49))

    def test_timeout_validation_and_atomic_rollback(self):
        self.ledger.register(self.A, 100, 110)
        for changes in ({'policy': True}, {'reason': 'invented'}, {'paused_ms': 0},
                        {'observed_active_ms': 99, 'paused_ms': 51}, {'first_active_ms': True},
                        {'extra': 'payload'}):
            with self.assertRaises(ProgressError):
                self.ledger.timeout(self.A, self.timeout_evidence(**changes))
        self.ledger.db.execute("""CREATE TRIGGER fail_timeout BEFORE UPDATE OF frontier ON m3_cursor
            BEGIN SELECT RAISE(ABORT, 'injected'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.timeout(self.A, self.timeout_evidence())
        self.assertEqual(self.ledger.event_health()['timeouts'], 0)
        self.assertEqual(self.ledger._state(self.A), 'open')
        self.ledger.db.execute('DROP TRIGGER fail_timeout')
        self.ledger.register(self.A, 110, 120, eoe=True)
        with self.assertRaises(ProgressError):
            self.ledger.timeout(self.A, self.timeout_evidence())

    def test_recovery_suppresses_interrupted_identity(self):
        self.ledger.register(self.A, 100, 110)
        self.ledger.close()
        self.ledger = self.open_ledger()
        self.assertEqual(self.ledger.positions(), (110, 100))
        self.ledger.recover()
        self.assertEqual(self.ledger.register(self.A, 100, 110), "replay")
        self.assertEqual(self.ledger.register(self.A, 110, 120), "suppressed")
        self.assertEqual(self.ledger.register(self.B, 120, 130), "admit")
        self.assertEqual(self.ledger.positions(), (130, 120))

    def test_interrupted_replay_preserves_exact_eoe_classification(self):
        self.ledger.register(self.A, 100, 110)
        self.ledger.register(self.B, 110, 120)
        self.ledger.register(self.B, 120, 130, eoe=True)
        self.ledger.accept(self.B, self.execution())
        self.ledger.register(self.A, 130, 140, eoe=True)
        self.ledger.recover()
        for begin, end, eoe in ((100, 110, False), (130, 140, True)):
            self.assertEqual(self.ledger.register(self.A, begin, end, eoe=eoe), 'replay')
            with self.subTest(begin=begin), self.assertRaisesRegex(ProgressError, 'conflicting position replay'):
                self.ledger.register(self.A, begin, end, eoe=not eoe)
        self.assertEqual(self.ledger.positions(), (140, 140))
        self.assertEqual(self.ledger._state(self.A), 'interrupted')
        self.assertEqual(self.ledger.db.execute('SELECT identity FROM m3_execution').fetchall(), [(self.B,)])
        self.assertEqual(self.ledger.event_health()['late_records'], 0)

    def test_finalization_rolls_back_if_frontier_write_fails(self):
        self.ledger.register(self.A, 100, 110)
        self.ledger.db.execute("""CREATE TRIGGER fail_frontier
            BEFORE UPDATE OF frontier ON m3_cursor
            BEGIN SELECT RAISE(ABORT, 'fault injection'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.reject(self.A)
        self.assertEqual(self.ledger.positions(), (110, 100))
        self.ledger.db.execute("DROP TRIGGER fail_frontier")
        self.ledger.register(self.A, 110, 120)
        self.ledger.reject(self.A)
        self.assertEqual(self.ledger.positions(), (120, 120))

    def test_failed_registration_leaves_no_suppression_on_restart(self):
        self.ledger.db.execute("""CREATE TRIGGER fail_scan
            BEFORE UPDATE OF scanned ON m3_cursor
            BEGIN SELECT RAISE(ABORT, 'fault injection'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.register(self.A, 100, 110)
        self.assertEqual(self.ledger.positions(), (100, 100))
        self.ledger.db.execute("DROP TRIGGER fail_scan")
        self.ledger.close()
        self.ledger = self.open_ledger()
        self.ledger.recover()
        self.assertEqual(self.ledger.register(self.A, 100, 110), "admit")

    def execution(self, **changes):
        event = dict(syscall=221, pid=42, ppid=1, uid=1000, euid=1000,
                     suid=1000, fsuid=1000, auid=None, session=7, path_count=1,
                     success=True, cwd_present=True, proctitle_present=True,
                     result=0, exe_base64="L2Jpbi94", comm_base64="eA==")
        event.update(changes)
        return event

    def test_accepted_retry_after_lost_ack_and_restart(self):
        self.ledger.register(self.A, 100, 110)
        self.ledger.register(self.B, 110, 120)
        self.ledger.register(self.A, 120, 130, eoe=True)
        self.assertEqual(self.ledger.accept(self.A, self.execution()), "accepted")
        self.assertEqual(self.ledger.positions(), (130, 110))
        self.ledger.close()
        self.ledger = self.open_ledger()
        self.ledger.recover()
        self.assertEqual(self.ledger.positions(), (130, 130))
        self.assertEqual(self.ledger.accept(self.A, self.execution()), "duplicate")
        with self.assertRaises(ProgressError):
            self.ledger.accept(self.A, self.execution(pid=43))
        with self.assertRaises(ProgressError):
            self.ledger.reject(self.A)
        self.assertEqual(self.ledger.db.execute(
            "SELECT first_offset FROM m3_execution"
        ).fetchall(), [(100,)])

    def test_process_exit_before_and_after_commit(self):
        script = """
import json
import os
import sys
from engine.ingestion.m3_progress import Progress

ledger = Progress(sys.argv[1], "activation", "generation", 100)
ledger.register("1.001:1", 100, 110)
ledger.register("1.001:1", 110, 120, eoe=True)
if sys.argv[3] == "committed":
    ledger.accept("1.001:1", json.loads(sys.argv[2]))
os._exit(19)
"""
        for stage in ("registered", "committed"):
            with self.subTest(stage=stage):
                path = self.path.with_name(stage + ".sqlite")
                completed = subprocess.run(
                    [sys.executable, "-B", "-c", script, str(path),
                     json.dumps(self.execution()), stage],
                    timeout=10, check=False,
                )
                self.assertEqual(completed.returncode, 19)
                ledger = Progress(path, "activation", "generation", 100)
                try:
                    ledger.recover()
                    self.assertEqual(ledger.positions(), (120, 120))
                    if stage == "committed":
                        self.assertEqual(ledger.accept(self.A, self.execution()), "duplicate")
                    else:
                        with self.assertRaises(ProgressError):
                            ledger.accept(self.A, self.execution())
                finally:
                    ledger.close()

    def test_accepted_payload_and_frontier_rollback_together(self):
        self.ledger.register(self.A, 100, 110)
        self.ledger.register(self.A, 110, 120, eoe=True)
        self.ledger.db.execute("""CREATE TRIGGER fail_accept
            BEFORE UPDATE OF frontier ON m3_cursor
            BEGIN SELECT RAISE(ABORT, 'fault injection'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.accept(self.A, self.execution())
        self.assertEqual(self.ledger.positions(), (120, 100))
        self.assertIsNone(self.ledger.db.execute("SELECT 1 FROM m3_execution").fetchone())
        self.ledger.db.execute("DROP TRIGGER fail_accept")
        self.ledger.recover()
        with self.assertRaises(ProgressError):
            self.ledger.accept(self.A, self.execution())

    def test_acceptance_requires_eoe_and_closed_payload(self):
        self.ledger.register(self.A, 100, 110)
        with self.assertRaises(ProgressError):
            self.ledger.accept(self.A, self.execution())
        self.ledger.register(self.A, 110, 120, eoe=True)
        with self.assertRaises(ProgressError):
            self.ledger.register(self.A, 120, 130)
        for invalid in (self.execution(argv=["private"]), self.execution(comm_base64="AA=="),
                        self.execution(comm_base64="eB=="), self.execution(pid=True),
                        self.execution(success=False)):
            with self.assertRaises(ProgressError):
                self.ledger.accept(self.A, invalid)
        self.assertEqual(self.ledger.positions(), (120, 100))
        self.assertEqual(self.ledger.accept(self.A, self.execution()), "accepted")

    def test_scope_and_scan_conflicts_fail_closed(self):
        with self.assertRaises(ProgressError):
            Progress(self.path, "other", "generation", 100)
        with self.assertRaises(ProgressError):
            self.ledger.register(self.A, 101, 110)
        self.ledger.register(self.A, 100, 110)
        with self.assertRaises(ProgressError):
            self.ledger.register(self.B, 100, 110)
        self.assertEqual(self.ledger.positions(), (110, 100))


if __name__ == "__main__":
    unittest.main()
