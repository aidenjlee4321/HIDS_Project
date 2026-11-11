import json
import contextlib
import io
import os
from pathlib import Path
import select
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid

from engine.ingestion.m3_progress import Progress, ProgressError
from engine.ingestion.m3_runtime import Runtime
from engine.ingestion.m3_service import Service
from engine.ingestion import m3_control

SOURCE = '7d9b6873-c6a0-4e9a-88ab-5ec2c04dc592'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.runtime = self.open_runtime()
        self.addCleanup(lambda: self.runtime.close())

    def open_runtime(self, **options):
        return Runtime(self.directory, SOURCE, max_activations=options.get('max_activations', 4),
                       max_pages=128, position_limit=32)

    def test_fresh_authorization_and_single_reader(self):
        self.assertIsNone(self.runtime.current())
        with self.assertRaises(ProgressError):
            self.runtime.claim()
        activation = str(uuid.uuid4())
        first = self.runtime.activate(activation)
        self.assertEqual(first, self.runtime.activate(activation))
        scope = self.runtime.claim()
        self.assertEqual(scope['activation'], activation)
        with self.assertRaises(ProgressError):
            self.runtime.claim()
        self.runtime.revoke(activation)
        self.runtime.revoke(activation)
        self.assertEqual(self.runtime.current()['state'], 'revoked')
        with self.assertRaises(ProgressError):
            self.runtime.activate(activation)

    def test_restart_interrupts_before_new_interval_can_begin(self):
        activation = str(uuid.uuid4())
        first = self.runtime.activate(activation)
        self.runtime.claim()
        self.runtime.progress.register('1.001:1', 0, 10)
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.assertEqual(self.runtime.current()['code'], 'backend_restart')
        self.assertTrue(self.runtime.status()['possible_gap'])
        with self.assertRaises(ProgressError):
            self.runtime.claim()
        old = Progress(self.directory / f'{activation}.sqlite', activation, first['generation'], 0)
        try:
            self.assertEqual(old.positions(), (10, 10))
            self.assertEqual(old.register('1.001:1', 10, 20), 'suppressed')
        finally:
            old.close()
        second = self.runtime.activate(str(uuid.uuid4()))
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertNotEqual(first['lease'], second['lease'])
        self.assertEqual(self.runtime.progress.positions(), (0, 0))

    def test_timeout_evidence_survives_revocation_and_backend_reopen(self):
        activation = str(uuid.uuid4())
        self.runtime.activate(activation)
        self.runtime.claim()
        self.runtime.progress.start_stream()
        self.runtime.progress.register('1.001:1', 0, 10)
        self.runtime.progress.timeout('1.001:1', dict(
            policy=1, reason='lifetime', first_active_ms=0, last_active_ms=0,
            observed_active_ms=100, observed_monotonic_ms=150, paused_ms=50,
            inactivity_limit_ms=100, lifetime_limit_ms=100))
        self.assertTrue(self.runtime.status()['possible_gap'])
        self.runtime.revoke(activation)
        self.runtime.close()
        self.runtime = self.open_runtime()
        status = self.runtime.status()
        self.assertEqual(status['event_health'], {'timeouts': 1, 'late_records': 0, 'resource_incidents': 0, 'discarding': 0})
        self.assertTrue(status['possible_gap'])
        self.assertFalse(status['source_ready'])
        self.assertEqual(status['interval']['state'], 'revoked')

    def test_parser_failure_interrupts_admission_and_retains_independent_execution(self):
        import test_m3_progress as fixtures
        activation = str(uuid.uuid4())
        interval = self.runtime.activate(activation)
        self.runtime.claim()
        self.runtime.progress.register('1.001:1', 0, 10)
        self.runtime.progress.register('1.001:2', 10, 20)
        self.runtime.progress.register('1.001:2', 20, 30, eoe=True)
        self.runtime.progress.accept('1.001:2', fixtures.ProgressTests.execution(self))
        self.runtime.interrupt('collector_parser_failure')
        status = self.runtime.status()
        self.assertEqual(status['interval']['code'], 'collector_parser_failure')
        self.assertTrue(status['possible_gap'])
        self.assertFalse(status['source_ready'])
        old = Progress(self.directory / f'{activation}.sqlite', activation, interval['generation'], 0)
        try:
            self.assertEqual(old.positions(), (30, 30))
            self.assertEqual(old._state('1.001:1'), 'interrupted')
            self.assertEqual(old._state('1.001:2'), 'accepted')
            self.assertEqual(old.register('1.001:1', 30, 40, eoe=True), 'suppressed')
        finally:
            old.close()

    def test_concurrent_writer_and_missing_ledger_fail_closed(self):
        with self.assertRaises(BlockingIOError):
            self.open_runtime()
        activation = str(uuid.uuid4())
        self.runtime.activate(activation)
        self.runtime.close()
        (self.directory / f'{activation}.sqlite').unlink()
        with self.assertRaisesRegex(ProgressError, 'missing activation'):
            self.open_runtime()

    def test_control_commit_failure_keeps_orphan_bounded(self):
        self.runtime.db.execute("""CREATE TRIGGER fail_activation BEFORE INSERT ON m3_intervals
            BEGIN SELECT RAISE(ABORT, 'injected'); END""")
        activation = str(uuid.uuid4())
        with self.assertRaises(sqlite3.IntegrityError):
            self.runtime.activate(activation)
        self.assertIsNone(self.runtime.current())
        self.assertIsNone(self.runtime.progress)
        self.runtime.db.execute('DROP TRIGGER fail_activation')
        with self.assertRaisesRegex(ProgressError, 'uncommitted'):
            self.runtime.activate(activation)
        self.runtime.close()
        self.runtime = self.open_runtime(max_activations=1)
        with self.assertRaisesRegex(ProgressError, 'capacity'):
            self.runtime.activate(str(uuid.uuid4()))
        self.assertTrue((self.directory / f'{activation}.sqlite').exists())

    def test_actual_backend_exit_releases_lock_and_interrupts(self):
        self.runtime.close()
        activation = str(uuid.uuid4())
        script = """
import os
import signal
import sys
from engine.ingestion.m3_runtime import Runtime
runtime = Runtime(sys.argv[1], sys.argv[2], max_activations=4, max_pages=128, position_limit=32)
runtime.activate(sys.argv[3])
runtime.claim()
runtime.progress.register('1.001:1', 0, 10)
os.kill(os.getpid(), signal.SIGKILL)
"""
        child = subprocess.run([sys.executable, '-B', '-c', script,
                                str(self.directory), SOURCE, activation], timeout=5)
        self.assertEqual(child.returncode, -9)
        self.runtime = self.open_runtime()
        self.assertEqual(self.runtime.current()['code'], 'backend_restart')
        self.runtime.revoke(activation)
        self.assertEqual(self.runtime.current()['code'], 'backend_restart')
        self.assertTrue(self.runtime.status()['possible_gap'])

    def test_failed_reconciliation_records_gap_without_resolving_positions(self):
        self.runtime.activate(str(uuid.uuid4()))
        self.runtime.claim()
        self.runtime.progress.register('1.001:1', 0, 10)
        self.runtime.progress.db.execute("""CREATE TRIGGER fail_recovery
            BEFORE UPDATE OF frontier ON m3_cursor BEGIN SELECT RAISE(ABORT, 'injected'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.runtime.interrupt('stream_disconnected')
        self.assertEqual(self.runtime.current()['code'], 'storage_failure')
        self.assertTrue(self.runtime.status()['possible_gap'])
        self.assertEqual(self.runtime.progress.positions(), (10, 0))
        with self.assertRaisesRegex(ProgressError, 'explicit restart'):
            self.runtime.activate(str(uuid.uuid4()))


class FixturePeer:
    def check(self, connection):
        return os.getpid()


class FixtureListener:
    """Private socket pairs supply readiness without a filesystem listener."""
    def __init__(self):
        self.notice, self.writer = socket.socketpair()
        self.pending = []

    def fileno(self):
        return self.notice.fileno()

    def setblocking(self, value):
        self.notice.setblocking(value)

    def connect(self):
        server, client = socket.socketpair()
        self.pending.append(server)
        self.writer.sendall(b'x')
        return client

    def accept(self):
        self.notice.recv(1)
        return self.pending.pop(0), None

    def close(self):
        for server in self.pending:
            server.close()
        self.notice.close()
        self.writer.close()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name).resolve()
        self.runtime = Runtime(directory, SOURCE, max_activations=4, max_pages=128, position_limit=32)
        self.addCleanup(self.runtime.close)
        self.data = self.listener()
        self.control = self.listener()
        self.now = 0
        self.health_listener = self.listener()
        self.service = Service(self.runtime, self.data, self.control, FixturePeer(),
                               control_peer=FixturePeer(), health_listener=self.health_listener,
                               health_peer=FixturePeer(), clock=lambda: self.now)
        self.addCleanup(self.service.close)
        self.activation = str(uuid.uuid4())

    def listener(self):
        listener = FixtureListener()
        self.addCleanup(listener.close)
        return listener

    def connect(self, listener):
        client = listener.connect()
        self.addCleanup(client.close)
        client.settimeout(1)
        self.service.run_once()
        return client

    def receive(self, client):
        for _ in range(10):
            self.service.run_once()
            if select.select([client], [], [], 0)[0]:
                raw = client.recv(4096)
                return json.loads(raw) if raw else None
        self.fail('no bounded service response')

    def command(self, name, **fields):
        client = self.connect(self.control)
        client.sendall(json.dumps(dict(version=3, command=name, **fields)).encode() + b'\n')
        return self.receive(client)

    def activate(self):
        result = self.command('activate', source=SOURCE, activation=self.activation)
        self.assertEqual(result['result'], 'activated')
        return self.command('lease')['scope']

    def health_command(self, name, **fields):
        client = self.connect(self.health_listener)
        client.sendall(json.dumps(dict(version=3, command=name, **fields)).encode()+b'\n')
        return self.receive(client)

    def test_health_endpoint_cannot_activate_and_stale_reports_cannot_cross_intervals(self):
        self.assertEqual(self.health_command('scope')['result'], 'inactive')
        self.assertEqual(self.health_command('activate', source=SOURCE, activation=self.activation)['result'], 'rejected')
        self.assertIsNone(self.runtime.current())
        scope = self.activate()
        expected = {'version': 3, 'result': 'scope', 'activation': scope['activation'], 'generation': scope['generation']}
        self.assertEqual(self.health_command('scope'), expected)
        observation = dict(sample_ns=time.monotonic_ns(), kernel={'state': 'unavailable'}, dispatcher={'state': 'missing'})
        self.assertEqual(self.health_command('sample', activation=scope['activation'], generation=scope['generation'], observation=observation)['result'], 'recorded')
        self.command('deactivate', source=SOURCE, activation=self.activation)
        self.assertEqual(self.health_command('sample', activation=scope['activation'], generation=scope['generation'], observation=observation)['result'], 'rejected')
        self.assertEqual(self.runtime.current()['state'], 'revoked')

    def test_health_storage_failure_does_not_stop_event_reader_or_root_control(self):
        scope = self.activate()
        reader = self.connect(self.data)
        self.send_record(reader, scope)
        self.assertEqual(self.receive(reader)['status'], 'admit')
        self.runtime.db.execute("""CREATE TRIGGER fail_health BEFORE INSERT ON m3_health
            BEGIN SELECT RAISE(ABORT, 'test'); END""")
        result = self.health_command('sample', activation=scope['activation'], generation=scope['generation'],
                    observation=dict(sample_ns=time.monotonic_ns(), kernel={'state': 'unavailable'}, dispatcher={'state': 'missing'}))
        self.assertEqual(result['code'], 'health_storage_failure')
        status = self.command('status')
        self.assertIsNone(status['failure'])
        self.assertEqual(status['health_reporting_error'], 'health_storage_failure')
        self.assertTrue(status['source_ready'])
        self.send_record(reader, scope, begin=10, end=20, identity='1.001:2')
        self.assertEqual(self.receive(reader)['status'], 'admit')

    def send_record(self, client, scope, **fields):
        if not self.runtime.progress.stream_started():
            client.sendall(json.dumps(dict(version=3, op='boundary', **scope)).encode() + b'\n')
            self.assertEqual(self.receive(client)['status'], 'boundary')
        request = dict(version=3, op='register', identity='1.001:1', begin=0, end=10, eoe=False, **scope)
        request.update(fields)
        client.sendall(json.dumps(request).encode() + b'\n')

    def test_no_activation_from_data_and_idle_reader_survives(self):
        denied = self.connect(self.data)
        self.assertIsNone(self.receive(denied))
        self.assertIsNone(self.runtime.current())
        scope = self.activate()
        client = self.connect(self.data)
        self.now = 100
        self.service.run_once()
        self.assertIsNotNone(self.service.reader)
        self.send_record(client, scope)
        self.assertEqual(self.receive(client), {'version': 3, 'status': 'admit'})
        status = self.command('status')
        self.assertTrue(status['reader_connected'])
        self.assertTrue(status['source_ready'])
        self.assertFalse(status['possible_gap'])
        self.assertEqual(status['upstream_loss'], {'kernel': 'unknown', 'dispatcher': 'unknown'})
        self.assertEqual(status['interval']['state'], 'streaming')
        self.assertEqual(self.command('lease')['result'], 'rejected')

    def test_control_cli_preserves_service_status_evidence(self):
        status = self.command('status')
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', ['m3_control', 'status']), \
             mock.patch.object(m3_control.os, 'getuid', return_value=0), \
             mock.patch.object(m3_control.os, 'geteuid', return_value=0), \
             mock.patch.object(m3_control, 'load_config', return_value={'source_id': SOURCE}), \
             mock.patch.object(m3_control, 'request', return_value=status), \
             contextlib.redirect_stdout(output):
            self.assertEqual(m3_control.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), status)
        self.assertEqual(status['upstream_loss'], {'kernel': 'unknown', 'dispatcher': 'unknown'})

    def test_admission_requires_current_tail_boundary(self):
        scope = self.activate()
        reader = self.connect(self.data)
        self.assertFalse(self.command('status')['source_ready'])
        message = dict(version=3, op='register', identity='1.001:1', begin=0, end=10,
                       eoe=False, **scope)
        reader.sendall(json.dumps(message).encode() + b'\n')
        self.assertIsNone(self.receive(reader))
        self.assertEqual(self.runtime.current()['code'], 'protocol_failure')

    def test_root_revocation_precedes_ready_data(self):
        scope = self.activate()
        reader = self.connect(self.data)
        self.send_record(reader, scope)
        self.receive(reader)
        activation = self.runtime.current()
        control = self.connect(self.control)
        control.sendall(json.dumps(dict(version=3, command='deactivate', source=SOURCE,
                                       activation=self.activation)).encode() + b'\n')
        self.send_record(reader, scope, begin=10, end=20)
        self.assertEqual(self.receive(control)['result'], 'deactivated')
        try:
            closed = reader.recv(1) == b''
        except ConnectionResetError:
            closed = True
        self.assertTrue(closed)
        old = Progress(self.runtime.directory / f'{self.activation}.sqlite',
                       self.activation, activation['generation'], 0)
        try:
            self.assertEqual(old.positions(), (10, 10))
        finally:
            old.close()

    def test_partial_deadline_and_stale_scope_are_observable(self):
        self.activate()
        reader = self.connect(self.data)
        reader.sendall(b'{')
        self.service.run_once()
        self.now = 3
        self.service.run_once()
        self.assertEqual(self.runtime.current()['code'], 'deadline')
        self.assertTrue(self.command('status')['possible_gap'])
        self.activation = str(uuid.uuid4())
        scope = self.activate()
        reader = self.connect(self.data)
        reader.sendall(json.dumps(dict(version=3, op='boundary', **scope)).encode() + b'\n')
        self.assertEqual(self.receive(reader)['status'], 'boundary')
        self.send_record(reader, dict(scope, lease=str(uuid.uuid4())))
        self.assertIsNone(self.receive(reader))
        self.assertEqual(self.runtime.current()['code'], 'protocol_failure')

    def test_normalized_commit_survives_revocation(self):
        scope = self.activate()
        reader = self.connect(self.data)
        self.send_record(reader, scope, eoe=True)
        self.assertEqual(self.receive(reader)['status'], 'admit')
        payload = dict(syscall=221, pid=42, ppid=1, uid=1000, euid=1000,
                       suid=1000, fsuid=1000, auid=None, session=7, path_count=1,
                       success=True, cwd_present=True, proctitle_present=True,
                       result=0, exe_base64='L2Jpbi94', comm_base64='eA==')
        message = dict(version=3, op='accept', identity='1.001:1', execution=payload, **scope)
        reader.sendall(json.dumps(message).encode() + b'\n')
        self.assertEqual(self.receive(reader)['status'], 'accepted')
        self.assertEqual(self.runtime.progress.positions(), (10, 10))
        self.command('deactivate', source=SOURCE, activation=self.activation)
        ledger = Progress(self.runtime.directory / f'{self.activation}.sqlite',
                          self.activation, scope['generation'], 0)
        try:
            self.assertEqual(ledger.accept('1.001:1', payload), 'duplicate')
            self.assertEqual(ledger.db.execute('SELECT COUNT(*) FROM m3_execution').fetchone(), (1,))
        finally:
            ledger.close()

    def test_event_storage_failure_is_reported_by_control(self):
        scope = self.activate()
        reader = self.connect(self.data)
        self.runtime.progress.db.execute("""CREATE TRIGGER fail_registration
            BEFORE INSERT ON m3_positions BEGIN SELECT RAISE(ABORT, 'injected'); END""")
        self.send_record(reader, scope)
        self.assertIsNone(self.receive(reader))
        status = self.command('status')
        self.assertEqual(status['failure'], 'storage_failure')
        self.assertEqual(status['interval']['code'], 'storage_failure')
        self.assertTrue(status['possible_gap'])
        self.activation = str(uuid.uuid4())
        self.assertEqual(self.command('activate', source=SOURCE, activation=self.activation)['result'], 'rejected')

    def test_collector_gap_is_durable_and_has_no_execution_claim(self):
        scope = self.activate()
        reader = self.connect(self.data)
        self.send_record(reader, scope)
        self.assertEqual(self.receive(reader)['status'], 'admit')
        reader.sendall(json.dumps(dict(version=3, op='gap', code='assembly_timeout', **scope)).encode() + b'\n')
        self.assertEqual(self.receive(reader), {'version': 3, 'status': 'interrupted'})
        status = self.command('status')
        self.assertEqual(status['interval']['code'], 'assembly_timeout')
        self.assertTrue(status['possible_gap'])
        ledger = Progress(self.runtime.directory / f'{self.activation}.sqlite',
                          self.activation, scope['generation'], 0)
        try:
            self.assertEqual(ledger.positions(), (10, 10))
            self.assertEqual(ledger.db.execute('SELECT COUNT(*) FROM m3_execution').fetchone(), (0,))
        finally:
            ledger.close()

    def test_unknown_gap_code_is_rejected_before_boundary(self):
        scope = self.activate()
        reader = self.connect(self.data)
        reader.sendall(json.dumps(dict(version=3, op='gap', code=['untrusted'], **scope)).encode() + b'\n')
        self.assertIsNone(self.receive(reader))
        self.assertEqual(self.runtime.current()['code'], 'protocol_failure')

    def test_capacity_is_reported_without_claiming_protocol_corruption(self):
        self.runtime.max_activations = 1
        scope = self.activate()
        reader = self.connect(self.data)
        self.runtime.progress.position_limit = 1
        self.send_record(reader, scope)
        self.assertEqual(self.receive(reader)['status'], 'admit')
        self.send_record(reader, scope, begin=10, end=20)
        self.assertIsNone(self.receive(reader))
        status = self.command('status')
        self.assertEqual(status['interval']['code'], 'progress_capacity')
        self.assertTrue(status['possible_gap'])
        self.assertIsNone(status['failure'])
        response = self.command('activate', source=SOURCE, activation=str(uuid.uuid4()))
        self.assertEqual(response['code'], 'capacity_exhausted')


if __name__ == '__main__':
    unittest.main()
