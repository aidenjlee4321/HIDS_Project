"""Explicit root-only Ubuntu acceptance for the installed M3 service and launcher.

Uses a sanitized fixture. Existing event history is preserved. Service activation,
revocation and one intentional backend kill are confined to hids-m3.service.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import pwd
import re
import grp
import sqlite3
import subprocess
import sys
import time
import tempfile
import uuid

APP = Path('/usr/lib/hids')
STATE = Path('/var/lib/hids/m3')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'PYTHONPATH': str(APP), 'LANG': 'C'}


def control(command, activation=None):
    arguments = ['/usr/bin/python3', '-B', '-m', 'engine.ingestion.m3_control', command]
    if activation is not None:
        arguments += ['--activation-id', activation]
    completed = subprocess.run(arguments, cwd=APP, env=ENV, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=8)
    if completed.returncode:
        raise RuntimeError('M3 control command failed')
    return json.loads(completed.stdout)


def until(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise TimeoutError('M3 acceptance condition not reached')


def query(activation, sql):
    path = STATE / f'{activation}.sqlite'
    account = pwd.getpwnam('hids-ingest')
    original_uid, original_gid = os.geteuid(), os.getegid()
    os.setegid(account.pw_gid)
    os.seteuid(account.pw_uid)
    connection = None
    try:
        # A read-only WAL connection can still create sidecars. Keep them under
        # the actual database owner, including when reading an ended interval.
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)
        return connection.execute(sql).fetchall()
    finally:
        if connection is not None:
            connection.close()
        os.seteuid(original_uid)
        os.setegid(original_gid)



class Reader:
    def __init__(self, queued=b''):
        self.input, self.output = os.pipe()
        if queued:
            os.write(self.output, queued)
        self.process = subprocess.Popen(
            ['/usr/bin/python3', '-B', '-m', 'engine.ingestion.m3_launch'],
            cwd=APP, env=ENV, stdin=self.input, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process.stderr.close()
        os.close(self.input)
        os.close(self.output)

    def send(self, value):
        remaining = memoryview(value)
        while remaining:
            count = os.write(self.output, remaining)
            remaining = remaining[count:]


def verify_identity(reader):
    account = pwd.getpwnam('hids-audit')
    ipc = grp.getgrnam('hids-ipc').gr_gid
    fields = {}
    for line in Path(f'/proc/{reader.process.pid}/status').read_text().splitlines():
        key, _, value = line.partition(':')
        fields[key] = value.split()
    assert list(map(int, fields['Uid'])) == [account.pw_uid] * 4
    assert list(map(int, fields['Gid'])) == [account.pw_gid] * 4
    assert set(map(int, fields['Groups'])) == {ipc}
    assert all(int(fields[name][0], 16) == 0 for name in
               ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'))
    assert fields['NoNewPrivs'] == ['1']


def process_usage(pid):
    values = {}
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        name, _, value = line.partition(':')
        if name == 'VmHWM':
            values['high_water_kib'] = int(value.split()[0])
    fields = Path(f'/proc/{pid}/stat').read_text().rpartition(') ')[2].split()
    values['cpu_seconds'] = (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')
    return values


def ordinary_denial():
    nobody = pwd.getpwnam('nobody')
    arguments = ['/usr/bin/setpriv', '--reuid', str(nobody.pw_uid), '--regid',
                 str(nobody.pw_gid), '--clear-groups', '--no-new-privs',
                 '/usr/bin/python3', '-B', '-m', 'engine.ingestion.m3_control', 'status']
    completed = subprocess.run(arguments, cwd=APP, env=ENV, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=3)
    assert completed.returncode == 1
    ipc = grp.getgrnam('hids-ipc').gr_gid
    script = """
import socket
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(2)
    connection.connect('/run/hids/m3/ingest/audit.sock')
    try:
        assert connection.recv(1) == b''
    except ConnectionResetError:
        pass
