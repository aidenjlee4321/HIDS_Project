"""Kill real SQLite writers at deterministic M3 transaction boundaries.

Uses only sanitized data in a new private directory; no services or Audit settings.
Evidence databases are retained. This tests process death, not power loss or reboot.
"""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.ingestion.m3_progress import Progress, ProgressError

A, B, C = '1.001:1', '1.001:2', '1.001:3'
EXECUTION = dict(syscall=221, pid=42, ppid=1, uid=1000, euid=1000,
                 suid=1000, fsuid=1000, auid=None, session=7, path_count=1,
                 success=True, cwd_present=True, proctitle_present=True,
                 result=0, exe_base64='L2Jpbi94', comm_base64='eA==')
TIMEOUT = dict(policy=1, reason='lifetime', first_active_ms=0, last_active_ms=20,
               observed_active_ms=100, observed_monotonic_ms=150, paused_ms=50,
               inactivity_limit_ms=50, lifetime_limit_ms=100)
RESOURCE = dict(policy=1, reason='event_bytes', event_bytes_before=10, event_records_before=1,
                trigger_begin=130, trigger_end=140, incoming_for_event=True, group_limit=15,
                group_record_limit=64, aggregate_limit=32768, retained_accounted_bytes=4096,
                retained_records=1, retained_record_limit=4096, requested_accounted_bytes=1034,
                observed_active_ms=10, observed_monotonic_ms=20, paused_ms=10)

# Trace callbacks run before the matched statement executes. Each later cut also
# proves prior statements executed; before COMMIT leaves a real open transaction.
CUTS = {
    'register': ['BEGIN IMMEDIATE', 'INSERT OR IGNORE INTO m3_disposition',
                 'INSERT INTO m3_eoe', 'INSERT INTO m3_positions',
                 'UPDATE m3_cursor SET scanned=', 'COMMIT', 'returned'],
    'accept': ['BEGIN IMMEDIATE', 'INSERT INTO m3_execution', 'INSERT INTO m3_event_metadata',
               'UPDATE m3_cursor SET frontier=', 'COMMIT', 'returned'],
    'reject': ['BEGIN IMMEDIATE', 'UPDATE m3_disposition SET state=', 'INSERT INTO m3_rejections',
               'UPDATE m3_cursor SET frontier=', 'COMMIT', 'returned'],
    'timeout': ['BEGIN IMMEDIATE', 'INSERT INTO m3_timeouts', 'INSERT INTO m3_rejections',
                'UPDATE m3_disposition SET state=', 'UPDATE m3_cursor SET frontier=',
                'COMMIT', 'returned'],
    'resource': ['BEGIN IMMEDIATE', 'INSERT INTO m3_resources', 'COMMIT', 'returned'],
    'late': ['BEGIN IMMEDIATE', 'INSERT INTO m3_positions',
             'UPDATE m3_cursor SET scanned=', 'INSERT INTO m3_late_positions',
             'UPDATE m3_cursor SET frontier=', 'COMMIT', 'returned'],
    'recover': ['BEGIN IMMEDIATE', 'UPDATE m3_disposition SET state=',
                'UPDATE m3_cursor SET frontier=', 'COMMIT', 'returned'],
}


def open_ledger(path):
    return Progress(path, 'activation', 'generation', 100)


def seed(path, operation):
    ledger = open_ledger(path)
    try:
        ledger.register(A, 100, 110)
        ledger.register(B, 110, 120)
        ledger.register(B, 120, 130, eoe=True)
        ledger.accept(B, EXECUTION)
        if operation in ('accept', 'reject'):
            ledger.register(A, 130, 140, eoe=True)
        if operation in ('resource', 'recover'):
            ledger.register(A, 130, 140)
        if operation == 'recover':
            ledger.resource(A, RESOURCE)
        if operation == 'late':
            ledger.timeout(A, TIMEOUT)
    finally:
        ledger.close()


