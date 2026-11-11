"""Root-only installed event metadata/diagnostic acceptance using sanitized stdin.

Exercises actual C++ observations and atomic SQLite faults; no Audit policy changes.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid
from m3_runtime_ubuntu_acceptance import Reader,STATE,control,query,until

UNITS=('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')


def run(*args):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)


def main():
    assert os.getuid()==0
    lines=Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines();lines[-1]+=b' '
    fixture=b'\n'.join(lines)+b'\n'
    reader=None;activation=None;database=None
    def start():
        nonlocal reader,activation
        run('systemctl','stop',*UNITS);run('systemctl','start','hids-m3.socket')
        activation=str(uuid.uuid4());control('activate',activation)
        reader=Reader();until(lambda:control('status')['source_ready'])
    def stop():
        nonlocal reader
        control('deactivate',activation);reader.close();reader=None
    try:
        start()
        reader.send(fixture.replace(b':100)',b':840001)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        row=query(activation,'SELECT format,arch,collector_profile,first_observed_unix_ns,received_at,persistence_started_at FROM m3_event_metadata')[0]
        assert row[0:3]==(1,0xc00000b7,'linux.audit.aarch64.string/1')
        assert type(row[3]) is int and row[3]>=0
        assert all(type(value) is str and value.endswith('Z') for value in row[4:])
        assert query(activation,'SELECT identity FROM m3_execution')==[('1794096000.123:840001',)]
        bad=fixture.replace(b'nametype=NORMAL',b'nametype=PARENT').replace(b':100)',b':840002)')
        assert bad!=fixture
        reader.send(bad)
        until(lambda:control('status')['event_health']['rejected_groups']==1)
        status=control('status')
        assert status['source_ready'] and status['event_health']['observed_executions']==1
        assert status['event_health']['rejection_details']==1
        details=control('diagnostics')
        assert details['available'] and len(details['items'])==1
        assert details['items'][0]['identity']=='1794096000.123:840002'
        assert details['items'][0]['reason']=='invalid_path_record'
        assert details['items'][0]['recorded_at'].endswith('Z')
        assert query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)]
        stop()
        assert control('diagnostics')['items']==details['items']
        print('PASS: actual native observation/architecture and distinct backend times persist; root diagnostics retain a sanitized rejection after revocation',flush=True)
        for table,first,second in (('m3_event_metadata',840003,840004),('m3_rejections',840005,840006)):
            start()
            reader.send(fixture.replace(b':100)',f':{first})'.encode()))
            until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
            database=sqlite3.connect(STATE/f'{activation}.sqlite',isolation_level=None)
            trigger='fail_event_acceptance'
            try:
                database.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'test'); END")
                target=fixture if table=='m3_event_metadata' else fixture.replace(b'nametype=NORMAL',b'nametype=PARENT')
                reader.send(target.replace(b':100)',f':{second})'.encode()))
                assert reader.process.wait(timeout=8)!=0
                status=control('status')
                assert status['failure']=='storage_failure' and status['possible_gap']
                assert query(activation,'SELECT identity FROM m3_execution')==[(f'1794096000.123:{first}',)]
                assert query(activation,'SELECT identity FROM m3_event_metadata')==[(f'1794096000.123:{first}',)]
                assert query(activation,f"SELECT state FROM m3_disposition WHERE identity='1794096000.123:{second}'")==[('interrupted',)]
                assert query(activation,'SELECT COUNT(*) FROM m3_rejections')==[(0,)]
            finally:
                database.execute(f'DROP TRIGGER {trigger}');database.close();database=None
            reader.close();reader=None
            print('PASS: failed '+table+' insert rolls back event/disposition atomically and preserves the independent committed event',flush=True)
    finally:
        if database:database.close()
        if activation:
            try:control('deactivate',activation)
            except Exception:pass
        if reader:reader.close()
        run('systemctl','stop',*UNITS)
        print('Retained private metadata/diagnostic history; all HIDS/checker units stopped',flush=True)


if __name__=='__main__':main()
