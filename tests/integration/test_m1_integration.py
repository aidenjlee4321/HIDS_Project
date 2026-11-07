"""Actual Linux Unix-socket/process/SQLite tests. Never opens NETLINK_CONNECTOR."""
import copy
import json
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import sqlite3
import sys
import time
import unittest
from unittest.mock import patch

from engine.database.m1_store import get_event
from engine.ingestion.m1_contract import canonical, decode, frame
from engine.ingestion.m1_io import control_read, control_write, read_line
from engine.ingestion.m1_security import peer_matches, private_file
from m1_harness import HarnessFailure, M1Harness

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / 'tests/fixtures/process/m1-exec-envelope.json').read_text())
PRODUCER = os.environ.get('HIDS_M1_PRODUCER', '')


def before_commit(stage):
    if stage == 'before_commit':
        raise sqlite3.OperationalError('injected_before_commit')


def after_commit(stage):
    if stage == 'after_commit':
        raise sqlite3.OperationalError('injected_after_commit')


def startup_fail(stage):
    if stage == 'startup':
        raise sqlite3.OperationalError('injected_startup')


def slow_commit(stage):
    if stage == 'before_commit':
        time.sleep(.1)


def drop_ack(_response):
    raise BrokenPipeError('injected_lost_ack')


def raw_child(path, server_pid, release, report, close_fds, payload, count, mode):
    for fd in close_fds:
        os.close(fd)
    sock = None
    try:
        control_read(release)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(path)
        if not peer_matches(sock, server_pid):
            raise PermissionError('server_identity')
        if mode == 'partial':
            sock.sendall(payload[:40])
        elif mode == 'split':
            for byte in payload:
                sock.sendall(bytes([byte]))
        else:
            sock.sendall(payload)
        if mode in ('partial', 'lost_ack'):
            sock.close()
            sock = None
            control_write(report, {'stage': 'closed'})
        else:
            for _ in range(count):
                response = decode(read_line(sock.fileno(), 512, time.monotonic()+5), 512)
                control_write(report, response)
    except (OSError, EOFError, TimeoutError) as exc:
        control_write(report, {'stage': 'transport_closed', 'reason': type(exc).__name__})
    finally:
        if sock is not None:
            sock.close()
        os.close(release)
        os.close(report)