def operation_call(ledger, operation):
    if operation == 'register': return ledger.register(C, 130, 140, eoe=True)
    if operation == 'accept': return ledger.accept(A, EXECUTION,observation=dict(version=1,arch=0xc00000b7,profile='linux.audit.aarch64.string/1',first_observed_unix_ns=123456789))
    if operation == 'reject': return ledger.reject(A)
    if operation == 'timeout': return ledger.timeout(A, TIMEOUT)
    if operation == 'resource': return ledger.resource(A, RESOURCE)
    if operation == 'late': return ledger.register(A, 130, 140, eoe=True)
    if operation == 'recover': return ledger.recover()
    raise AssertionError('unknown operation')


def worker(path, operation, cut, notice):
    ledger = open_ledger(path)
    def block():
        os.write(notice, b'boundary\n')
        while True: signal.pause()
    def trace(statement):
        if cut != 'returned' and statement.startswith(cut): block()
    ledger.db.set_trace_callback(trace)
    operation_call(ledger, operation)
    if cut == 'returned': block()
    raise AssertionError('selected boundary was not reached')


def verify(path, operation, committed):
    ledger = open_ledger(path)
    try:
        assert ledger.db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert ledger.db.execute('PRAGMA synchronous').fetchone() == (2,)
        assert ledger.db.execute('SELECT payload FROM m3_execution WHERE identity=?', (B,)).fetchone() == (
            json.dumps(EXECUTION, sort_keys=True, separators=(',', ':')),)
        target_scanned = 140 if operation in ('accept', 'reject', 'resource', 'recover') or committed and operation in ('register', 'late') else 130
        expected_frontier = target_scanned if committed and operation in ('accept', 'reject', 'timeout', 'recover') else (140 if committed else 130) if operation == 'late' else 100
        assert ledger.positions() == (target_scanned, expected_frontier)
        expected_count = 4 if operation in ('accept', 'reject', 'resource', 'recover') or committed and operation in ('register', 'late') else 3
        assert ledger.db.execute('SELECT COUNT(*) FROM m3_positions').fetchone() == (expected_count,)
        expected_state = 'accepted' if operation == 'accept' and committed else 'rejected' if operation == 'late' or committed and operation in ('reject', 'timeout') else 'interrupted' if operation == 'recover' and committed else 'open'
        assert ledger._state(A) == expected_state
        assert bool(ledger.db.execute('SELECT 1 FROM m3_execution WHERE identity=?', (A,)).fetchone()) == (operation == 'accept' and committed)
        for table, op in (('m3_timeouts', 'timeout'), ('m3_resources', 'resource'), ('m3_late_positions', 'late')):
            count = ledger.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            expected = int(operation == op and committed or table == 'm3_timeouts' and operation == 'late' or table == 'm3_resources' and operation == 'recover')
            assert count == expected, (table, count, expected)
        if operation == 'register':
            assert ledger._state(C) == ('open' if committed else None)
            assert bool(ledger.db.execute('SELECT 1 FROM m3_eoe WHERE identity=?', (C,)).fetchone()) == committed
        if operation == 'recover':
            assert ledger._state(A) == ('interrupted' if committed else 'open')
            assert ledger.positions()[1] == (140 if committed else 100)
        if operation == 'resource':
            assert ledger._state(A) == 'open' and ledger.positions()[1] == 100
        metadata_ids=ledger.db.execute('SELECT identity FROM m3_event_metadata ORDER BY identity').fetchall()
        assert metadata_ids==([(A,),(B,)] if operation=='accept' and committed else [(B,)])
        assert ledger.db.execute('SELECT COUNT(*) FROM m3_rejections').fetchone()==(int(operation=='late' or committed and operation in ('reject','timeout')),)
        if operation=='accept' and committed:
            assert ledger.db.execute('SELECT arch,first_observed_unix_ns FROM m3_event_metadata WHERE identity=?',(A,)).fetchone()==(0xc00000b7,123456789)
        ledger.recover()
        assert ledger.positions() == (target_scanned, target_scanned)
        if operation == 'accept' and committed:
            assert ledger.accept(A, EXECUTION) == 'duplicate'
            try: ledger.accept(A, dict(EXECUTION, pid=43))
            except ProgressError: pass
            else: raise AssertionError('conflicting accepted retry permitted')
        else:
            try: ledger.accept(A, EXECUTION)
            except ProgressError: pass
            else: raise AssertionError('interrupted/rejected event resurrected')
        # An acknowledged registration whose ACK was lost is interrupted, never
        # reconstructed. Pre-registration input must remain genuinely new.
        if operation == 'register':
            classification = ledger.register(C, 130, 140, eoe=True)
            assert classification == ('replay' if committed else 'admit')
            if committed:
                assert ledger.register(C, 140, 150, eoe=True) == 'suppressed'
            else:
                ledger.recover()
        if operation == 'resource' and committed:
            assert ledger.resource(A, RESOURCE) == 'resource_recorded'
        if operation == 'timeout' and committed:
            assert ledger.timeout(A, TIMEOUT) == 'timed_out'
        if operation == 'late' and committed:
            assert ledger.register(A, 130, 140, eoe=True) == 'replay'
        end = ledger.positions()[0]
        assert ledger.register(A, end, end+10, eoe=True) == 'suppressed'
        assert ledger.positions() == (end+10, end+10)
        assert ledger.db.execute('SELECT identity FROM m3_execution ORDER BY identity').fetchall() == ([(A,), (B,)] if operation == 'accept' and committed else [(B,)])
    finally:
        ledger.close()


