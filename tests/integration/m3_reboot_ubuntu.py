"""Explicit root-only two-phase real-reboot M3 acceptance.

Prepare retains an interrupted lab stream and private manifest. Reboot is a
separate operator action. Verify preserves all event history and restores stopped
HIDS units. No Audit configuration, rules or plugins are changed.
"""
import argparse
import hashlib
import json
import os
import pwd
import grp
import stat
from pathlib import Path
import signal
import subprocess
import tempfile
import uuid
from m3_runtime_ubuntu_acceptance import Reader, STATE, control, query, until

BOOT = Path('/proc/sys/kernel/random/boot_id')
UNITS = ('hids-m3.socket', 'hids-m3.service', 'hids-m3-health.timer', 'hids-m3-health.service')


def run(*arguments):
    return subprocess.run(arguments, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)


def host_policy():
    files = [Path('/etc/audit/auditd.conf'), *sorted(Path('/etc/audit/plugins.d').glob('*.conf'))]
    return dict(files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                rules=run('auditctl', '-l').stdout.decode())


def prepare():
    run('systemctl', 'stop', *UNITS)
    run('systemctl', 'start', 'hids-m3.socket')
    activation = str(uuid.uuid4())
    control('activate', activation)
    reader = Reader()
    directory = Path(tempfile.mkdtemp(prefix='hids-m3-reboot.', dir='/root'))
    manifest = directory / 'manifest.json'
    try:
        until(lambda:control('status')['source_ready'])
        lines = Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines()
        lines[-1] += b' '
        reader.send(lines[0].replace(b':100)', b':810001)')+b'\n')
        reader.send((b'\n'.join(lines)+b'\n').replace(b':100)', b':810002)'))
        until(lambda:query(activation, 'SELECT COUNT(*) FROM m3_execution') == [(1,)])
        until(lambda:bool(control('status')['upstream_health']), timeout=10)
        current = control('status')
        assert query(activation, 'SELECT scanned>frontier FROM m3_cursor') == [(1,)]
        assert current['upstream_health']['freshness'] == 'fresh'
        assert current['upstream_health']['observation']['kernel']['boot_id'] == BOOT.read_text().strip()
        evidence = dict(activation=activation, generation=current['interval']['generation'],
                        lease=current['interval']['lease'], boot_id=BOOT.read_text().strip(),
                        source=current['source'], policy=host_policy(),
                        health_received=current['upstream_health']['received_at'])
        manifest.write_text(json.dumps(evidence)+'\n');manifest.chmod(0o600)
        backend = int(run('systemctl', 'show', 'hids-m3.service', '-p', 'MainPID', '--value').stdout)
        os.kill(backend, signal.SIGKILL)
        until(lambda:subprocess.run(['systemctl','is-active','--quiet','hids-m3.service']).returncode != 0)
        run('systemctl', 'stop', *UNITS)
        assert query(activation, "SELECT state FROM m3_disposition WHERE identity='1794096000.123:810001'") == [('open',)]
        print('PREPARED: '+str(manifest), flush=True)
    finally: reader.close()


def verify(manifest):
    evidence = json.loads(manifest.read_text())
    assert BOOT.read_text().strip() != evidence['boot_id'], 'a real reboot is required'
    assert host_policy() == evidence['policy'], 'Audit policy changed across reboot'
    assert run('systemctl', 'is-active', 'auditd').stdout.strip() == b'active'
    # Check before opening the control socket or running any manual tmpfiles
    # creation: these directories must already have been provisioned at boot.
    ingest = pwd.getpwnam('hids-ingest')
    ipc = grp.getgrnam('hids-ipc').gr_gid
    for name in ('ingest', 'health'):
        info = (Path('/run/hids/m3') / name).lstat()
        assert stat.S_ISDIR(info.st_mode)
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (ingest.pw_uid, ipc, 0o750)
    assert Path('/usr/lib/tmpfiles.d/hids-m3.conf').read_bytes() == Path('packaging/systemd/hids-m3.tmpfiles.conf').read_bytes()
    print('PASS: boot automatically provisions private HIDS runtime directories', flush=True)
    run('systemctl', 'start', 'hids-m3.socket')
    reader = None
    fresh = None
    try:
        status = control('status')
        assert status['source'] == evidence['source']
        assert status['interval']['activation'] == evidence['activation']
        assert status['interval']['generation'] == evidence['generation']
        assert status['interval']['state'] == 'interrupted'
        assert status['interval']['code'] == 'backend_restart'
        assert not status['source_ready'] and status['possible_gap']
        assert status['upstream_loss'] == dict(kernel='unknown', dispatcher='unknown')
        assert status['upstream_health']['freshness'] == 'historical'
        assert status['upstream_health']['received_at'] == evidence['health_received']
        # Ended observations cannot prove a shared monotonic epoch, even if a
        # later boot has a larger uptime. Historical age must remain unknown.
        assert status['upstream_health']['age_ns'] is None
        activation = evidence['activation']
        assert query(activation, "SELECT identity FROM m3_execution") == [('1794096000.123:810002',)]
        assert query(activation, "SELECT state FROM m3_disposition WHERE identity='1794096000.123:810001'") == [('interrupted',)]
        assert query(activation, 'SELECT scanned=frontier FROM m3_cursor') == [(1,)]
        denied = Reader(b'not authorized\n')
        try: assert denied.process.wait(timeout=5) != 0
        finally: denied.close()
        print('PASS: actual reboot preserves B, interrupts A, retains historical health and refuses automatic source activation', flush=True)
        fresh = str(uuid.uuid4())
        control('activate', fresh)
        status = control('status')
        assert status['interval']['generation'] != evidence['generation']
        assert status['interval']['lease'] != evidence['lease']
        reader = Reader()
        until(lambda:control('status')['source_ready'])
        lines = Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines()
        lines[-1] += b' '
        reader.send((b'\n'.join(lines)+b'\n').replace(b':100)', b':810003)'))
        until(lambda:query(fresh, 'SELECT COUNT(*) FROM m3_execution') == [(1,)])
        until(lambda:bool(control('status')['upstream_health']), timeout=10)
        current = control('status')
        assert current['upstream_health']['freshness'] == 'fresh'
        assert current['upstream_health']['observation']['kernel']['boot_id'] == BOOT.read_text().strip()
        assert query(activation, "SELECT identity FROM m3_execution") == [('1794096000.123:810002',)]
        assert host_policy() == evidence['policy']
        print('PASS: fresh explicit authorization uses new generation/lease, collects C and samples the new kernel boot without modifying prior evidence', flush=True)
        result = dict(previous_boot=evidence['boot_id'], current_boot=BOOT.read_text().strip(),
                      previous_activation=activation, new_activation=fresh, passed=True)
        output = manifest.with_name('result.json')
        output.write_text(json.dumps(result)+'\n');output.chmod(0o600)
        print('RETAINED: '+str(output), flush=True)
    finally:
        if fresh:
            try: control('deactivate', fresh)
            except Exception: pass
        if reader: reader.close()
        run('systemctl', 'stop', *UNITS)


def main():
    assert os.getuid() == 0
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'verify'))
    parser.add_argument('manifest', nargs='?', type=Path)
    args = parser.parse_args()
    if args.phase == 'prepare': prepare()
    else:
        assert args.manifest is not None
        verify(args.manifest)


if __name__ == '__main__': main()