@unittest.skipUnless(sys.platform == 'linux' and bool(PRODUCER), 'requires Ubuntu/Linux and HIDS_M1_PRODUCER')
class IntegrationTests(unittest.TestCase):
    def harness(self, **kwargs):
        h = M1Harness(PRODUCER, ROOT/'tests/fixtures/process/synthetic-exec-001.json', **kwargs)
        self.addCleanup(h.close)
        return h

    def raw(self, h, payload, count=1, mode='normal', authorize=True):
        release_r, release_w = os.pipe()
        report_r, report_w = os.pipe()
        child = multiprocessing.get_context('fork').Process(target=raw_child,
            args=(str(h.directory/'events.sock'), h.receiver.pid, release_r, report_w,
                  (release_w, report_r), payload, count, mode))
        child.start()
        os.close(release_r)
        os.close(report_w)
        try:
            if authorize:
                h.authorize(child.pid)
            control_write(release_w, {'command': 'go'})
            replies = [control_read(report_r) for _ in range(count)]
            child.join(5)
            self.assertFalse(child.is_alive())
            return replies
        finally:
            os.close(release_w)
            os.close(report_r)
            if child.is_alive():
                child.terminate()
                child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)

    def wait_event(self, h, present=True):
        deadline = time.monotonic()+3
        found = None
        while time.monotonic() < deadline:
            found = get_event(h.directory/'pilot.sqlite', BASE['event_id'])
            if (found is not None) == present:
                return found
            time.sleep(.01)
        self.fail('expected persistence observation not established')

    def test_cpp_to_python_sqlite_readonly(self):
        h = self.harness()
        h.start_producer()
        frozen = bytes(h.original)
        result = h.send()
        self.assertEqual((result['outcome'], result['code'], result['attempts']), ('acknowledged', 'stored', 1))
        event = h.retrieve()
        self.assertEqual(event['native'], BASE['native'])
        self.assertIsNone(event['timestamps']['activity_wall_time'])
        self.assertEqual(h.original, frozen)
        for suffix in ('', '-wal', '-shm'):
            private_file(Path(str(h.directory/'pilot.sqlite')+suffix))
        h.stop_producer()
        h.stop_receiver()
        self.assertEqual(get_event(h.directory/'pilot.sqlite', event['event_id']), event)

    def test_split_coalesced_duplicate_and_collision(self):
        h = self.harness()
        payload = canonical(BASE).encode()+b'\n'
        first = self.raw(h, payload, mode='split')[0]
        self.assertEqual(first['result'], 'stored')
        replies = self.raw(h, payload+payload, count=2)
        self.assertEqual([r['result'] for r in replies], ['duplicate', 'duplicate'])
        changed = copy.deepcopy(BASE)
        changed['native']['pid'] += 1
        reply = self.raw(h, canonical(changed).encode()+b'\n')[0]
        self.assertEqual(reply['code'], 'id_conflict')
        h.receiver.join(5)
        self.assertEqual(h.receiver.exitcode, 1)
        self.assertEqual(get_event(h.directory/'pilot.sqlite', BASE['event_id']), BASE)

    def test_invalid_json_oversized_and_invalid_event(self):
        for payload, code in ((b'{"a":1,"a":2}\n', 'invalid_json'),
                              (b'\n', 'invalid_json'), (b'{}\r\n', 'invalid_json'),
                              (b'x'*65537+b'\n', 'frame_too_large'),
                              (b'{}\n', 'invalid_event')):
            with self.subTest(code=code, size=len(payload)):
                h = self.harness()
                reply = self.raw(h, payload)[0]
                self.assertEqual(reply['code'], code)
                h.receiver.join(5)
                self.assertEqual(h.receiver.exitcode, 1)
                self.assertIsNone(get_event(h.directory/'pilot.sqlite', BASE['event_id']))

    def test_unsupported_version_before_collision(self):
        for key, value in (('protocol_version', 2), ('contract_version', 'unsupported')):
            with self.subTest(key=key):
                h = self.harness()
                self.raw(h, canonical(BASE).encode()+b'\n')
                event = copy.deepcopy(BASE)
                event[key] = value
                reply = self.raw(h, json.dumps(event).encode()+b'\n')[0]
                self.assertEqual(reply['code'], 'unsupported_version')
                h.receiver.join(5)
                self.assertEqual(get_event(h.directory/'pilot.sqlite', BASE['event_id']), BASE)

    def test_partial_disconnect_and_lost_ack_redelivery(self):
        h = self.harness()
        payload = canonical(BASE).encode()+b'\n'
        self.raw(h, payload, mode='partial')
        self.assertIsNone(get_event(h.directory/'pilot.sqlite', BASE['event_id']))
        self.raw(h, payload, mode='lost_ack')
        self.wait_event(h)
        self.assertEqual(self.raw(h, payload)[0]['result'], 'duplicate')

    def test_write_failures_explicit_restart_and_budget(self):
        for fault, expected in ((before_commit, 'stored'), (after_commit, 'duplicate')):
            with self.subTest(expected=expected):
                h = self.harness(fault=fault)
                h.start_producer()
                original = bytes(h.original)
                result = h.send()
                self.assertEqual((result['outcome'], result['code'], result['attempts']), ('unconfirmed', 'storage_error', 1))
                h.receiver.join(5)
                self.assertEqual(h.receiver.exitcode, 1)
                h.start_receiver()  # Explicit action; no receiver self-recovery.
                old_pid = h.producer.pid
                h.stop_producer()
                h.start_producer(restore=True)
                self.assertNotEqual(h.producer.pid, old_pid)
                self.assertEqual(h.original, original)
                result = h.send(explicit_retry=True)
                self.assertEqual((result['outcome'], result['code']), ('acknowledged', expected))
                self.assertEqual(h.retrieve(), decode(original[:-1]))
                with self.assertRaises(HarnessFailure):
                    h.send(explicit_retry=True)

    def test_malformed_ack_reject_and_error_are_unconfirmed(self):
        mutations = [lambda r: {**r, 'result': 'pending'},
                     lambda r: b'{\n',
                     lambda r: b'{"protocol_version":1,"protocol_version":1}\n',
                     lambda r: {'protocol_version': True, 'message_type': 'reject', 'event_id': None, 'code': 'invalid_event'},
                     lambda r: {'protocol_version': 1, 'message_type': 'error', 'event_id': None, 'code': 'storage_error'},
                     lambda r: {'protocol_version': 1, 'message_type': 'reject', 'event_id': r['event_id'], 'code': 'unknown'},
                     lambda r: {'protocol_version': 1, 'message_type': 'error', 'event_id': r['event_id'], 'code': 'unknown'}]
        for mutate in mutations:
            h = self.harness(response_hook=mutate)
            h.start_producer()
            result = h.send()
            self.assertEqual((result['outcome'], result['code'], result['attempts']), ('unconfirmed', 'response_protocol_error', 1))
            self.assertIsNotNone(h.retrieve())  # Malformed ACK never revokes commit.

    def test_wrong_peer_pid_denied_before_event_bytes(self):
        h = self.harness()
        h.authorize(os.getpid())  # A different child is deliberately not authorized.
        reply = self.raw(h, canonical(BASE).encode()+b'\n', authorize=False)[0]
        self.assertEqual(reply['stage'], 'transport_closed')
        self.assertEqual(control_read(h.reports)['stage'], 'peer_denied')
        self.assertIsNone(get_event(h.directory/'pilot.sqlite', BASE['event_id']))

    def test_signal_cleanup(self):
        h = self.harness()
        os.kill(h.receiver.pid, signal.SIGINT)
        h.receiver.join(5)
        self.assertFalse(h.receiver.is_alive())
        self.assertEqual(h.receiver.exitcode, 0)
        self.assertFalse((h.directory/'events.sock').exists())

    def test_startup_failure_has_no_event_response(self):
        with self.assertRaises(HarnessFailure) as result:
            self.harness(fault=startup_fail)
        self.assertEqual(str(result.exception), 'startup_failure')

    def test_exhausted_automatic_attempts_and_explicit_fresh_operation(self):
        h = self.harness(response_hook=drop_ack)
        h.start_producer()
        original = bytes(h.original)
        result = h.send()
        self.assertEqual((result['outcome'], result['attempts']), ('unconfirmed', 3))
        self.assertEqual(h.operations, 1)
        h.stop_receiver()
        h.start_receiver()
        result = h.send(explicit_retry=True)
        self.assertEqual((result['outcome'], result['code'], result['attempts']), ('acknowledged', 'duplicate', 1))
        self.assertEqual(h.original, original)
        with self.assertRaises(HarnessFailure):
            h.send(explicit_retry=True)

    def test_slow_database_and_post_commit_retrieval_failure(self):
        h = self.harness(fault=slow_commit)
        h.start_producer()
        start = time.monotonic()
        self.assertEqual(h.send()['outcome'], 'acknowledged')
        self.assertGreaterEqual(time.monotonic()-start, .1)
        with patch('engine.database.m1_store.profile', side_effect=RuntimeError('injected_retrieval')):
            with self.assertRaises(RuntimeError):
                h.retrieve()
        self.assertEqual(h.outcome, 'acknowledged')
        self.assertIsNotNone(h.retrieve())


if __name__ == '__main__':
    unittest.main()