SOURCE = '7d9b6873-c6a0-4e9a-88ab-5ec2c04dc592'
ACTIVATION = '47e48803-cdf5-44c5-8b08-f873575470e7'
RUNTIME_CUTS = {
    'activate': ['ledger_cursor', 'ledger_commit', 'control_insert', 'control_committed', 'returned'],
    'claim': ['control_update', 'returned'],
    'interrupt': ['recovery_commit', 'control_update', 'returned'],
    'revoke': ['recovery_commit', 'control_update', 'returned'],
    'restart': ['recovery_commit', 'control_update', 'returned'],
}


def open_runtime(directory):
    from engine.ingestion.m3_runtime import Runtime
    return Runtime(directory, SOURCE, max_activations=2, max_pages=128, position_limit=64)


def runtime_worker(directory, operation, cut, notice):
    directory = Path(directory)
    directory.mkdir(mode=0o700)
    runtime = open_runtime(directory)
    def block():
        os.write(notice, b'boundary\n')
        while True: signal.pause()
    seen_insert = False
    def control_trace(statement):
        nonlocal seen_insert
        if statement.startswith('INSERT INTO m3_intervals'):
            if cut == 'control_insert': block()
            seen_insert = True
        if cut == 'control_committed' and seen_insert and statement.startswith('SELECT'):
            block()
        if cut == 'control_update' and statement.startswith('UPDATE m3_intervals SET state='):
            block()
    def progress_trace(statement):
        if cut == 'ledger_cursor' and statement.startswith('INSERT OR IGNORE INTO m3_cursor'):
            block()
        if cut in ('ledger_commit', 'recovery_commit') and statement == 'COMMIT':
            block()
    if operation != 'activate':
        runtime.activate(ACTIVATION)
        if operation != 'claim':
            runtime.claim()
            runtime.progress.register(A, 0, 10)
            runtime.progress.register(B, 10, 20)
            runtime.progress.register(B, 20, 30, eoe=True)
            runtime.progress.accept(B, EXECUTION)
            runtime.progress.register(A, 30, 40)
            runtime.progress.resource(A, dict(RESOURCE, trigger_begin=30, trigger_end=40))
    if operation == 'restart':
        runtime.close()
    # Install only test-side trace callbacks. No production hooks or global VM
    # services are involved. New activation/restart connections are traced too.
    original_connect = sqlite3.connect
    def traced_connect(database, *args, **kwargs):
        connection = original_connect(database, *args, **kwargs)
        if Path(database).name == ACTIVATION+'.sqlite':
            connection.set_trace_callback(progress_trace)
        elif Path(database).name == 'control.sqlite':
            connection.set_trace_callback(control_trace)
        return connection
    sqlite3.connect = traced_connect
    if operation == 'restart':
        runtime = open_runtime(directory)
    else:
        runtime.db.set_trace_callback(control_trace)
        if runtime.progress is not None:
            runtime.progress.db.set_trace_callback(progress_trace)
        if operation == 'activate': runtime.activate(ACTIVATION)
        elif operation == 'claim': runtime.claim()
        elif operation == 'interrupt': runtime.interrupt('stream_disconnected')
        elif operation == 'revoke': runtime.revoke(ACTIVATION)
    if cut == 'returned': block()
    raise AssertionError('runtime boundary not reached')


