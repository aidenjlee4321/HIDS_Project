"""Synthetic mount-aliased M4 WAL/retained-backup admission probe only."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from engine.detection.m4_live import LiveSource,POLICY
from engine.detection.m4_rule_store import RuleStore
from engine.detection.m4_rules import REFERENCE,load_rules
from engine.detection.m4_service import isolation_probe
from engine.detection.m4_migrate import snapshot
from engine.ingestion.m3_storage import StoragePressure


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--scope',required=True);args=parser.parse_args()
    root=args.root
    if (root.parent!=Path('/var/tmp') or not root.name.startswith('hids-m4-handoff.') or root.resolve()!=root or
        root.stat().st_uid!=0 or stat.S_IMODE(root.stat().st_mode)!=0o711 or os.getuid()==0):
        raise RuntimeError('synthetic namespace required')
    if not Path('/var/lib/hids/m3').samefile(root/'source') or not Path('/var/lib/hids/m4').samefile(root/'state'):
        raise RuntimeError('synthetic mount aliases required before store access')
    scope=json.loads(args.scope);source=LiveSource(Path('/var/lib/hids/m3'),**scope)
    isolation=isolation_probe(source);rules=load_rules([REFERENCE])
    with RuleStore() as store:
        store.select_evaluations(source,rules)
        before=snapshot(store.db);plan=store.db.execute('SELECT rule_plan FROM m4h_bindings ORDER BY binding_key').fetchall()
        reader=sqlite3.connect(store.path.as_uri()+'?mode=ro',uri=True,isolation_level=None)
        try:
            reader.execute('BEGIN');reader.execute('SELECT count(*) FROM m4h_events').fetchone()
            started=time.monotonic()
            for n in range(4096):
                if time.monotonic()-started>20:raise TimeoutError('bounded WAL probe deadline')
                try:
                    # Same header marker creates real WAL frames without changing
                    # event/rule/finding history, schema identity or cursor values.
                    with store.transaction():store.db.execute('PRAGMA user_version=2')
                except StoragePressure:break
            else:raise AssertionError('WAL budget did not refuse within the bounded probe')
            wal=store.guard.observe(store.path,force=True)
            assert wal['state']=='critical' and wal['reason']=='wal_budget' and wal['wal_bytes']<POLICY['max_wal_bytes']
            try:store.import_page(source,rules)
            except StoragePressure:pass
            else:raise AssertionError('WAL pressure admitted progress')
            assert snapshot(store.db)==before and store.db.execute('SELECT rule_plan FROM m4h_bindings ORDER BY binding_key').fetchall()==plan
        finally:reader.close()
        store.guard.checkpoint(store.db,store.path)
        assert store.guard.observe(store.path,force=True)['state']=='normal'
        directory=store.directory.parent/'backups'/'accounting-probe';directory.mkdir(mode=0o700)
        path=directory/'reserved.bin';fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            os.ftruncate(fd,POLICY['max_state_bytes']*3//4)
            aggregate=store.guard.observe(store.path,force=True)
            assert aggregate['state']=='critical' and aggregate['reason']=='state_budget'
            try:store.import_page(source,rules)
            except StoragePressure:pass
            else:raise AssertionError('retained backup budget admitted progress')
            assert snapshot(store.db)==before
            os.ftruncate(fd,0);os.fsync(fd)
        finally:os.close(fd)
        assert store.guard.observe(store.path,force=True)['state']=='normal'
        store.import_page(source,rules);store.evaluate_pending()
        summary=store.summary()
        assert summary['events']==18 and summary['alerts']==2 and summary['unevaluated']==16 and summary['pending']==0
        after=snapshot(store.db)
        assert all(after[t]==before[t] for t in ('m4h_events','m4h_rules','m4h_evaluations','m4h_alerts'))
        assert store.db.execute('PRAGMA integrity_check').fetchone()==('ok',) and not store.db.execute('PRAGMA foreign_key_check').fetchall()
        print(json.dumps(dict(result='passed',isolation=isolation,wal_frames_written=n,wal=wal,aggregate=aggregate,
                             recovered=True,history_unchanged=True,summary=summary),sort_keys=True),flush=True)


if __name__=='__main__':main()