"""
    arguments = ['/usr/bin/setpriv', '--reuid', str(nobody.pw_uid), '--regid',
                 str(nobody.pw_gid), '--groups', str(ipc), '--no-new-privs',
                 '/usr/bin/python3', '-B', '-c', script]
    completed = subprocess.run(arguments, cwd=APP, env=ENV, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=3)
    assert completed.returncode == 0


def live_audit():
    configuration = Path('/etc/audit/auditd.conf')
    plugin = Path('/etc/audit/plugins.d/hids-m3-runtime-acceptance.conf')
    assert not plugin.exists() and not plugin.is_symlink()
    assert subprocess.check_output(['auditctl', '-l']).strip() == b'No rules'
    original = configuration.read_bytes()
    raw, changed = re.subn(rb'(?m)^\s*log_format\s*=.*$', b'log_format = RAW', original)
    assert changed == 1
    activation = str(uuid.uuid4())
    backup = tempfile.TemporaryDirectory(prefix='hids-m3-runtime-audit.', dir='/run')
    backup_path = Path(backup.name) / 'auditd.conf'
    backup_path.write_bytes(original)
    backup_path.chmod(0o600)
    try:
        control('activate', activation)
        fd = os.open(plugin, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o640)
        with os.fdopen(fd, 'w') as stream:
            stream.write('active = yes\npath = /usr/lib/hids/hids-audit-launcher\ntype = always\nformat = string\n')
        configuration.write_bytes(raw)
        subprocess.run(['auditctl', '--signal', 'reload'], check=True)
        until(lambda: control('status')['source_ready'])
        rule = ['always,exit', '-F', 'arch=b64', '-S', 'execve,execveat',
                '-F', f'ppid={os.getpid()}', '-k', 'hids_m3_runtime_acceptance']
        subprocess.run(['auditctl', '-a', *rule], check=True)
        try:
            subprocess.run(['/usr/bin/true', 'native-runtime-fixture', 'x' * 10000], check=True)
            subprocess.run(['auditctl', '-d', *rule], check=True)
            rule = None
            executable = base64.b64encode(os.fsencode(os.path.realpath('/usr/bin/true'))).decode('ascii')
            def matching():
                events = [json.loads(row[0]) for row in query(activation, 'SELECT payload FROM m3_execution')]
                return [event for event in events if event['exe_base64'] == executable and
                        event['comm_base64'] == 'dHJ1ZQ==' and event['success']]
            events = until(matching)
            assert len(events) == 1 and events[0]['path_count'] == 2
            status = control('status')
            assert status['source_ready'] and status['reader_connected'] and status['failure'] is None
            print('PASS: live auditd through root activation, capability-free reader, current-tail boundary and durable SQLite event', flush=True)
        finally:
            if rule is not None:
                subprocess.run(['auditctl', '-d', *rule], check=True)
        control('deactivate', activation)
    finally:
        try:
            control('deactivate', activation)
        except Exception:
            pass
        plugin.unlink(missing_ok=True)
        configuration.write_bytes(original)
        subprocess.run(['auditctl', '--signal', 'reload'], check=True)
        assert configuration.read_bytes() == original
        assert subprocess.check_output(['auditctl', '-l']).strip() == b'No rules'
        subprocess.run(['systemctl', 'is-active', 'auditd'], check=True)
        backup.cleanup()



def capacity_limits(fixture):
    configuration = Path('/etc/hids/m3.json')
    original = configuration.read_bytes()
    reader = None
    activation = str(uuid.uuid4())
    try:
        subprocess.run(['systemctl', 'stop', 'hids-m3.socket', 'hids-m3.service'], check=True, timeout=5)
        settings = json.loads(original)
        settings['position_limit'] = 1
        configuration.write_text(json.dumps(settings) + '\n')
        subprocess.run(['systemctl', 'start', 'hids-m3.socket'], check=True, timeout=5)
        control('activate', activation)
        reader = Reader()
        until(lambda: control('status')['source_ready'])
        reader.send(fixture.replace(b':100)', b':106)'))
        assert reader.process.wait(timeout=4) != 0
        status = control('status')
        assert status['interval']['code'] == 'progress_capacity' and status['possible_gap']
        assert status['failure'] is None
        assert query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(0,)]
        control('deactivate', activation)
        subprocess.run(['systemctl', 'stop', 'hids-m3.socket', 'hids-m3.service'], check=True, timeout=5)
        settings = json.loads(original)
        settings['max_activations'] = 1
        configuration.write_text(json.dumps(settings) + '\n')
        subprocess.run(['systemctl', 'start', 'hids-m3.socket'], check=True, timeout=5)
        arguments = ['/usr/bin/python3', '-B', '-m', 'engine.ingestion.m3_control',
                     'activate', '--activation-id', str(uuid.uuid4())]
        rejected = subprocess.run(arguments, cwd=APP, env=ENV, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=5)
        assert rejected.returncode == 1
        assert json.loads(rejected.stdout)['code'] == 'capacity_exhausted'
        print('PASS: configured position and activation limits preserve history and report capacity exhaustion', flush=True)
    finally:
        configuration.write_bytes(original)
        if reader is not None:
            reader.close()
        subprocess.run(['systemctl', 'stop', 'hids-m3.socket', 'hids-m3.service'], timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--live-audit', action='store_true', help='Temporarily configure an auditd plugin and one process-scoped rule')
    parser.add_argument('--capacity-limits', action='store_true', help='Temporarily lower HIDS budgets to test capacity handling')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.getuid() != 0 or os.geteuid() != 0:
        raise PermissionError('explicit root-only Ubuntu test')
    fixture = args.fixture.read_bytes()
    assert fixture.startswith(b'type=SYSCALL ') and fixture.endswith(b':\n')
    lines = fixture.splitlines()
    lines[-1] += b' '
    fixture = b'\n'.join(lines) + b'\n'
    readers = []
    activation = None
    try:
        baseline = control('status')
        assert baseline['interval'] is None or baseline['interval']['state'] not in ('ready', 'streaming')
        queued = b'not authorized fixture bytes\n'
        denied = Reader(queued)
        readers.append(denied)
        assert denied.process.wait(timeout=4) == 1
        os.set_blocking(denied.input, False)
        assert os.read(denied.input, len(queued)) == queued
        assert control('status')['interval'] == baseline['interval']
        print('PASS: unauthorized launcher consumes no source input', flush=True)

        activation = str(uuid.uuid4())
        control('activate', activation)
        ordinary_denial()
        assert control('status')['interval']['state'] == 'ready'
        reader = Reader(fixture)
        readers.append(reader)
        until(lambda: control('status')['source_ready'])
        verify_identity(reader)
        assert query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(0,)]
        assert query(activation, 'SELECT scanned,frontier FROM m3_cursor') == [(0, 0)]
        reader.send(fixture.replace(b':100)', b':101)'))
        until(lambda: query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(1,)])
        assert query(activation, 'SELECT identity FROM m3_execution') == [('1794096000.123:101',)]
        started = time.monotonic()
        burst = b''.join(fixture.replace(b':100)', f':{serial})'.encode()) for serial in range(200, 264))
        reader.send(burst)
        until(lambda: query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(65,)], timeout=15)
        elapsed = time.monotonic() - started
        print(f'PASS: 64 additional fixture executions committed in {elapsed:.3f} seconds', flush=True)
        backend_pid = int(subprocess.check_output(['systemctl', 'show', 'hids-m3.service', '-p', 'MainPID', '--value']))
        before = {name: process_usage(pid) for name, pid in
                  (('collector', reader.process.pid), ('backend', backend_pid))}
        idle_start = time.monotonic()
        time.sleep(1)
        after = {name: process_usage(pid) for name, pid in
                 (('collector', reader.process.pid), ('backend', backend_pid))}
        measured = {'idle_seconds': round(time.monotonic() - idle_start, 3)}
        for name in before:
            measured[name] = dict(high_water_kib=after[name]['high_water_kib'],
                                  idle_cpu_seconds=round(after[name]['cpu_seconds'] - before[name]['cpu_seconds'], 3))
        print('Observed fixture process resources ' + json.dumps(measured, sort_keys=True), flush=True)
        control('deactivate', activation)
        assert reader.process.wait(timeout=3) != 0
        assert query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(65,)]
        assert control('status')['interval']['state'] == 'revoked'
        print('PASS: real root control, peer denial, privilege drop, current-tail exclusion and live revocation', flush=True)

        activation = str(uuid.uuid4())
        control('activate', activation)
        reader = Reader()
        readers.append(reader)
        until(lambda: control('status')['source_ready'])
        first = fixture.splitlines(keepends=True)[0].replace(b':100)', b':102)')
        reader.send(first)
        until(lambda: query(activation, 'SELECT scanned FROM m3_cursor')[0][0] > 0)
        subprocess.run(['systemctl', 'kill', '--kill-whom=main', '--signal=KILL', 'hids-m3.service'], check=True, timeout=3)
        assert reader.process.wait(timeout=3) != 0
        status = control('status')
        assert status['interval']['activation'] == activation
        assert status['interval']['state'] == 'interrupted'
        assert status['interval']['code'] == 'backend_restart'
        assert status['possible_gap'] and not status['source_ready']
        assert query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(0,)]
        scanned, frontier = query(activation, 'SELECT scanned,frontier FROM m3_cursor')[0]
        assert scanned == frontier > 0
        print('PASS: actual backend kill, interrupted admission recovery and no automatic reactivation', flush=True)

        activation = str(uuid.uuid4())
        control('activate', activation)
        reader = Reader()
        readers.append(reader)
        until(lambda: control('status')['source_ready'])
        reader.send(fixture.replace(b':100)', b':103)'))
        until(lambda: query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(1,)])
        control('deactivate', activation)
        assert reader.process.wait(timeout=3) != 0
        print('PASS: fresh root authorization resumes with a new stream after backend restart', flush=True)

        activation = str(uuid.uuid4())
        control('activate', activation)
        reader = Reader()
        readers.append(reader)
        until(lambda: control('status')['source_ready'])
        records = fixture.replace(b':100)', b':104)').splitlines(keepends=True)
        reader.send(records[0])
        until(lambda: query(activation, 'SELECT scanned FROM m3_cursor')[0][0] > 0)
        blocker = sqlite3.connect(STATE / f'{activation}.sqlite', isolation_level=None)
        try:
            blocker.execute('BEGIN IMMEDIATE')
            reader.send(b''.join(records[1:]))
            assert reader.process.wait(timeout=5) != 0
            status = control('status')
            assert status['failure'] == 'storage_failure' and status['possible_gap']
            assert status['interval']['code'] == 'storage_failure'
            assert query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(0,)]
            scanned, frontier = query(activation, 'SELECT scanned,frontier FROM m3_cursor')[0]
            assert scanned > 0 and frontier == 0
        finally:
            blocker.rollback()
            blocker.close()
        subprocess.run(['systemctl', 'restart', 'hids-m3.service'], check=True, timeout=5)
        assert control('status')['failure'] is None
        print('PASS: blocked event storage preserves unresolved progress and reports failure through independent root control', flush=True)

        activation = str(uuid.uuid4())
        control('activate', activation)
        reader = Reader()
        readers.append(reader)
        until(lambda: control('status')['source_ready'])
        reader.send(b'invalid fixture input\n')
        assert reader.process.wait(timeout=4) != 0
        status = control('status')
        assert status['interval']['code'] == 'collector_input_failure'
        assert status['possible_gap'] and status['failure'] is None
        print('PASS: collector input failure is durably reported without claiming an execution', flush=True)

        activation = str(uuid.uuid4())
        control('activate', activation)
        reader = Reader()
        readers.append(reader)
        until(lambda: control('status')['source_ready'])
        reader.send(fixture.splitlines(keepends=True)[0].replace(b':100)', b':105)'))
        until(lambda: query(activation, 'SELECT COUNT(*) FROM m3_timeouts') == [(1,)], timeout=13)
        status = control('status')
        assert status['interval']['state'] == 'streaming' and status['possible_gap']
        assert status['source_ready'] and status['reader_connected'] and reader.process.poll() is None
        assert status['event_health']['timeouts'] == 1
        assert query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(0,)]
        late_eoe = fixture.splitlines(keepends=True)[-1].replace(b':100)', b':105)')
        reader.send(late_eoe)
        until(lambda: control('status')['event_health']['late_records'] == 1)
        reader.send(fixture.replace(b':100)', b':106)'))
        until(lambda: query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(1,)])
        assert query(activation, "SELECT identity FROM m3_execution WHERE identity LIKE '%:105'") == []
        scanned, frontier = query(activation, 'SELECT scanned,frontier FROM m3_cursor')[0]
        assert scanned == frontier
        control('deactivate', activation)
        assert reader.process.wait(timeout=3) != 0
        print('PASS: durable per-event timeout, late EOE suppression and continued independent execution', flush=True)
        if args.live_audit:
            live_audit()
        if args.capacity_limits:
            capacity_limits(fixture)
        return 0
    finally:
        if activation is not None:
            try:
                control('deactivate', activation)
            except Exception:
                pass
        for reader in readers:
            reader.close()


if __name__ == '__main__':
    raise SystemExit(main())
