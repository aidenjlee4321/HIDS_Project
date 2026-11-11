"""Explicit root-only installed health-checker acceptance on the isolated M3 VM.

Changes only HIDS test units/state plus a protected, restored derived auditd state
report. Audit rules and logging configuration are never changed by this harness.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import sqlite3
import subprocess
import tempfile
import time
import uuid

from m3_runtime_ubuntu_acceptance import Reader, STATE, control, query, until


def run(*arguments, check=True):
    return subprocess.run(arguments, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)


def sample(check=True):
    # Explicit lab samples intentionally run faster than the production timer.
    # Clear only this test unit's operator start-rate state; do not weaken the
    # installed unit's rate limits or hide the returned sample exit status.
    reset=run('systemctl', 'reset-failed', 'hids-m3-health.service', check=False)
    if reset.returncode and b'not loaded' not in reset.stderr:
        reset.check_returncode()
    return run('systemctl', 'start', 'hids-m3-health.service', check=check)


def message(value):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect('/run/hids/m3/health/metrics.sock')
        connection.sendall(json.dumps(value).encode()+b'\n')
        output=bytearray()
        while not output.endswith(b'\n') and len(output)<2048:
            chunk=connection.recv(2048)
            if not chunk: break
            output.extend(chunk)
        return json.loads(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--isolation-probe', type=Path, required=True,
                        help='Root-owned test binary already installed under /usr/lib/hids')
    args=parser.parse_args()
    assert os.getuid()==0
    assert args.isolation_probe.parent==Path('/usr/lib/hids')
    assert args.isolation_probe.stat().st_uid==0 and args.isolation_probe.stat().st_mode&0o022==0
    configuration=Path('/etc/audit/auditd.conf')
    original_configuration=configuration.read_bytes()
    assert any(line.strip()==b'report_interval = 0' for line in original_configuration.splitlines())
    assert run('auditctl','-l').stdout.strip()==b'No rules'
    workspace=Path(tempfile.mkdtemp(prefix='hids-m3-health.',dir='/run'))
    report_path=Path('/run/audit/auditd.state')
    backup=workspace/'auditd.state'
    previous_exists=os.path.lexists(report_path)
    if previous_exists:
        assert report_path.is_file() and not report_path.is_symlink()
        os.rename(report_path,backup)
    fixture=args.fixture.read_bytes()
    lines=fixture.splitlines()
    assert fixture.endswith(b':\n')
    lines[-1]+=b' '
    fixture=b'\n'.join(lines)+b'\n'
    reader=None
    activation=None
    trigger=False
    probe_unit=Path('/etc/systemd/system/hids-m3-health-isolation.service')
    assert not probe_unit.exists()
    try:
        run('systemctl','start','hids-m3.socket')
        control('status')  # Trigger socket activation before using the backend-owned health socket.
        assert message(dict(version=3,command='scope'))['result']=='inactive'
        activation=str(uuid.uuid4())
        control('activate',activation)
        reader=Reader()
        until(lambda:control('status')['source_ready'])
        reader.send(fixture)
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        until(lambda:control('status')['upstream_loss']['kernel']=='sampled', timeout=12)
        current=control('status')
        assert current['upstream_health']['observation']['dispatcher']['state']=='missing'
        assert current['upstream_health']['observation']['kernel']['auditd_pid']>0
        print('PASS: automatic isolated checker reports real host kernel counters; missing dispatcher evidence remains unknown',flush=True)
        run('systemctl','stop','hids-m3-health.timer')
        rejected=message(dict(version=3,command='activate',source=current['source'],activation=str(uuid.uuid4())))
        assert rejected['result']=='rejected' and control('status')['interval']['activation']==activation
        nobody=pwd.getpwnam('hids-audit')
        denial="""import socket
