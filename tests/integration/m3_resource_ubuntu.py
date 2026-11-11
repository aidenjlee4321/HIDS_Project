"""Explicit installed-runtime resource-pressure acceptance using sanitized stdin.

No Audit configuration, rules or native host commands are collected. All ledger
history is retained. Temporary HIDS position/page budgets are restored on exit.
"""
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import uuid
from m3_runtime_ubuntu_acceptance import Reader, STATE, control, query, until


def command(*args):
    return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)


def payload(identity, size=8192):
    return f'type=PATH msg=audit(1794096000.123:{identity}): name='.encode()+b'a'*size+b'\n'


def eoe(identity):
    return f'type=EOE msg=audit(1794096000.123:{identity}): \n'.encode()


def usage(pid):
    fields=dict(line.split(':',1) for line in Path(f'/proc/{pid}/status').read_text().splitlines())
    return {key:int(fields[key].split()[0]) for key in ('VmRSS','VmHWM')}


def fill(reader, record, count):
    for first in range(0,count,32):
        reader.send(record*min(32,count-first))


def main():
    assert os.getuid()==0
    assert command('systemctl','is-active','auditd').stdout.strip()==b'active'
    config=Path('/etc/hids/m3.json');original=config.read_bytes()
    settings=json.loads(original);settings.update(max_pages=8192,position_limit=16384)
    workspace=Path(tempfile.mkdtemp(prefix='hids-m3-resource.',dir='/run'))
    (workspace/'config.json').write_bytes(original);(workspace/'config.json').chmod(0o600)
    fixture=Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines()
    fixture[-1]+=b' ';fixture=b'\n'.join(fixture)+b'\n'
    reader=None;activation=None
    report={}

    def start():
        nonlocal activation,reader
        activation=str(uuid.uuid4());control('activate',activation)
        reader=Reader();until(lambda:control('status')['source_ready'])

    def stop():
        nonlocal reader
        control('deactivate',activation)
        reader.close();reader=None

    try:
        command('systemctl','stop','hids-m3.socket','hids-m3.service')
        config.write_text(json.dumps(settings)+'\n')
        command('systemctl','start','hids-m3.socket')
        start()
        large=payload(700001)
        records=math.ceil(16*1024*1024/len(large))+4
        began=time.monotonic();fill(reader,large,records)
        until(lambda:control('status')['event_health']['resource_incidents']==1,timeout=30)
        status=control('status')
        assert status['source_ready'] and status['event_health']['discarding']==1
        assert query(activation,'SELECT COUNT(*) FROM m3_execution')==[(0,)]
        assert query(activation,'SELECT scanned>frontier FROM m3_cursor')==[(1,)]
        reader.send(fixture.replace(b':100)',b':700002)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        before_eoe=usage(reader.process.pid)
        reader.send(eoe(700001))
        until(lambda:control('status')['event_health']['discarding']==0)
        assert query(activation,'SELECT scanned=frontier FROM m3_cursor')==[(1,)]
        evidence=json.loads(query(activation,'SELECT evidence FROM m3_resources')[0][0])
        assert evidence['reason']=='event_bytes' and evidence['group_limit']==16*1024*1024
        assert evidence['retained_accounted_bytes']<=32*1024*1024
        reader.send(eoe(700001))
        until(lambda:control('status')['event_health']['late_records']==1)
        assert query(activation,'SELECT identity FROM m3_execution')==[('1794096000.123:700002',)]
        report['oversize']=dict(records=records,seconds=round(time.monotonic()-began,3),collector=before_eoe,evidence=evidence)
        stop()
        print('PASS: real 16 MiB event limit durably discards only A, accepts independent B, waits for A EOE and suppresses later A',flush=True)

        start();began=time.monotonic()
        a,b=payload(710001),payload(710002)
        count=15*1024*1024//len(a)
        fill(reader,a,count)
        reader.send(fixture.replace(b':100)',b':710003)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        fill(reader,b,count)
        until(lambda:control('status')['event_health']['resource_incidents']>=1,timeout=30)
        rows=query(activation,'SELECT identity,evidence FROM m3_resources')
        assert len(rows)==1 and rows[0][0]=='1794096000.123:710001'
        evidence=json.loads(rows[0][1]);assert evidence['reason']=='aggregate_bytes'
        assert evidence['retained_accounted_bytes']<=32*1024*1024
        assert evidence['retained_accounted_bytes']+evidence['requested_accounted_bytes']>32*1024*1024
        assert control('status')['source_ready']
        measured=usage(reader.process.pid)
        reader.send(eoe(710002)+eoe(710001))
        until(lambda:control('status')['event_health']['discarding']==0)
        until(lambda:query(activation,'SELECT scanned=frontier FROM m3_cursor')==[(1,)])
        assert query(activation,'SELECT identity FROM m3_execution')==[('1794096000.123:710003',)]
        report['aggregate']=dict(records_each=count,seconds=round(time.monotonic()-began,3),collector=measured,evidence=evidence)
        stop()
        print('PASS: bounded 32 MiB accounting, durable oldest-blocker discard, independent committed event preservation and resolved frontier',flush=True)

        start()
        reader.send(fixture.replace(b':100)',b':720003)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        database=sqlite3.connect(STATE/f'{activation}.sqlite',isolation_level=None)
        try:
            database.execute("CREATE TRIGGER resource_acceptance_fault BEFORE INSERT ON m3_resources BEGIN SELECT RAISE(ABORT,'test'); END")
            large=payload(720001)
            try: fill(reader,large,math.ceil(16*1024*1024/len(large))+4)
            except BrokenPipeError: pass
            assert reader.process.wait(timeout=8)!=0
            status=control('status')
            assert status['failure']=='storage_failure' and status['possible_gap']
            assert query(activation,'SELECT COUNT(*) FROM m3_resources')==[(0,)]
            assert query(activation,'SELECT identity FROM m3_execution')==[('1794096000.123:720003',)]
            assert query(activation,"SELECT state FROM m3_disposition WHERE identity='1794096000.123:720001'")==[('interrupted',)]
        finally:
            database.execute('DROP TRIGGER resource_acceptance_fault');database.close()
        print('PASS: failed resource persistence stops safely without inventing a rejection or losing an independent committed event',flush=True)
        print(json.dumps(report,sort_keys=True),flush=True)
    finally:
        if activation:
            try: control('deactivate',activation)
            except Exception: pass
        if reader:reader.close()
        command('systemctl','stop','hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')
        config.write_bytes(original)
        assert config.read_bytes()==original
        print('Restored HIDS test budgets; retained resource-test history and private backup '+str(workspace),flush=True)


if __name__=='__main__':main()
