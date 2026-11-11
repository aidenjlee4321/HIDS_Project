import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from engine.ingestion import m3_health
from engine.ingestion.m3_progress import ProgressError
from engine.ingestion.m3_runtime import Runtime
from engine.ingestion.m2_contract import frame


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve()
        self.source = str(uuid.uuid4())
        self.runtime = self.open()
        self.addCleanup(lambda: self.runtime.close())
        self.activation = str(uuid.uuid4())
        self.current = self.runtime.activate(self.activation)
        self.generation = self.current['generation']
        self.now = 30_000_000_000

    def open(self):
        return Runtime(self.path, self.source, max_activations=4, max_pages=128, position_limit=32)

    def observation(self, **changes):
        value = dict(sample_ns=self.now, kernel=dict(state='observed', boot_id='00000000-0000-4000-8000-000000000001',
                    auditd_pid=42, lost=0, backlog=0, backlog_limit=64, enabled=1),
                    dispatcher=dict(state='observed', report_mtime_ns=1_000_000, age_ns=0,
                    active_plugins=1, queue_depth=0, queue_capacity=2000, overflow=False, suspended=False))
        for name, fields in changes.items():
            value[name].update(fields)
        return value

    def record(self, value):
        return m3_health.record(self.runtime.db, self.activation, self.generation, value, now_ns=self.now)

    def status(self):
        return m3_health.status(self.runtime.db, self.runtime.current(), now_ns=self.now)

    def test_observation_freshness_replay_and_historical_scope(self):
        first = self.observation()
        self.assertEqual(self.record(first), 'recorded')
        self.assertEqual(self.record(first), 'duplicate')
        self.assertEqual(self.status()['kernel'], 'sampled')
        self.assertEqual(self.status()['dispatcher'], 'sampled')
        self.now += m3_health.FRESH_NS+1
        status = self.status()
        self.assertEqual(status['freshness'], 'stale')
        self.assertEqual(status['kernel'], 'unknown')
        self.record(self.observation())
        self.assertTrue(self.status()['summary']['incidents']['sampling_gap'])
        self.runtime.revoke(self.activation)
        self.runtime.close()
        self.runtime = self.open()
        status = self.status()
        self.assertEqual(status['freshness'], 'historical')
        self.assertEqual(status['kernel'], 'unknown')
        self.assertTrue(status['summary']['incidents']['sampling_gap'])

    def test_historical_age_is_unknown_after_a_monotonic_clock_epoch_change(self):
        self.record(self.observation())
        self.runtime.revoke(self.activation)
        self.now = 1
        status = self.status()
        self.assertEqual(status['freshness'], 'historical')
        self.assertIsNone(status['age_ns'])
        self.assertEqual(status['kernel'], 'unknown')
        m3_health.validate_status(status)

    def test_historical_age_is_unknown_when_clock_epochs_can_overlap(self):
        self.record(self.observation())
        self.runtime.revoke(self.activation)
        # A later boot may have a larger uptime than the saved sample. Positive
        # subtraction alone cannot establish that monotonic epochs match.
        self.now += 100
        status = self.status()
        self.assertEqual(status['freshness'], 'historical')
        self.assertIsNone(status['age_ns'])
        self.assertEqual(status['kernel'], 'unknown')
        m3_health.validate_status(status)

    def test_counter_changes_are_sticky_and_never_attributed_to_hids_counts(self):
        self.record(self.observation(kernel={'lost': 7}))
        self.assertTrue(self.status()['summary']['preexisting_kernel_loss'])
        self.assertFalse(self.status()['summary']['incidents']['kernel_loss_increased'])
        self.now += 1
        self.record(self.observation(kernel={'lost': 10}, dispatcher={'overflow': True}))
        self.now += 1
        self.record(self.observation(kernel={'lost': 0, 'auditd_pid': 43}))
        self.now += 1
        self.record(self.observation(kernel={'boot_id': '00000000-0000-4000-8000-000000000002'}))
        incidents = self.status()['summary']['incidents']
        for key in ('kernel_loss_increased', 'kernel_counter_reset', 'auditd_changed', 'boot_changed', 'dispatcher_overflow'):
            self.assertTrue(incidents[key])
        self.assertEqual(self.status()['summary']['baseline']['lost'], 7)
        self.assertEqual(self.runtime.db.execute('SELECT COUNT(*) FROM m3_health').fetchone(), (1,))

    def test_inactive_stale_and_missing_dispatcher_do_not_invent_loss(self):
        self.record(self.observation(dispatcher={'active_plugins': 0, 'queue_capacity': 0, 'suspended': True}))
        self.assertEqual(self.status()['dispatcher'], 'inactive')
        self.assertFalse(any(self.status()['summary']['incidents'].values()))
        self.now += 1
        self.record(self.observation(dispatcher={'state': 'stale', 'age_ns': m3_health.FRESH_NS+1, 'overflow': True}))
        self.assertEqual(self.status()['dispatcher'], 'unknown')
        self.assertFalse(self.status()['summary']['incidents']['dispatcher_overflow'])
        self.now += 1
        value = self.observation()
        value['dispatcher'] = {'state': 'missing'}
        value['kernel'] = {'state': 'timeout'}
        self.record(value)
        self.assertEqual(self.status()['kernel'], 'unknown')
        self.assertEqual(self.status()['dispatcher'], 'unknown')
        self.now += 1
        self.record(self.observation())
        self.assertEqual(self.status()['summary']['unavailable_seen'], {'kernel': True, 'dispatcher': True})
        self.assertEqual(self.status()['kernel'], 'sampled')
        m3_health.validate_status(self.status())

    def test_status_contract_rejects_false_freshness_and_missing_evidence(self):
        self.record(self.observation())
        status = self.status()
        m3_health.validate_status(status)
        bad = copy.deepcopy(status)
        bad['freshness'] = 'historical'
        with self.assertRaises(ProgressError):
            m3_health.validate_status(bad)
        bad = copy.deepcopy(status)
        bad['observation']['kernel'] = {'state': 'timeout'}
        with self.assertRaises(ProgressError):
            m3_health.validate_status(bad)
        bad = copy.deepcopy(status)
        bad['observation']['dispatcher']['age_ns'] = m3_health.FRESH_NS
        bad['age_ns'] = 1
        with self.assertRaises(ProgressError):
            m3_health.validate_status(bad)

    def test_invalid_metadata_conflicts_and_receipt_window_are_rejected(self):
        first = self.observation()
        self.record(first)
        bad = copy.deepcopy(first)
        bad['kernel']['lost'] = 1
        with self.assertRaises(ProgressError):
            self.record(bad)
        for field, value in (('lost', True), ('boot_id', 'invented'), ('enabled', 3), ('backlog', -1)):
            bad = self.observation(kernel={field: value})
            with self.assertRaises(ProgressError):
                self.record(bad)
        bad = self.observation(dispatcher={'queue_depth': 2001})
        with self.assertRaises(ProgressError):
            self.record(bad)
        bad = self.observation()
        bad['raw_payload'] = 'forbidden'
        with self.assertRaises(ProgressError):
            self.record(bad)
        self.now += 4_000_000_000
        with self.assertRaises(ProgressError):
            self.record(first)

    def test_health_transaction_rolls_back_without_changing_collection(self):
        self.record(self.observation())
        self.now += 1
        self.runtime.db.execute("""CREATE TRIGGER reject_health BEFORE INSERT ON m3_health
            BEGIN SELECT RAISE(ABORT, 'injected'); END""")
        with self.assertRaises(sqlite3.Error):
            self.record(self.observation(kernel={'lost': 5}))
        self.assertEqual(self.status()['observation']['kernel']['lost'], 0)
        self.assertEqual(self.runtime.current()['state'], 'ready')

    def test_v3_control_migration_preserves_interval_and_event_history(self):
        self.runtime.revoke(self.activation)
        self.runtime.close()
        database = sqlite3.connect(self.path / 'control.sqlite', isolation_level=None)
        database.execute('DROP TABLE m3_health')
        database.execute('PRAGMA user_version=3')
        database.close()
        self.runtime = self.open()
        self.assertEqual(self.runtime.current()['activation'], self.activation)
        self.assertEqual(self.runtime.current()['state'], 'revoked')
        self.assertEqual(self.runtime.db.execute('PRAGMA user_version').fetchone(), (4,))
        self.assertTrue((self.path / f'{self.activation}.sqlite').exists())

    def test_status_frame_fits_existing_bounded_control_protocol(self):
        self.now += 1
        m3_health.record(self.runtime.db, self.activation, self.generation,
                         self.observation(kernel={'lost': 2**32-1, 'backlog': 2**32-1}), now_ns=self.now)
        response = dict(version=3, result='status', failure=None, reader_connected=True, **self.runtime.status())
        self.assertLessEqual(len(frame(response, 2048)), 2048)
