"""Design evidence only: synthetic M3 commits and candidate M4 sweep cursors.

This test harness is NOT a production source adapter or a supported live handoff.
It exercises the proposed ordering against the actual M3 progress ledger.
"""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from engine.detection.m4_pilot import load_json
from engine.ingestion.m3_event import ARCH, PROFILE
from engine.ingestion.m3_progress import Progress

ROOT = Path(__file__).resolve().parents[2]


class Sweep:
    """Candidate bookkeeping in the consumer only; no M3 writes/rowid cursor."""
    def __init__(self, settled=0):
        self.settled = settled
        self.target = None
        self.after = settled - 1
        self.received = set()

    def page(self, db, limit=1, *, commit_destination=True):
        db.execute('BEGIN')
        try:
            frontier = db.execute('SELECT frontier FROM m3_cursor WHERE singleton=1').fetchone()[0]
            target = frontier if self.target is None else self.target
            rows = db.execute('''SELECT e.first_offset,e.identity,e.payload,m.format,
                m.arch,m.collector_profile,m.first_observed_unix_ns,m.received_at,m.persistence_started_at
                FROM m3_execution e LEFT JOIN m3_event_metadata m USING(identity)
                WHERE e.first_offset>=? AND e.first_offset>? ORDER BY e.first_offset LIMIT ?''',
                (self.settled, self.after, limit)).fetchall()
        finally:
            db.execute('ROLLBACK')
        if not commit_destination:
            return rows  # Destination failure: neither records nor cursor advance.
        # A real adapter must persist these together in its destination transaction.
        self.received.update(row[1] for row in rows)
        if rows:
            self.target, self.after = target, rows[-1][0]
        else:
            self.settled = target  # Target was already final at sweep start.
            self.target, self.after = None, target - 1
        return rows


class HandoffDesignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hids-m4-handoff-design.')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'source.sqlite'
        self.path.touch(mode=0o600)
        self.writer = Progress(self.path, 'activation', 'generation', 0)
        self.addCleanup(self.writer.close)
        self.reader = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, isolation_level=None)
        self.addCleanup(self.reader.close)
        self.execution = load_json(ROOT / 'tests/fixtures/m4/execution.json')['execution']
        self.observation = dict(version=1, arch=ARCH, profile=PROFILE, first_observed_unix_ns=123)

    def register(self, identity, begin, end):
        self.writer.register(identity, begin, end, eoe=True)

    def accept(self, identity):
        self.writer.accept(identity, self.execution, observation=self.observation)

    def drain(self, sweep):
        for _ in range(20):
            if not sweep.page(self.reader):
                return
        self.fail('bounded fixture sweep did not finish')

    def test_simple_max_offset_cursor_would_miss_late_A(self):
        self.register('1.001:1', 0, 10); self.register('1.001:2', 10, 20)
        self.accept('1.001:2')
        last = self.reader.execute('SELECT MAX(first_offset) FROM m3_execution').fetchone()[0]
        self.accept('1.001:1')
        self.assertEqual(self.reader.execute('SELECT identity FROM m3_execution WHERE first_offset>?', (last,)).fetchall(), [])
        self.assertEqual(self.reader.execute('SELECT count(*) FROM m3_execution').fetchone()[0], 2)

    def test_sweep_delivers_B_early_and_later_A_without_loss(self):
        self.register('1.001:1', 0, 10); self.register('1.001:2', 10, 20)
        self.accept('1.001:2')
        sweep = Sweep()
        self.assertEqual(sweep.page(self.reader)[0][1], '1.001:2')
        self.assertEqual(sweep.target, 0)
        self.accept('1.001:1')  # Appears behind this sweep's scan marker.
        self.assertEqual(sweep.page(self.reader), [])
        self.assertEqual(sweep.settled, 0)  # Must not jump to the NEW frontier 20.
        self.drain(sweep)
        self.assertEqual(sweep.received, {'1.001:1', '1.001:2'})
        self.assertEqual(sweep.settled, 20)

    def test_pagination_does_not_starve_later_B_events(self):
        for i in range(4): self.register(f'1.001:{i+1}', i*10, (i+1)*10)
        for i in (2, 3, 4): self.accept(f'1.001:{i}')
        sweep = Sweep()
        self.drain(sweep)
        self.assertEqual(sweep.received, {'1.001:2', '1.001:3', '1.001:4'})
        self.assertEqual(sweep.settled, 0)
        self.accept('1.001:1'); self.drain(sweep)
        self.assertEqual(len(sweep.received), 4)
        self.assertEqual(sweep.settled, 40)

    def test_destination_failure_does_not_advance_scan(self):
        self.register('1.001:1', 0, 10); self.accept('1.001:1')
        sweep = Sweep()
        failed = sweep.page(self.reader, commit_destination=False)
        self.assertEqual((sweep.settled, sweep.target, sweep.after, sweep.received), (0, None, -1, set()))
        self.assertEqual(sweep.page(self.reader), failed)
        self.drain(sweep)
        self.assertEqual(sweep.received, {'1.001:1'})

    def test_rollback_uncommitted_execution_is_invisible(self):
        self.register('1.001:1', 0, 10)
        self.writer.db.execute('BEGIN IMMEDIATE')
        self.writer.db.execute('INSERT INTO m3_execution VALUES (?,?,?)', ('1.001:1', 0, json.dumps(self.execution)))
        sweep = Sweep()
        self.assertEqual(sweep.page(self.reader), [])
        self.writer.db.execute('ROLLBACK')
        self.assertEqual(sweep.received, set())
        self.accept('1.001:1'); self.drain(sweep)
        self.assertEqual(sweep.received, {'1.001:1'})

    def test_recovery_without_accepted_A_and_metadata_retained(self):
        self.register('1.001:1', 0, 10); self.register('1.001:2', 10, 20)
        self.accept('1.001:2'); self.writer.recover()
        sweep = Sweep(); rows = sweep.page(self.reader)
        self.assertEqual(rows[0][1], '1.001:2')
        self.assertEqual(rows[0][3:7], (1, ARCH, PROFILE, 123))
        self.assertTrue(rows[0][7] and rows[0][8])
        self.drain(sweep)
        self.assertEqual(sweep.received, {'1.001:2'})
        self.assertEqual(sweep.settled, 20)
        self.assertEqual(self.reader.execute("SELECT state FROM m3_disposition WHERE identity='1.001:1'").fetchone()[0], 'interrupted')

    def test_read_connection_cannot_update_M3(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.reader.execute('UPDATE m3_cursor SET frontier=1')


if __name__ == '__main__':
    unittest.main()