s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect('/run/hids/m3/health/metrics.sock')
try: assert s.recv(1)==b''
except ConnectionResetError: pass
"""
        run('setpriv','--reuid',str(nobody.pw_uid),'--regid',str(nobody.pw_gid),
            '--groups','hids-ipc','--no-new-privs','python3','-B','-c',denial)
        print('PASS: event reader denied health endpoint; health endpoint cannot change activation',flush=True)

        # The operator requests one derived state report. The product checker never
        # signals auditd and never changes report_interval or logging policy.
        run('auditctl','--signal','cont')
        until(report_path.exists)
        sample()
        current=control('status')
        assert current['upstream_loss']['dispatcher']=='inactive'
        assert current['upstream_health']['observation']['dispatcher']['state']=='observed'
        fresh_copy=workspace/'fresh.state'
        fresh_copy.write_bytes(report_path.read_bytes())
        fresh_copy.chmod(0o600)
        old=time.time_ns()-30_000_000_000
        os.utime(report_path,ns=(old,old))
        sample()
        assert control('status')['upstream_health']['observation']['dispatcher']['state']=='stale'
        assert control('status')['upstream_loss']['dispatcher']=='unknown'
        report_path.write_bytes(b'invalid metadata\n')
        sample()
        assert control('status')['upstream_health']['observation']['dispatcher']['state']=='invalid'
        report_path.unlink()
        report_path.symlink_to(fresh_copy)
        sample()
        assert control('status')['upstream_health']['observation']['dispatcher']['state']=='invalid'
        report_path.unlink()
        report_path.write_bytes(fresh_copy.read_bytes())
        report_path.chmod(0o640)
        print('PASS: actual fresh/inactive report, stale report, malformed report and symlink rejection',flush=True)

        snapshot=control('status')['upstream_health']['received_at']
        time.sleep(16)
        current=control('status')
        assert current['upstream_health']['freshness']=='stale' and current['upstream_loss']['kernel']=='unknown'
        reader.send(fixture.replace(b':100)',b':101)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(2,)])
        assert reader.process.poll() is None
        sample()
        assert control('status')['upstream_health']['received_at']!=snapshot
        assert control('status')['upstream_health']['summary']['incidents']['sampling_gap']
        print('PASS: missed samples become stale; recovery retains sampling gap while event ingestion continues',flush=True)

        database=sqlite3.connect(STATE/'control.sqlite',isolation_level=None)
        try:
            database.execute("CREATE TRIGGER health_acceptance_fault BEFORE INSERT ON m3_health BEGIN SELECT RAISE(ABORT,'test'); END")
            trigger=True
            assert sample(check=False).returncode!=0
            current=control('status')
            assert current['health_reporting_error']=='health_storage_failure' and current['failure'] is None
            assert current['source_ready']
            reader.send(fixture.replace(b':100)',b':102)'))
            until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(3,)])
        finally:
            if trigger:
                database.execute('DROP TRIGGER health_acceptance_fault')
                trigger=False
            database.close()
        sample()
        assert control('status')['health_reporting_error'] is None
        print('PASS: health storage fault does not stop root control or event collection; checker recovers',flush=True)

        production=Path('/etc/systemd/system/hids-m3-health.service').read_text()
        capture=workspace/'isolation.json'
        probe_unit.write_text(production.replace('ExecStart=/usr/lib/hids/hids-m3-health',f'ExecStart={args.isolation_probe}')
                                      .replace('StandardOutput=null',f'StandardOutput=file:{capture}'))
        run('systemctl','daemon-reload')
        run('systemctl','start',probe_unit.name)
        proof=json.loads(capture.read_text())
        for key,value in proof.items():
            if key.startswith('Cap'):
                assert int(value,16)==1<<30
            elif key=='NoNewPrivs:':
                assert int(value)==1
            else:
                assert value is True, (key,value)
        print('PASS: actual unit hides administrative/event IPC and state, denies internet/filesystem writes/exec/signals, and retains only Audit-control capability',flush=True)
        control('deactivate',activation)
        reader.close();reader=None
        current=control('status')
        assert current['upstream_health']['freshness']=='historical'
        assert current['upstream_loss']['kernel']=='unknown'
        run('systemctl','restart','hids-m3.service')
        assert control('status')['upstream_health']['summary']['incidents']['sampling_gap']
        assert message(dict(version=3,command='scope'))['result']=='inactive'
        print('PASS: durable health incidents survive revocation/restart without restarting collection',flush=True)
        run('systemctl','stop','hids-m3.socket','hids-m3.service')
        assert run('systemctl','is-active','--quiet','hids-m3-health.timer',check=False).returncode != 0
        assert run('systemctl','is-active','--quiet','hids-m3-health.service',check=False).returncode != 0
        print('PASS: checker and timer stop with the M3 service',flush=True)
    finally:
        if activation is not None:
            try: control('deactivate',activation)
            except Exception: pass
        if reader is not None: reader.close()
        run('systemctl','stop','hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service',check=False)
        probe_unit.unlink(missing_ok=True)
        run('systemctl','daemon-reload')
        if os.path.lexists(report_path): report_path.unlink()
        if previous_exists: os.rename(backup,report_path)
        assert configuration.read_bytes()==original_configuration
        assert run('auditctl','-l').stdout.strip()==b'No rules'
        assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
        print('Restored derived Audit report; logging configuration/rules unchanged; M3 and checker stopped. Evidence '+str(workspace),flush=True)


if __name__=='__main__':
    main()
