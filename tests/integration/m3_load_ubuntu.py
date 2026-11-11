"""Explicit root-only installed-runtime load and storage-wait acceptance.

Uses sanitized stdin fixtures, never modifies Audit configuration or rules, and
preserves every generated database. Temporary HIDS budgets are restored at exit.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid

from m3_runtime_ubuntu_acceptance import Reader, STATE, control, query, until


def usage(pid):
    fields = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines())
    result={key: int(fields[key].split()[0]) for key in ('VmRSS', 'VmHWM')}
    times=Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()
    result['CpuSeconds']=(int(times[11])+int(times[12]))/os.sysconf('SC_CLK_TCK')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--events', type=int, default=4096)
    parser.add_argument('--duration-seconds', type=float, default=0,
                        help='Pace the sustained phase over this many seconds; zero runs at full speed')
    parser.add_argument('--progress', type=Path, help='Private atomic progress file for a supervised lab run')
    parser.add_argument('--varied', action='store_true', help='Vary batch sizes and include bounded writer locks during pacing')
    args = parser.parse_args()
    assert os.getuid() == 0 and 512 <= args.events <= 8000
    assert 0 <= args.duration_seconds <= 14400
    assert subprocess.run(['systemctl', 'is-active', '--quiet', 'hids-m3.service']).returncode != 0
    assert shutil.disk_usage(STATE).free >= 256 * 1024 * 1024
    fixture = args.fixture.read_bytes()
    assert fixture.startswith(b'type=SYSCALL ') and fixture.endswith(b':\n')
    lines = fixture.splitlines()
    lines[-1] += b' '
    fixture = b'\n'.join(lines) + b'\n'
    position_limit = max(1024, len(lines) * args.events + 100)
    assert position_limit <= 65536
    config = Path('/etc/hids/m3.json')
    original = config.read_bytes()
    settings = json.loads(original)
    settings.update(position_limit=position_limit, max_pages=8192)
    backup = Path(tempfile.mkdtemp(prefix='hids-m3-load.', dir='/run')) / 'config.json'
    backup.write_bytes(original)
    backup.chmod(0o600)
    reader = None
    activation = None
    report = {'fixture_events': args.events, 'pressure_locks': 32, 'lock_seconds_each': .4,
              'requested_duration_seconds': args.duration_seconds}
    try:
        config.write_text(json.dumps(settings) + '\n')
        subprocess.run(['systemctl', 'start', 'hids-m3.socket'], check=True)
        activation = str(uuid.uuid4())
        control('activate', activation)
        reader = Reader()
        until(lambda: control('status')['source_ready'])
        reader.send(lines[0].replace(b':100)', b':900000)') + b'\n')
        until(lambda: query(activation, 'SELECT scanned FROM m3_cursor')[0][0] > 0)
        started = time.monotonic()
        blocker = sqlite3.connect(STATE / f'{activation}.sqlite', isolation_level=None, timeout=1)
        try:
            for index in range(32):
                blocker.execute('BEGIN IMMEDIATE')
                try:
                    reader.send(fixture.replace(b':100)', f':{900001+index})'.encode()))
                    time.sleep(.4)
                finally:
                    blocker.rollback()
                until(lambda: query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(index+1,)])
        finally:
            blocker.close()
        report['pressure_wall_seconds'] = round(time.monotonic()-started, 3)
        assert report['pressure_wall_seconds'] > 10
        status = control('status')
        assert status['source_ready'] and status['event_health']['timeouts'] == 0
        reader.send(lines[-1].replace(b':100)', b':900000)') + b'\n')
        until(lambda: query(activation, "SELECT state FROM m3_disposition WHERE identity LIKE '%:900000'") == [('rejected',)])
        assert query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(32,)]
        assert control('status')['event_health']['timeouts'] == 0
        control('deactivate', activation)
        reader.close()
        reader = None
        print('PASS: incomplete A survived over ten wall seconds of bounded writer pressure while 32 independent B executions committed', flush=True)

        activation = str(uuid.uuid4())
        control('activate', activation)
        reader = Reader()
        until(lambda: control('status')['source_ready'])
        backend = int(subprocess.check_output(['systemctl', 'show', 'hids-m3.service', '-p', 'MainPID', '--value']))
        samples = []
        cpu_before={'backend':usage(backend)['CpuSeconds'],'collector':usage(reader.process.pid)['CpuSeconds']}
        rates = []
        started = time.monotonic()
        first=0;batch=0;last_sample=started;extra_locks=0
        while first<args.events:
            size=(16,64,128,32)[batch%4] if args.varied else 64
            end = min(first+size, args.events)
            batch_start = time.monotonic()
            if args.varied and batch%8==0:
                blocker=sqlite3.connect(STATE/f'{activation}.sqlite',isolation_level=None,timeout=1)
                try:
                    blocker.execute('BEGIN IMMEDIATE')
                    reader.send(fixture.replace(b':100)',f':{10000+first})'.encode()))
                    time.sleep(.4);extra_locks+=1
                finally:blocker.rollback();blocker.close()
                start_remaining=first+1
            else:start_remaining=first
            reader.send(b''.join(fixture.replace(b':100)', f':{10000+index})'.encode())
                                 for index in range(start_remaining, end)))
            until(lambda: query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(end,)], timeout=30)
            rates.append((end-first)/(time.monotonic()-batch_start))
            if end == 64 or end % 512 == 0 or end == args.events:
                samples.append({'events': end, 'collector': usage(reader.process.pid), 'backend': usage(backend)})
            deadline = started + args.duration_seconds * end / args.events
            while time.monotonic() < deadline:
                assert reader.process.poll() is None
                if time.monotonic()-last_sample>=60:
                    status=control('status');assert status['source_ready'] and status['failure'] is None
                    samples.append(dict(events=end,elapsed_seconds=round(time.monotonic()-started,3),
                        collector=usage(reader.process.pid),backend=usage(backend),storage=status['storage']))
                    if args.progress:
                        with tempfile.NamedTemporaryFile(dir=args.progress.parent,delete=False) as progress:
                            progress.write((json.dumps(dict(status='running',sample=samples[-1]))+'\n').encode())
                            progress.flush();os.fsync(progress.fileno());os.fchmod(progress.fileno(),0o600)
                            os.replace(progress.name,args.progress)
                    last_sample=time.monotonic()
                time.sleep(max(0, min(1, deadline-time.monotonic())))
            if end % 512 == 0:
                print(f'Load checkpoint: {end} committed executions', flush=True)
            first=end;batch+=1
        elapsed = time.monotonic()-started
        expected = {f'1794096000.123:{10000+index}' for index in range(args.events)}
        assert {row[0] for row in query(activation, 'SELECT identity FROM m3_execution')} == expected
        assert query(activation, 'SELECT COUNT(*) FROM m3_positions') == [(len(lines)*args.events,)]
        scanned, frontier = query(activation, 'SELECT scanned,frontier FROM m3_cursor')[0]
        assert scanned == frontier
        assert control('status')['event_health'] == {'timeouts': 0, 'late_records': 0, 'resource_incidents': 0, 'discarding': 0, 'rejected_groups': 0, 'rejection_details': 0, 'observed_executions': args.events}
        page_count = query(activation, 'PRAGMA page_count')[0][0]
        page_size = query(activation, 'PRAGMA page_size')[0][0]
        report.update(seconds=round(elapsed, 3), events_per_second=round(args.events/elapsed, 2),
                      first_batch_events_per_second=round(rates[0], 2), last_batch_events_per_second=round(rates[-1], 2),
                      cpu_seconds={name:round(usage(pid)['CpuSeconds']-cpu_before[name],3) for name,pid in
                          (('backend',backend),('collector',reader.process.pid))},
                      varied=args.varied, extra_writer_locks=extra_locks, samples=samples, database_pages=page_count, page_size=page_size,
                      source_bytes=scanned, position_limit=position_limit)
        report_path=backup.parent/'report.json'
        report_path.write_text(json.dumps(report,sort_keys=True)+'\n');report_path.chmod(0o600)
        print(json.dumps({key:report[key] for key in ('fixture_events','seconds','events_per_second','database_pages','varied','extra_writer_locks')},sort_keys=True),flush=True)
        print('Private full load report: '+str(report_path),flush=True)
        print('PASS: sustained installed-runtime delivery, exact identities, resolved frontier and zero timeout/late dispositions', flush=True)
    finally:
        if activation is not None:
            try:
                control('deactivate', activation)
            except Exception:
                pass
        if reader is not None:
            reader.close()
        subprocess.run(['systemctl', 'stop', 'hids-m3.socket', 'hids-m3.service'], check=True)
        config.write_bytes(original)
        assert config.read_bytes() == original
        print('Restored HIDS budgets; retained test history and private backup '+str(backup), flush=True)


if __name__ == '__main__':
    main()
