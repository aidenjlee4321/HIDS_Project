"""Temporary acceptance probes: no journal API and no SQLite writer.

The proxy forwards one SSH TCP stream without retaining its contents. All DB
operations use production read-only connections. Replay uses one stored envelope.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
DB = Path('/var/lib/hids/m2/journal.sqlite')


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def proxy(target):
    require(os.getuid() == os.geteuid() != 0, 'ordinary-user SSH proxy required')
    started = time.monotonic_ns() // 1000
    with socket.create_connection(('127.0.0.1', 22), timeout=5) as sock:
        metadata = dict(address='127.0.0.1', server_port=22, port=sock.getsockname()[1],
                        started_monotonic_us=started,
                        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-', ''))
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(metadata, f); f.write('\n')
        deadline = time.monotonic()+15
        inputs = [0, sock]
        while time.monotonic() < deadline:
            ready, _, _ = select.select(inputs, [], [], max(0, min(1, deadline-time.monotonic())))
            for item in ready:
                data = os.read(0, 32768) if item == 0 else sock.recv(32768)
                if not data:
                    if item != 0:
                        return
                    inputs.remove(0); sock.shutdown(socket.SHUT_WR)
                elif item == 0:
                    sock.sendall(data)
                else:
                    view = memoryview(data)
                    while view:
                        n = os.write(1, view)
                        require(n > 0, 'SSH stdout closed')
                        view = view[n:]
        raise RuntimeError('SSH proxy deadline exceeded')


def initialize():
    # Trusted, root-owned code copy supplied by the acceptance resource helper.
    sys.path.insert(0, str(BASE/'code'))
    global CFG, contract, receiver, store_module, m1_store, m1_security, m1_contract
    from engine.ingestion import m2_contract as contract, m2_receiver as receiver
    from engine.ingestion import m1_security, m1_contract
    from engine.ingestion.m2_service import load_config
    from engine.database import m2_store as store_module, m1_store
    CFG = load_config(BASE/'m2.json')


def identity(role):
    policy = receiver.service_policy(role)
    fields = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('Uid', 'Gid', 'Groups', 'CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd', 'NoNewPrivs'):
            fields[key] = value.split()
    require(list(map(int, fields['Uid'])) == [os.getuid()]*4, 'UID mismatch')
    require(list(map(int, fields['Gid'])) == [os.getgid()]*4, 'GID mismatch')
    require(all(int(fields[k][0], 16) == 0 for k in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd')),
            'unexpected service capabilities')
    require(fields['NoNewPrivs'] == ['1'], 'NoNewPrivs required')
    return policy


def root_control(*args, timeout=6):
    require(os.getuid() == os.geteuid() == 0, 'root control probe required')
    p = subprocess.run(['/usr/bin/python3', '-B', '-m', 'engine.ingestion.m2_control',
                        *args, '--config', str(BASE/'m2.json')], cwd=BASE/'code',
                       env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'},
                       capture_output=True, timeout=timeout)
    require(p.returncode == 0 and len(p.stdout) <= 2049 and p.stdout.endswith(b'\n'),
            'production root control failed/unconfirmed')
    return contract.decode(p.stdout[:-1], 2048)


def unit_pid(unit):
    require(unit in ('hids-ingest.service', 'hids-journal.service'), 'unexpected unit')
    p = subprocess.run(['systemctl', 'show', unit, '-p', 'MainPID', '--value'],
                       capture_output=True, text=True, timeout=3, check=True)
    return int(p.stdout.strip())


def wait_status(state, reader):
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        value = root_control('status', timeout=min(6, max(.1, deadline-time.monotonic())))
        require(value['failure'] is None, 'ingestion reports failure')
        require(value['source_id'] == CFG['source_id'], 'status source')
        states = ('anchored', 'empty_unanchored') if state == 'running' else (state,)
        pid = unit_pid('hids-journal.service')
        ready = (value['state'] in states and
                 ((reader == 'none' and not value['reader_connected'] and pid == 0) or
                  (reader == 'unit' and pid > 0 and value['reader_connected'] and value['reader_pid'] == pid)))
        if ready:
            print(json.dumps(value, sort_keys=True)); return
        time.sleep(.1)
    raise RuntimeError('status readiness deadline exceeded')


def wait_exit():
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        p = subprocess.run(['systemctl', 'show', 'hids-journal.service',
                            '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus',
                            '-p', 'ExecMainCode'], capture_output=True, text=True, timeout=3, check=True)
        info = dict(line.split('=', 1) for line in p.stdout.splitlines())
        # MainPID can become zero while ExecStopPost is still running.
        require(info['ActiveState'] != 'failed', 'reader unit failed')
        if info['MainPID'] == '0' and info['ActiveState'] == 'inactive':
            require(info['ActiveState'] == 'inactive' and info['Result'] == 'success' and
                    info['ExecMainStatus'] == '0', 'reader did not exit cleanly')
            marker = latest_exit('reader')
            require((marker['result'], marker['exit_code'], marker['exit_status']) ==
                    ('success', 'exited', '0'), 'reader stop hook did not record exit 0')
            print(json.dumps(dict(unit=info, exit_marker=marker))); return
        time.sleep(.1)
    raise RuntimeError('reader exit deadline exceeded')


def latest_exit(role):
    require(os.getuid() == 0 and role in ('reader', 'ingest'), 'root exit evidence reader required')
    path = Path('/var/lib')/BASE.name/(role+'.stderr')
    with path.open('rb') as f:
        raw = f.read(1024*1024+1)
    require(len(raw) <= 1024*1024, 'exit diagnostic bound')
    prefix = b'M2_ACCEPTANCE_EXIT '
    markers = [json.loads(line[len(prefix):]) for line in raw.splitlines() if line.startswith(prefix)]
    require(markers and markers[-1]['role'] == role, 'missing exit marker')
    return markers[-1]


def record_exit(role):
    import pwd
    require(role in ('reader', 'ingest'), 'exit role')
    who = pwd.getpwnam('hids-journal' if role == 'reader' else 'hids-ingest')
    require(os.getuid() == os.geteuid() == who.pw_uid and os.getgid() == os.getegid() == who.pw_gid,
            'exit recorder service identity')
    marker = dict(role=role, uid=os.getuid(), gid=os.getgid(),
                  result=os.environ.get('SERVICE_RESULT'), exit_code=os.environ.get('EXIT_CODE'),
                  exit_status=os.environ.get('EXIT_STATUS'), invocation=os.environ.get('INVOCATION_ID'),
                  observed_monotonic_ns=time.monotonic_ns())
    require(all(marker[k] is not None for k in ('result', 'exit_code', 'exit_status', 'invocation')),
            'missing manager exit metadata')
    print('M2_ACCEPTANCE_EXIT '+json.dumps(marker, sort_keys=True), file=sys.stderr, flush=True)


def runtime_credentials(include_reader=True):
    import grp
    import pwd
    identities = (
        ('hids-ingest.service', 'hids-ingest', ('hids-ipc',)),
        ('hids-journal.service', 'hids-journal', ('hids-ipc', 'systemd-journal')))
    for unit, account, extra in identities if include_reader else identities[:1]:
        pid = unit_pid(unit); require(pid > 0, 'missing service process')
        who = pwd.getpwnam(account); values = {}
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            key, _, value = line.partition(':'); values[key] = value.split()
        require(list(map(int, values['Uid'])) == [who.pw_uid]*4, 'runtime UID')
        require(list(map(int, values['Gid'])) == [who.pw_gid]*4, 'runtime GID')
        expected = {who.pw_gid} | {grp.getgrnam(g).gr_gid for g in extra}
        require(set(map(int, values['Groups'])) | {who.pw_gid} == expected, 'runtime groups')
        require(all(int(values[k][0], 16) == 0 for k in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd')), 'runtime capabilities')
        require(values['NoNewPrivs'] == ['1'], 'runtime NoNewPrivs')
        print(json.dumps(dict(unit=unit, pid=pid, uid=who.pw_uid, gid=who.pw_gid, groups=sorted(expected))))
        if account == 'hids-ingest':
            env = dict(x.split(b'=', 1) for x in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in x)
            require(env.get(b'LISTEN_PID') == str(pid).encode() and env.get(b'LISTEN_FDS') == b'1', 'actual socket activation environment')
            require(os.readlink(f'/proc/{pid}/fd/3').startswith('socket:['), 'FD 3 missing')
    for name, uid, gid, mode in (
        ('/run/hids', 0, 0, 0o755),
        ('/run/hids/control.sock', 0, 0, 0o600),
        ('/run/hids/ingest', pwd.getpwnam('hids-ingest').pw_uid, grp.getgrnam('hids-ipc').gr_gid, 0o750),
        ('/var/lib/hids/m2', pwd.getpwnam('hids-ingest').pw_uid, pwd.getpwnam('hids-ingest').pw_gid, 0o700),
        ('/run/hids/ingest/journal.sock', pwd.getpwnam('hids-ingest').pw_uid, grp.getgrnam('hids-ipc').gr_gid, 0o660)):
        p = Path(name); s = p.lstat()
        require(p.resolve() == p and (s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) == (uid, gid, mode), 'runtime path metadata')
        require(stat.S_ISSOCK(s.st_mode) if name.endswith('.sock') else stat.S_ISDIR(s.st_mode), 'runtime path type')
        print(json.dumps(dict(path=name, uid=s.st_uid, gid=s.st_gid, mode=oct(stat.S_IMODE(s.st_mode)))))
    print('Runtime identities, socket metadata, and actual FD-3 inheritance verified')


def bounded(db, sql, cap):
    rows = db.execute(sql).fetchmany(cap+1)
    require(len(rows) <= cap, 'acceptance retrieval bound exceeded')
    return rows


def snapshot():
    identity('ingest')
    m1_security.private_directory(DB.parent)
    m1_security.private_file(DB)
    m1_store.check_sidecars(DB)
    for path in (DB, Path(str(DB)+'-wal'), Path(str(DB)+'-shm')):
        if path.exists():
            info = path.lstat()
            require(info.st_gid == os.getgid() and stat.S_IMODE(info.st_mode) == 0o600,
                    'database/sidecar group or mode')
    with contextlib.closing(m1_store.connect(DB, reader=True)) as db:
        m1_store.profile(db, reader=True)
        db.execute('BEGIN')
        try:
            store_module.Store.schema(db)
            tables = {
                'dispositions': bounded(db, 'SELECT * FROM dispositions ORDER BY revision', min(CFG['max_records'], 1000)),
                'progress': bounded(db, 'SELECT * FROM progress ORDER BY source', 1),
                'activations': bounded(db, 'SELECT * FROM activations ORDER BY activation', 100),
            }
            gaps = bounded(db, 'SELECT * FROM gaps ORDER BY id', 1000)
            page_size = db.execute('PRAGMA page_size').fetchone()[0]
            page_count = db.execute('PRAGMA page_count').fetchone()[0]
        finally:
            db.execute('ROLLBACK')
    events = []
    for row in tables['dispositions']:
        identifier, source, cursor, kind, stable, envelope, revision, received, stored = row
        event = contract.validate_event(contract.decode(envelope.encode('ascii')))
        require(source == CFG['source_id'] == event['source_id'] and cursor == event['cursor'], 'stored provenance')
        require(identifier == event['event_id'] == contract.event_id(source, cursor), 'cursor identity')
        require(kind == event['message_type'] and stable == contract.canonical(event), 'stored native content')
        require(type(revision) is int and revision == event['expected_revision']+1, 'stored revision')
        m1_contract.timestamp(received); m1_contract.timestamp(stored)
        if kind == 'journal_event':
            require(store_module.get_event(DB, identifier) == event, 'independent fresh read-only retrieval')
            events.append((row, event))
    p = tables['progress']
    if p:
        require(p[0][0] == CFG['source_id'], 'checkpoint source')
        if tables['dispositions']:
            last = tables['dispositions'][-1]
            require((p[0][4], p[0][5]) == (last[6], last[2]), 'checkpoint/record alignment')
    else:
        require(not tables['dispositions'], 'events without checkpoint')
    return tables, gaps, events, page_size, page_count


def correlate(baseline, connection):
    require(type(baseline) is int and baseline >= 0, 'baseline')
    meta = json.loads(connection)
    require(set(meta) == {'address', 'server_port', 'port', 'started_monotonic_us', 'boot_id'} and
            meta['address'] == '127.0.0.1' and meta['server_port'] == 22 and
            type(meta['port']) is int and 1 <= meta['port'] <= 65535 and
            type(meta['started_monotonic_us']) is int and meta['started_monotonic_us'] > 0 and
            re.fullmatch('[0-9a-f]{32}', meta['boot_id']), 'connection metadata')
    tables, gaps, events, size, pages = snapshot()
    require(len(tables['progress']) == 1, 'missing activation')
    activation = tables['progress'][0][1]
    pattern = re.compile(r'(?<![0-9.])127\.0\.0\.1 port '+str(meta['port'])+r'\b')
    selected = [(row, event) for row, event in events if row[6] > baseline and
                event['activation_id'] == activation and event['journal']['boot_id'] == meta['boot_id'] and
                meta['started_monotonic_us'] <= int(event['journal']['monotonic_us']) <= time.monotonic_ns()//1000 and
                pattern.search(event['fields']['MESSAGE'])]
    return selected


def receive(sock):
    raw = bytearray()
    while True:
        byte = sock.recv(1)
        if not byte: raise EOFError('peer closed before complete response')
        if byte == b'\n': return contract.decode(bytes(raw), 2048)
        require(len(raw) < 2048, 'response accumulator bound')
        raw.extend(byte)


def reader_channel():
    peer, ipc = identity('reader')
    path = Path('/run/hids/ingest/journal.sock')
    s = path.lstat()
    require(stat.S_ISSOCK(s.st_mode) and path.resolve() == path and
            (s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) == (peer.uid, ipc, 0o660), 'data socket')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sock.settimeout(5)
    try:
        sock.connect(str(path)); pid = peer.check(sock)
        return sock, pid
    except BaseException:
        sock.close(); raise


def reconcile(value, event):
    m1_contract.keys(value, 'protocol_version message_type source_id activation_id state revision cursor boundary_start boundary_end')
    m1_contract.integer(value['protocol_version'], 2, 2)
    require(value['message_type'] == 'progress' and value['source_id'] == event['source_id'] and
            value['activation_id'] == event['activation_id'] and value['state'] == 'anchored', 'reconcile identity/state')
    require(m1_contract.uuid_valid(value['source_id']) and m1_contract.uuid_valid(value['activation_id']), 'reconcile UUIDs')
    m1_contract.integer(value['revision'], 1, contract.MAX_REVISION)
    require(value['revision'] >= event['expected_revision']+1, 'reconcile revision')
    contract.event_id(value['source_id'], value['cursor'])
    m1_contract.timestamp(value['boundary_start']); m1_contract.timestamp(value['boundary_end'])


def replay(path):
    identity('reader')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == 0 and
                s.st_gid == os.getgid() and stat.S_IMODE(s.st_mode) == 0o640, 'replay file policy')
        raw = f.read(65538)
    require(len(raw) <= 65537 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'immutable replay frame')
    event = contract.validate_event(contract.decode(raw[:-1]))
    require(event['source_id'] == CFG['source_id'] and event['message_type'] == 'journal_event', 'replay source')
    sock, pid = reader_channel()
    with sock:
        sock.sendall(contract.frame({'protocol_version': 2, 'message_type': 'reconcile'}, 2048))
        reconcile(receive(sock), event)
        sock.sendall(raw)
        ack = contract.validate_response(receive(sock), event['event_id'])
        require(ack['message_type'] == 'ack' and ack['result'] == 'duplicate' and
                ack['checkpoint_revision'] == event['expected_revision']+1, 'duplicate receipt')
        print(json.dumps(dict(result='duplicate', checkpoint_revision=ack['checkpoint_revision'],
                              server_pid=pid, replay_pid=os.getpid())))


def main():
    action, *args = sys.argv[1:]
    if action == 'proxy':
        proxy(*args); return
    if action == 'record-exit':
        record_exit(*args); return
    initialize()
    if action == 'wait': wait_status(*args)
    elif action == 'exit-ok': wait_exit()
    elif action == 'crash-ok':
        require(os.getuid() == 0, 'root crash evidence probe')
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            state = subprocess.run(['systemctl', 'show', 'hids-journal.service', '-p', 'ActiveState', '--value'],
                                   capture_output=True, text=True, timeout=3, check=True).stdout.strip()
            if state == 'failed':
                value = latest_exit('reader')
                require((value['result'], value['exit_code'], value['exit_status']) ==
                        ('signal', 'killed', 'KILL'), 'unexpected crash outcome')
                print(json.dumps(value)); return
            time.sleep(.1)
        raise RuntimeError('reader crash exit evidence missing')
    elif action in ('runtime', 'runtime-ingest'):
        require(os.getuid() == 0, 'root metadata probe'); runtime_credentials(action == 'runtime')
    elif action == 'stopped':
        require(os.getuid() == 0, 'root metadata probe')
        for unit in ('hids-journal.service', 'hids-ingest.service'):
            require(unit_pid(unit) == 0, 'service still running')
            p = subprocess.run(['systemctl', 'show', unit, '-p', 'Result', '-p', 'ExecMainStatus',
                                '-p', 'ActiveState', '-p', 'ExecMainCode'], capture_output=True, text=True, timeout=3, check=True)
            info = dict(x.split('=', 1) for x in p.stdout.splitlines())
            require(info['Result'] == 'success' and info['ExecMainStatus'] == '0' and
                    info['ActiveState'] == 'inactive', 'unclean stop')
            role = 'reader' if unit == 'hids-journal.service' else 'ingest'
            value = latest_exit(role)
            require((value['result'], value['exit_code'], value['exit_status']) ==
                    ('success', 'exited', '0'), 'missing successful exit evidence')
        require(not os.path.lexists('/run/hids/control.sock') and
                not os.path.lexists('/run/hids/ingest/journal.sock'), 'stale endpoint')
        print('Both services exited cleanly; both sockets removed')
    elif action == 'isolation':
        role, paths = args; identity(role)
        names = json.loads(paths)
        require(names and len(names) <= 1000, 'journal metadata bound')
        access = [os.access(p, os.R_OK) for p in names]
        if role == 'reader':
            require(any(access) and not os.access(DB.parent, os.R_OK | os.X_OK), 'reader storage/journal isolation')
        else:
            require(not any(access), 'ingestion can read assessed journal files')
            m1_security.private_directory(DB.parent)
        print(json.dumps(dict(role=role, assessed_files=len(names), isolation=True)))
    elif action == 'journal-denied':
        # Post-activation only: test open permission, never read a record/byte.
        identity('ingest')
        names = json.loads(args[0])
        require(names and len(names) <= 1000, 'journal metadata bound')
        for name in names:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except PermissionError:
                continue
            else:
                os.close(fd)
                raise RuntimeError('ingestion unexpectedly opened assessed journal file')
        print(json.dumps(dict(ingestion_journal_opens_denied=len(names), payload_bytes_read=0)))
    elif action == 'replay': replay(*args)
    elif action == 'compete':
        sock, pid = reader_channel()
        with sock:
            try:
                sock.sendall(contract.frame({'protocol_version': 2, 'message_type': 'reconcile'}, 2048))
                receive(sock)
            except (EOFError, BrokenPipeError, ConnectionResetError):
                print(json.dumps(dict(second_reader_rejected=True, server_pid=pid))); return
        raise RuntimeError('second reader was not rejected')
    elif action in ('match', 'export'):
        deadline = time.monotonic()+30
        while True:
            matches = correlate(int(args[0]), args[1])
            if matches:
                row, event = matches[-1]
                if action == 'export': sys.stdout.write(row[5]+'\n')
                else: print(json.dumps(dict(event_id=row[0], revision=row[6], controlled_port_matched=True,
                                           boot_monotonic_time_matched=True, fresh_readonly_retrieval=True)))
                return
            require(action == 'match' and time.monotonic() < deadline, 'no correlated SSH event; do not broaden scope')
            time.sleep(.1)
    else:
        tables, gaps, events, size, pages = snapshot()
        p = tables['progress']
        if action == 'fingerprint':
            print(hashlib.sha256(json.dumps(tables, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        elif action == 'revision': print(p[0][4] if p else 0)
        elif action == 'state': print(json.dumps(tables, sort_keys=True, separators=(',', ':')))
        elif action == 'check-prefix':
            fd = os.open(args[0], os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as f:
                info = os.fstat(f.fileno())
                require(info.st_uid == 0 and info.st_gid == os.getgid() and
                        stat.S_IMODE(info.st_mode) == 0o640 and info.st_nlink == 1,
                        'baseline file metadata')
                raw = f.read(32*1024*1024+1)
            require(len(raw) <= 32*1024*1024, 'baseline bound')
            old = json.loads(raw)
            require(set(old) == set(tables) and old['activations'] == [list(x) for x in tables['activations']],
                    'activation changed during recovery')
            previous = {x[0]: x for x in old['dispositions']}
            current = {x[0]: list(x) for x in tables['dispositions']}
            require(all(current.get(k) == v for k, v in previous.items()), 'stored event changed/lost')
            require(len(old['progress']) == len(p) == 1, 'checkpoint cardinality')
            a, b = old['progress'][0], p[0]
            require(a[:4] == list(b[:4]) and a[6:] == list(b[6:]), 'activation/boundary changed')
            require(b[3] == 'anchored' and b[4]-a[4] == len(current)-len(previous) >= 0,
                    'checkpoint rewind or invalid advance')
            print(json.dumps(dict(recovered_same_interval=True, original_records_unchanged=True,
                                  new_dispositions=len(current)-len(previous))))
        elif action == 'summary':
            print(json.dumps(dict(dispositions=len(tables['dispositions']), events=len(events),
                                  state=p[0][3] if p else 'inactive', revision=p[0][4] if p else 0,
                                  gaps=[g[5] for g in gaps], page_size=size, page_count=pages,
                                  activity_wall_time='not_established')))
        else: raise RuntimeError('unknown probe operation')


if __name__ == '__main__':
    main()
