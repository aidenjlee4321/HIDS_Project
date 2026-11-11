"""Explicit root-only installed storage pressure acceptance; never fills a disk.

Pins a read snapshot to exercise WAL admission, then lowers only the HIDS quota
below retained evidence. All history is preserved and original config restored.
"""
import copy
import json
import math
import os
from pathlib import Path
import pwd
import socket
import sqlite3
import subprocess
import tempfile
import time
import uuid
from m3_runtime_ubuntu_acceptance import Reader,STATE,control,query,until

UNITS=('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')


def run(*args):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)


def owned(function):
    account=pwd.getpwnam('hids-ingest');uid,gid=os.geteuid(),os.getegid()
    os.setegid(account.pw_gid);os.seteuid(account.pw_uid)
    try:return function()
    finally:os.seteuid(uid);os.setegid(gid)


def health(message):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(5);connection.connect('/run/hids/m3/health/metrics.sock')
        connection.sendall(json.dumps(message,separators=(',',':')).encode()+b'\n')
        raw=bytearray()
        while len(raw)<=2048:
            data=connection.recv(1)
            if not data:return None
            if data==b'\n':return json.loads(raw)
            raw.extend(data)
    raise AssertionError('health reply exceeded bounds')


def bytes_used():return sum(max(p.stat().st_size,p.stat().st_blocks*512) for p in STATE.iterdir() if p.is_file())


def main():
    assert os.getuid()==0
    config=Path('/etc/hids/m3.json');original=config.read_bytes();settings=json.loads(original)
    backup=Path(tempfile.mkdtemp(prefix='hids-m3-storage.',dir='/run'));backup.chmod(0o700)
    (backup/'config.json').write_bytes(original);(backup/'config.json').chmod(0o600)
    reader=None;snapshot=None;activation=None
    report={}
    try:
        run('systemctl','stop',*UNITS)
        pages=max(128,math.ceil((STATE/'control.sqlite').stat().st_size/4096)+16)
        reserve=(pages+2)*(4096+24)+32
        settings.update(max_pages=pages,storage=dict(max_wal_bytes=8*reserve,
            max_state_bytes=max(1024*1024*1024,bytes_used()*2+32*reserve),
            warning_free_bytes=1024*1024*1024,critical_free_bytes=512*1024*1024,
            minimum_free_bytes=256*1024*1024))
        config.write_text(json.dumps(settings)+'\n')
        run('systemctl','start','hids-m3.socket')
        activation=str(uuid.uuid4());control('activate',activation)
        run('systemctl','stop','hids-m3-health.timer','hids-m3-health.service')
        reader=Reader();until(lambda:control('status')['source_ready'])
        lines=Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines();lines[-1]+=b' '
        reader.send((b'\n'.join(lines)+b'\n').replace(b':100)',b':830002)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        current=control('status')['interval'];generation=current['generation']
        snapshot=owned(lambda:sqlite3.connect((STATE/'control.sqlite').as_uri()+'?mode=ro',uri=True,isolation_level=None))
        owned(lambda:snapshot.execute('BEGIN'))
        owned(lambda:snapshot.execute('SELECT * FROM m3_intervals').fetchall())
        warning=False;started=time.monotonic();last_sample=None;partial=False
        for index in range(3000):
            observation=dict(sample_ns=time.monotonic_ns(),kernel=dict(state='unavailable'),dispatcher=dict(state='missing'))
            response=health(dict(version=3,command='sample',activation=activation,generation=generation,observation=observation))
            if response is None or response.get('result')!='recorded':break
            last_sample=observation['sample_ns']
            if index%16==0:
                status=control('status')
                if status['storage']['state']=='warning':
                    warning=True
                    if not partial:
                        reader.send(lines[0].replace(b':100)',b':830001)')+b'\n')
                        until(lambda:query(activation,"SELECT state FROM m3_disposition WHERE identity='1794096000.123:830001'")==[('open',)])
                        partial=True
                if status['failure']=='storage_pressure':break
        else:raise AssertionError('WAL pressure did not stop admission')
        until(lambda:control('status')['failure']=='storage_pressure')
        status=control('status')
        assert warning and partial
        assert status['storage']['state']=='critical' and status['storage']['reason']=='wal_budget'
        assert status['storage']['wal_bytes']<settings['storage']['max_wal_bytes']
        assert status['possible_gap'] and not status['source_ready'] and not status['reader_connected']
        assert reader.process.wait(timeout=5)!=0
        assert query(activation,"SELECT identity FROM m3_execution")==[('1794096000.123:830002',)]
        assert query(activation,"SELECT state FROM m3_disposition WHERE identity='1794096000.123:830001'")==[('interrupted',)]
        assert query(activation,'SELECT scanned=frontier FROM m3_cursor')==[(1,)]
        report['wal']=dict(status=status['storage'],seconds=round(time.monotonic()-started,3),samples=index+1,last_acknowledged_sample=last_sample)
        print('PASS: observed warning, bounded WAL stop, root status, interrupted A and preserved committed B',flush=True)
        owned(lambda:snapshot.execute('ROLLBACK'));owned(snapshot.close);snapshot=None
        until(lambda:control('status')['storage']['state']=='normal',timeout=8)
        assert control('status')['failure']=='storage_pressure' and not control('status')['source_ready']
        print('PASS: SQLite checkpoint reclaims redundant WAL after reader release without automatic reauthorization',flush=True)
        reader.close();reader=None
        run('systemctl','stop',*UNITS)
        limited=copy.deepcopy(settings)
        used=bytes_used()
        assert used-4096>=16*reserve,'retained state too small for quota-only installed test'
        limited['storage']['max_state_bytes']=used-4096
        config.write_text(json.dumps(limited)+'\n')
        run('systemctl','start','hids-m3.socket')
        status=control('status')
        assert status['failure']=='storage_pressure' and status['storage']['state']=='exhausted'
        assert status['storage']['reason']=='state_budget' and not status['source_ready']
        assert query(activation,"SELECT identity FROM m3_execution")==[('1794096000.123:830002',)]
        report['quota']=status['storage']
        print('PASS: existing state above configured quota starts status-only, retains evidence and admits no source',flush=True)
        run('systemctl','stop',*UNITS)
        config.write_bytes(original)
        run('systemctl','start','hids-m3.socket')
        status=control('status')
        assert status['failure'] is None and status['storage']['state'] in ('normal','warning')
        assert not status['source_ready']
        activation=str(uuid.uuid4());control('activate',activation)
        reader=Reader();until(lambda:control('status')['source_ready'])
        reader.send((b'\n'.join(lines)+b'\n').replace(b':100)',b':830003)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        print('PASS: restored policy and new explicit authorization collect C',flush=True)
        (backup/'report.json').write_text(json.dumps(report,sort_keys=True)+'\n')
        (backup/'report.json').chmod(0o600)
        print(json.dumps(report,sort_keys=True),flush=True)
    finally:
        if snapshot:
            owned(lambda:snapshot.execute('ROLLBACK'));owned(snapshot.close)
        if activation:
            try:control('deactivate',activation)
            except Exception:pass
        if reader:reader.close()
        run('systemctl','stop',*UNITS)
        config.write_bytes(original)
        assert config.read_bytes()==original
        print('Restored HIDS config and stopped units; retained history/report '+str(backup),flush=True)


if __name__=='__main__':main()
