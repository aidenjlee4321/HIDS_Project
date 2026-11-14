"""Implementation acceptance on synthetic M3 Runtime/ledger + real destination."""
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from engine.detection.m4_handoff import Source, Store, Worker, Invalid
from engine.detection.m4_pilot import load_json
from engine.ingestion.m3_event import ARCH, PROFILE
from engine.ingestion.m3_runtime import Runtime
from engine.ingestion import m3_storage

ROOT=Path(__file__).resolve().parents[2]
SOURCE='00000000-0000-4000-8000-000000000001'
ACTIVATION='00000000-0000-4000-8000-000000000002'


def lab_policy(pages):
    policy=m3_storage.defaults(pages,4)
    policy.update(warning_free_bytes=4*1024**2,critical_free_bytes=2*1024**2,minimum_free_bytes=1024**2)
    return policy


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hids-m4-handoff.')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.source_dir=self.root/'source';self.source_dir.mkdir(mode=0o700)
        self.runtime=Runtime(self.source_dir,SOURCE,max_activations=4,max_pages=512,position_limit=1024,storage=lab_policy(512))
        self.addCleanup(self.runtime.close)
        scope=self.runtime.activate(ACTIVATION)
        self.source=Source(self.source_dir,SOURCE,ACTIVATION,scope['generation'])
        self.destination=self.root/'destination'
        self.store=self.open_store(create=True)
        self.addCleanup(lambda:self.store.close())
        self.execution=load_json(ROOT/'tests/fixtures/m4/execution.json')['execution']
        self.rule=load_json(ROOT/'rules/pilot/configured-executable.json')
        self.offset=0

    def open_store(self,create=False):
        return Store(self.destination,create=create,max_pages=64,storage=lab_policy(64),lab_only=True)

    def register(self,number):
        identity=f'1.001:{number}'
        self.runtime.progress.register(identity,self.offset,self.offset+10,eoe=True);self.offset+=10
        return identity

    def accept(self,number,known=True):
        obs=dict(version=1,arch=ARCH,profile=PROFILE,first_observed_unix_ns=123) if known else None
        self.runtime.progress.accept(f'1.001:{number}',self.execution,observation=obs)

    def counts(self):
        return tuple(self.store.db.execute('SELECT count(*) FROM '+name).fetchone()[0]
                     for name in ('m4h_events','m4h_evaluations','m4h_alerts'))

    def drain(self,rule=True):
        for _ in range(20):
            n=self.store.import_page(self.source,[self.rule] if rule else [],limit=1)
            if not n:return
        self.fail('fixture sweep did not finish')

    def test_committed_handoff_preserves_metadata_and_source_bytes(self):
        self.register(1);self.accept(1)
        files=[self.source_dir/'control.sqlite',self.source_dir/(ACTIVATION+'.sqlite')]
        before={str(p)+suffix:hashlib.sha256(Path(str(p)+suffix).read_bytes()).hexdigest() for p in files for suffix in ('','-wal')}
        self.drain();self.store.evaluate_pending()
        self.assertEqual(self.counts(),(1,1,1))
        event=json.loads(self.store.db.execute('SELECT envelope FROM m4h_events').fetchone()[0])
        self.assertEqual(event['metadata']['first_observed_unix_ns'],123)
        self.assertEqual(event['metadata']['profile'],PROFILE)
        self.assertEqual(event['execution'],self.execution)
        self.assertNotIn('lease',json.dumps(event))
        for name,digest in before.items():self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(),digest)
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_durable_sweep_finds_A_after_B_and_restart(self):
        self.register(1);self.register(2);self.accept(2)
        self.store.import_page(self.source,[self.rule],limit=1)
        self.accept(1)
        self.store.close();self.store=self.open_store()
        self.drain();self.drain();self.store.evaluate_pending()
        self.assertEqual(self.counts(),(2,2,2))
        state=json.loads(self.store.db.execute('SELECT state FROM m4h_bindings').fetchone()[0])
        self.assertEqual(state['settled'],20)

    def test_default_no_rules_does_not_invent_evaluation(self):
        self.register(1);self.accept(1);self.drain(rule=False)
        self.assertEqual(self.counts(),(1,0,0))
        self.assertEqual(self.store.summary()['pending'],0)

    def test_unknown_source_profile_is_unable(self):
        self.register(1);self.accept(1,known=False);self.drain();self.store.evaluate_pending()
        self.assertEqual(self.store.db.execute('SELECT state,reason FROM m4h_evaluations').fetchone(),('unable','source_profile_unknown'))
        self.assertEqual(self.counts(),(1,1,0))

    def test_missing_metadata_blocks_without_progress(self):
        self.register(1);self.accept(1)
        self.runtime.progress.db.execute('DELETE FROM m3_event_metadata')
        with self.assertRaises(Invalid):self.drain()
        self.assertEqual(self.counts(),(0,0,0))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM m4h_bindings').fetchone()[0],0)

    def test_rejected_and_interrupted_rows_never_import(self):
        a=self.register(1);self.runtime.progress.reject(a)
        self.register(2);self.runtime.progress.recover();self.drain()
        self.assertEqual(self.counts(),(0,0,0))

    def test_wrong_source_generation_schema_and_production_path_refuse(self):
        wrong='00000000-0000-4000-8000-000000000099'
        for source in (Source(self.source_dir,wrong,ACTIVATION,self.source.scope['generation']),Source(self.source_dir,SOURCE,ACTIVATION,wrong)):
            with self.assertRaises(Invalid):self.store.import_page(source)
        with self.assertRaises(Invalid):Source(Path('/var/lib/hids/m3'),SOURCE,ACTIVATION,wrong)
        self.runtime.progress.db.execute('CREATE TABLE extra(x)')
        with self.assertRaises(Invalid):self.store.import_page(self.source)

    def test_missing_sidecars_refuse_without_creating_any(self):
        self.runtime.close()
        sidecar=self.source_dir/'control.sqlite-shm'
        saved=self.source_dir/'closed-shm.saved'
        if sidecar.exists():sidecar.rename(saved)
        before={p.name for p in self.source_dir.iterdir()}
        try:
            with self.assertRaises(OSError):self.store.import_page(self.source)
            self.assertEqual({p.name for p in self.source_dir.iterdir()},before)
        finally:
            if saved.exists():saved.rename(sidecar)

    def test_cursor_regression_blocks_binding(self):
        self.register(1);self.accept(1);self.drain()
        self.runtime.progress.db.execute('UPDATE m3_cursor SET frontier=0')
        with self.assertRaises(Invalid):self.store.import_page(self.source)
        self.assertEqual(self.counts(),(1,1,0))

    def test_immutable_conflict_does_not_advance_cursor(self):
        self.register(1);self.register(2);self.accept(2)
        self.store.import_page(self.source,[self.rule]);self.store.import_page(self.source,[self.rule])
        before=self.store.db.execute('SELECT state FROM m4h_bindings').fetchone()
        changed=dict(self.execution,uid=1)
        self.runtime.progress.db.execute('UPDATE m3_execution SET payload=?',(json.dumps(changed),))
        with self.assertRaises(Invalid):self.store.import_page(self.source,[self.rule])
        self.assertEqual(self.store.db.execute('SELECT state FROM m4h_bindings').fetchone(),before)
        self.assertEqual(self.counts(),(1,1,0))

    def test_import_progress_failure_rolls_back_everything(self):
        self.register(1);self.accept(1)
        self.store.db.execute("CREATE TEMP TRIGGER fail_progress BEFORE UPDATE ON m4h_bindings BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.import_page(self.source,[self.rule])
        self.assertEqual(self.counts(),(0,0,0))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM m4h_bindings').fetchone()[0],0)
        self.store.db.execute('DROP TRIGGER fail_progress');self.drain();self.store.evaluate_pending()
        self.assertEqual(self.counts(),(1,1,1))

    def test_alert_failure_retains_event_pending_and_retry(self):
        self.register(1);self.accept(1);self.drain()
        self.store.db.execute("CREATE TEMP TRIGGER fail_alert BEFORE INSERT ON m4h_alerts BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.evaluate_pending()
        self.assertEqual(self.counts(),(1,1,0))
        self.assertEqual(self.store.summary()['pending'],1)
        self.store.db.execute('DROP TRIGGER fail_alert');self.store.evaluate_pending();self.store.evaluate_pending()
        self.assertEqual(self.counts(),(1,1,1))

    def test_source_failure_does_not_stop_other_binding(self):
        self.register(1);self.accept(1)
        bad=Source(self.source_dir,'00000000-0000-4000-8000-000000000099',ACTIVATION,self.source.scope['generation'])
        worker=Worker(self.store,[bad,self.source],[self.rule])
        status=worker.step()
        self.assertEqual(status['bindings'][bad.key],'source_invalid')
        self.assertEqual(status['bindings'][self.source.key],'imported')
        self.assertEqual(self.counts(),(1,1,1))

    def test_exclusive_destination_unknown_version_and_live_refuse(self):
        with self.assertRaises(BlockingIOError):self.open_store()
        with self.assertRaises(Invalid):Store(self.root/'live',create=True,max_pages=64,storage=lab_policy(64),lab_only=False)
        self.store.db.execute('PRAGMA user_version=99');self.store.close()
        before=self.store.path.read_bytes()
        with self.assertRaises(Invalid):self.open_store()
        self.assertEqual(self.store.path.read_bytes(),before)

    def test_real_destination_SQLITE_FULL_preserves_committed_state(self):
        self.execution['exe_base64']=base64.b64encode(b'/'+b'a'*3999).decode()
        previous=0
        for n in range(1,100):
            self.register(n);self.accept(n)
            state=self.store.db.execute('SELECT state FROM m4h_bindings').fetchone()
            try:self.store.import_page(self.source,limit=1)
            except sqlite3.OperationalError as exc:
                if hasattr(exc,'sqlite_errorcode'):self.assertEqual(exc.sqlite_errorcode,13)
                else:self.assertEqual(str(exc),'database or disk is full')  # Python 3.9 lacks error-code attributes.
                self.assertEqual(self.store.db.execute('SELECT state FROM m4h_bindings').fetchone(),state)
                self.assertEqual(self.counts()[0],previous)
                self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                break
            previous=self.counts()[0]
        else:self.fail('actual destination page cap did not return SQLITE_FULL')

    def crash(self,stage):
        self.register(1);self.accept(1);self.store.close()
        code='''import sys,os,signal,json
from pathlib import Path
from engine.detection.m4_handoff import Store,Source
from engine.detection.m4_pilot import load_json
root=Path(sys.argv[1]);scope=json.loads(sys.argv[2]);policy=json.loads(sys.argv[3]);stage=sys.argv[4]
s=Store(root/'destination',max_pages=64,storage=policy,lab_only=True)
source=Source(root/'source',scope['source'],scope['activation'],scope['generation'])
r=load_json(Path(sys.argv[5]))
s.db.create_function('crash_now',0,lambda:os.kill(os.getpid(),signal.SIGKILL))
if stage=='import':s.db.execute("CREATE TEMP TRIGGER crash_import AFTER UPDATE ON m4h_bindings BEGIN SELECT crash_now(); END")
s.import_page(source,[r])
if stage=='pending':os.kill(os.getpid(),signal.SIGKILL)
if stage=='alert':s.db.execute("CREATE TEMP TRIGGER crash_alert AFTER INSERT ON m4h_alerts BEGIN SELECT crash_now(); END")
s.evaluate_pending()
if stage=='committed':os.kill(os.getpid(),signal.SIGKILL)
'''
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.root),json.dumps(self.source.scope),json.dumps(lab_policy(64)),stage,str(ROOT/'rules/pilot/configured-executable.json')],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,timeout=15)
        self.assertEqual(result.returncode,-signal.SIGKILL,result.stderr.decode())
        self.store=self.open_store()
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        if stage=='import':self.assertEqual(self.counts(),(0,0,0))
        elif stage=='committed':self.assertEqual(self.counts(),(1,1,1))
        else:self.assertEqual(self.counts(),(1,1,0))
        self.drain();self.store.evaluate_pending();self.assertEqual(self.counts(),(1,1,1))

    def test_actual_sigkill_import_transaction(self):self.crash('import')
    def test_actual_sigkill_after_import_commit(self):self.crash('pending')
    def test_actual_sigkill_alert_transaction(self):self.crash('alert')
    def test_actual_sigkill_after_alert_commit(self):self.crash('committed')


if __name__=='__main__':unittest.main()
