"""Bounded synthetic review probe: SQLite logical budgets versus pinned WAL.

Never opens installed HIDS databases or native sources. Retains its private model
and report. Does not fill a filesystem or inject real device/storage failures.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from engine.ingestion.m3_runtime import Runtime
from engine.ingestion import m3_health


def main():
    os.umask(0o077)
    directory=Path(tempfile.mkdtemp(prefix='hids-m3-storage-review.')).resolve()
    assert shutil.disk_usage(directory).free >= 128*1024*1024
    runtime=Runtime(directory,'7d9b6873-c6a0-4e9a-88ab-5ec2c04dc592',max_activations=2,max_pages=64,position_limit=32)
    activation='47e48803-cdf5-44c5-8b08-f873575470e7'
    interval=runtime.activate(activation)
    now=100_000_000_000
    def sample(tick):
        observation=dict(sample_ns=tick,kernel=dict(state='observed',
            boot_id='00000000-0000-4000-8000-000000000001',auditd_pid=42,
            lost=0,backlog=0,backlog_limit=64,enabled=1),dispatcher=dict(state='missing'))
        m3_health.record(runtime.db,activation,interval['generation'],observation,now_ns=tick)
    sample(now)
    reader=sqlite3.connect(runtime.path.as_uri()+'?mode=ro',uri=True,isolation_level=None)
    try:
        reader.execute('BEGIN')
        first=reader.execute('SELECT observation FROM m3_health').fetchall()
        before=runtime.db.execute('PRAGMA page_count').fetchone()[0]
        for index in range(1,513):sample(now+index)
        after=runtime.db.execute('PRAGMA page_count').fetchone()[0]
        page_size=runtime.db.execute('PRAGMA page_size').fetchone()[0]
        report=dict(model='sanitized health projection only',samples_committed=513,
            logical_page_budget=runtime.db.execute('PRAGMA max_page_count').fetchone()[0],
            logical_page_count_before=before,logical_page_count_after=after,page_size=page_size,
            journal_size_limit=runtime.db.execute('PRAGMA journal_size_limit').fetchone()[0],
            wal_bytes_while_pinned=Path(str(runtime.path)+'-wal').stat().st_size,
            passive_checkpoint_while_pinned=runtime.db.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone(),
            health_rows=runtime.db.execute('SELECT COUNT(*) FROM m3_health').fetchone()[0])
        assert reader.execute('SELECT observation FROM m3_health').fetchall()==first
        reader.execute('ROLLBACK')
        report['passive_checkpoint_after_release']=runtime.db.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
        report['integrity']=runtime.db.execute('PRAGMA integrity_check').fetchone()[0]
        assert report['integrity']=='ok' and report['health_rows']==1
        assert after<=report['logical_page_budget']
        assert report['wal_bytes_while_pinned']>report['journal_size_limit']
        assert report['wal_bytes_while_pinned']>report['logical_page_budget']*page_size
        (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(report,retained_evidence=str(directory)),sort_keys=True),flush=True)
    finally:
        reader.close();runtime.close()


if __name__=='__main__':main()