def verify_runtime(directory, operation, cut):
    runtime = open_runtime(directory)
    try:
        assert runtime.db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        status = runtime.status()
        assert not status['source_ready'] and runtime.progress is None
        try: runtime.claim()
        except ProgressError: pass
        else: raise AssertionError('restart reused authorization')
        if operation == 'activate' and cut in ('ledger_cursor', 'ledger_commit', 'control_insert'):
            assert runtime.current() is None
            assert (directory / (ACTIVATION+'.sqlite')).exists()
            try: runtime.activate(ACTIVATION)
            except ProgressError: pass
            else: raise AssertionError('orphan activation silently reused')
        else:
            current = runtime.current()
            assert current['activation'] == ACTIVATION
            assert current['state'] == ('revoked' if operation == 'revoke' and cut == 'returned' else 'interrupted')
            if operation == 'revoke' and cut == 'returned': assert current['code'] == 'revoked'
            else: assert status['possible_gap']
            ledger = Progress(directory / (ACTIVATION+'.sqlite'), ACTIVATION, current['generation'], 0)
            try:
                assert ledger.db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
                if operation in ('activate', 'claim'):
                    assert ledger.positions() == (0, 0)
                else:
                    assert ledger.positions() == (40, 40)
                    assert ledger._state(A) == 'interrupted'
                    assert ledger._state(B) == 'accepted'
                    assert ledger.db.execute('SELECT identity FROM m3_execution').fetchall() == [(B,)]
                    assert ledger.event_health()['resource_incidents'] == 1
                    assert ledger.register(A, 40, 50, eoe=True) == 'suppressed'
            finally: ledger.close()
        # The orphan remains evidence, and a new explicit interval can be created
        # within the independent file budget; nothing auto-activates on startup.
        fresh = '7e2fa287-0ce3-4055-90de-c786a09f2073'
        runtime.activate(fresh)
        runtime.revoke(fresh)
    finally: runtime.close()


def kill_at_boundary(path, operation, cut):
    read_fd, write_fd = os.pipe()
    child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                              '--worker', str(path), operation, cut, str(write_fd)],
                             pass_fds=(write_fd,))
    os.close(write_fd)
    try:
        assert select.select([read_fd], [], [], 10)[0], 'worker boundary timeout'
        assert os.read(read_fd, 100) == b'boundary\n', 'worker exited before boundary'
        child.kill()
        assert child.wait(timeout=5) == -signal.SIGKILL
    finally:
        os.close(read_fd)
        if child.poll() is None: child.kill();child.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', nargs=4, metavar=('DATABASE', 'OPERATION', 'CUT', 'NOTICE_FD'))
    args = parser.parse_args()
    if args.worker:
        path, operation, cut, notice = args.worker
        if operation.startswith("runtime:"):
            runtime_worker(path, operation.split(":",1)[1], cut, int(notice))
        else: worker(path, operation, cut, int(notice))
        return
    os.umask(0o077)
    directory = Path(tempfile.mkdtemp(prefix='hids-m3-crash-matrix.')).resolve()
    total = 0
    for operation, cuts in CUTS.items():
        for index, cut in enumerate(cuts):
            path = directory / f'{operation}-{index}.sqlite'
            seed(path, operation)
            kill_at_boundary(path, operation, cut)
            verify(path, operation, cut == 'returned')
            total += 1
        print(f'PASS: {operation}: {len(cuts)} actual SIGKILL boundaries', flush=True)
    for operation, cuts in RUNTIME_CUTS.items():
        for index, cut in enumerate(cuts):
            case_directory = directory / f'runtime-{operation}-{index}'
            kill_at_boundary(case_directory, 'runtime:'+operation, cut)
            verify_runtime(case_directory, operation, cut)
            total += 1
        print(f'PASS: runtime {operation}: {len(cuts)} actual SIGKILL boundaries', flush=True)
    print(json.dumps(dict(passed=total, retained_evidence=str(directory)), sort_keys=True), flush=True)


if __name__ == '__main__': main()
