"""Approved v2 implementation acceptance on synthetic data only."""
import base64
import copy
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

import test_m4_handoff as fixtures
from engine.detection.m4_handoff import Store
from engine.detection.m4_service import LiveStore,LiveSource,POLICY,validate_config
from engine.detection.m4_rule_store import RuleStore
from engine.detection.m4_migrate import migrate_store,snapshot
from engine.detection.m4_rules import validate_rule,evaluate,REFERENCE,load_rules
from engine.detection.m4_pilot import Invalid,load_json,digest
from engine.ingestion import m3_storage
from engine.detection import m4_service

ROOT=Path(__file__).resolve().parents[2]
RULE=load_json(ROOT/'rules/process/configured-root-shell.json')


class RulesV2Tests(unittest.TestCase):
    def setUp(self):
        self.space=patch('engine.ingestion.m3_storage.Guard._available',return_value=8*1024**3)
        self.space.start();self.addCleanup(self.space.stop)
        self.env=fixtures.HandoffTests();self.env.setUp();self.addCleanup(self.env.doCleanups)
        parent=self.env.root/'m4';parent.mkdir(mode=0o700)
        self.directory=parent/'store'
        self.store=self.open(LiveStore,create=True);self.addCleanup(lambda:self.store.close())
        self.source=self.real_source(self.env.source.scope)
        for n in range(1,17):self.env.register(n);self.env.accept(n)
        self.store.import_page(self.source);self.store.import_page(self.source)
        self.original=snapshot(self.store.db)

    def real_source(self,scope):
        # Test-only fixed-path constructor bypass. The actual fixed paths and
        # identity are exercised separately under systemd mount namespaces.
        source=LiveSource.__new__(LiveSource);source.directory=self.env.source_dir;source.scope=dict(scope)
        source.key=digest(source.BINDING_DOMAIN,source.scope);return source

    def open(self,kind,create=False):
        obj=kind.__new__(kind)
        Store.__init__(obj,self.directory,create=create,max_pages=512,storage=dict(POLICY),lab_only=False)
        return obj

    def upgrade(self):
        self.store.close();result=migrate_store(self.directory);self.store=self.open(RuleStore);return result

    def new_source(self):
        self.env.runtime.revoke(self.env.source.scope['activation'])
        scope=self.env.runtime.activate(str(uuid.uuid4()))
        source=dict(source=self.source.scope['source'],activation=scope['activation'],generation=scope['generation'])
        self.source=self.real_source(source);self.env.offset=0
        self.env.execution.update(exe_base64=base64.b64encode(b'/usr/bin/dash').decode(),euid=0)

    def add(self,n,known=True):self.env.register(n);self.env.accept(n,known=known)
    def count(self,t):return self.store.db.execute('SELECT count(*) FROM '+t).fetchone()[0]

    def test_real_migration_backup_and_old_history_unchanged(self):
        result=self.upgrade()
        self.assertEqual(snapshot(self.store.db),self.original)
        self.assertEqual(self.store.db.execute('SELECT rule_plan FROM m4h_bindings').fetchall(),[('[]',)])
        backup=Path(result['backup']);self.assertEqual(backup.stat().st_mode&0o777,0o600)
        db=sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True)
        try:
            self.assertEqual(snapshot(db),self.original);LiveStore._identity(db)
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone(),('delete',))
        finally:db.close()
        with self.assertRaises(Invalid):LiveStore._identity(self.store.db)

    def test_old_empty_plan_cannot_be_backfilled(self):
        self.upgrade()
        with patch.object(self.source,'read_page',side_effect=AssertionError('must not read old source')):
            with self.assertRaisesRegex(Invalid,'frozen rule plan'):self.store.import_page(self.source,[RULE])
        self.assertEqual(snapshot(self.store.db),self.original)
        self.assertEqual(self.store.summary()['unevaluated'],16)

    def test_new_activation_positive_has_one_non_demo_explained_finding(self):
        self.upgrade();self.new_source();self.add(1)
        events,state=self.source.read_page()
        self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
        with patch.object(self.source,'read_page',return_value=(events,state)):
            self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
        self.assertEqual(self.count('m4h_events'),17);self.assertEqual(self.count('m4h_alerts'),1)
        self.assertEqual(self.store.summary()['unevaluated'],16)
        row=self.store.db.execute('SELECT demo,severity,explanation,matched_values FROM m4h_alerts').fetchone()
        self.assertEqual(row[:2],(0,'informational'));self.assertIn('identity is unavailable',row[2])
        self.assertEqual(json.loads(row[3]),{'euid':0,'exe_base64':self.env.execution['exe_base64'],'success':True})
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_nonroot_other_executable_unknown_profile_and_uid_distinction(self):
        self.upgrade();self.new_source()
        self.env.execution.update(uid=0,euid=1000);self.add(1)
        self.env.execution.update(euid=0,exe_base64=base64.b64encode(b'/usr/bin/true').decode());self.add(2)
        self.env.execution.update(exe_base64=base64.b64encode(b'/usr/bin/dash').decode());self.add(3,known=False)
        self.env.execution.update(uid=1000,euid=0);self.add(4)
        self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
        self.assertEqual(self.store.summary()['evaluations'],{'no_match':2,'unable':1,'matched':1})
        self.assertEqual(self.count('m4h_alerts'),1)

    def test_frozen_plan_cannot_be_disabled_in_place(self):
        self.upgrade();self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        before=snapshot(self.store.db)
        with self.assertRaisesRegex(Invalid,'frozen rule plan'):self.store.import_page(self.source,[])
        self.assertEqual(snapshot(self.store.db),before)

    def test_definition_revision_boolean_and_unknown_key_refusals(self):
        self.upgrade();self.new_source();self.add(1)
        variants=[]
        for key,value in [('revision','2'),('explanation','changed'),('severity','high'),('demo',True),('script','anything')]:
            rule=copy.deepcopy(RULE);rule[key]=value;variants.append(rule)
        rule=copy.deepcopy(RULE);rule['all_of'][1]['eq']=False;variants.append(rule)
        for rule in variants:
            with self.subTest(rule=rule),self.assertRaises(Invalid):self.store.import_page(self.source,[rule])
        self.assertEqual(snapshot(self.store.db),self.original)

    def test_actual_evaluator_missing_invalid_profile_and_optional_login(self):
        event=dict(self.env.execution,exe_base64=RULE['all_of'][0]['eq'],euid=0)
        self.assertEqual(evaluate(event,RULE['profile'],RULE)[0],'matched')
        self.assertEqual(evaluate(event,None,RULE)[0],'unable')
        event['euid']=False
        with self.assertRaises(ValueError):evaluate(event,RULE['profile'],RULE)

    def test_import_transaction_failure_keeps_history_and_plan_unregistered(self):
        self.upgrade();self.new_source();self.add(1)
        self.store.db.execute("CREATE TEMP TRIGGER fail_import BEFORE UPDATE ON m4h_bindings BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.import_page(self.source,[RULE])
        self.assertEqual(snapshot(self.store.db),self.original)

    def test_alert_failure_preserves_pending_then_idempotent_retry(self):
        self.upgrade();self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        self.store.db.execute("CREATE TEMP TRIGGER fail_alert BEFORE INSERT ON m4h_alerts BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.evaluate_pending()
        self.assertEqual(self.store.summary()['pending'],1);self.assertEqual(self.count('m4h_alerts'),0)
        self.store.db.execute('DROP TRIGGER fail_alert');self.store.evaluate_pending();self.store.evaluate_pending()
        self.assertEqual(self.count('m4h_alerts'),1)

    def test_stored_hash_conflict_is_error_not_match(self):
        self.upgrade();self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        self.store.db.execute("UPDATE m4h_rules SET content_hash='invalid'")
        self.store.evaluate_pending();self.assertEqual(self.store.summary()['evaluations'],{'error':1})
        self.assertEqual(self.count('m4h_alerts'),0)

    def test_writer_lock_and_aggregate_budget_block_before_backup(self):
        with self.assertRaises(BlockingIOError):migrate_store(self.directory)
        self.store.close()
        with patch('engine.detection.m4_migrate.aggregate',return_value=POLICY['max_state_bytes']):
            with self.assertRaises(m3_storage.StoragePressure):migrate_store(self.directory)
        self.store=self.open(LiveStore);self.assertEqual(snapshot(self.store.db),self.original)
        self.assertFalse((self.directory.parent/'backups').exists())

    def crash(self,stage):
        self.store.close()
        code='''import os,sys,signal
from pathlib import Path
from unittest.mock import patch
from engine.detection.m4_migrate import migrate_store
with patch('engine.ingestion.m3_storage.Guard._available',return_value=8*1024**3):
 def fault(stage):
  if stage==sys.argv[2]:os.kill(os.getpid(),signal.SIGKILL)
 migrate_store(Path(sys.argv[1]),fault=fault)
'''
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.directory),stage],cwd=ROOT,
                              env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,timeout=20)
        self.assertEqual(result.returncode,-signal.SIGKILL,result.stderr.decode())
        self.store=self.open(RuleStore if stage=='after_commit' else LiveStore)
        self.assertEqual(snapshot(self.store.db),self.original)
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
        self.assertTrue(list((self.directory.parent/'backups').glob('*/manifest.json')))

    def test_actual_migrator_sigkill_before_commit_keeps_v1(self):self.crash('statement_4')
    def test_actual_migrator_sigkill_after_commit_is_v2(self):self.crash('after_commit')

    def test_pending_only_for_selected_binding_and_frozen_opt_in(self):
        self.upgrade();self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        old=self.source
        self.env.source=old  # Tell the fixture which interval to end next.
        self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        self.store.select_evaluations(self.source,[RULE]);self.store.evaluate_pending()
        self.assertEqual(self.store.binding_pending(old.key),1)
        self.assertEqual(self.store.binding_pending(self.source.key),0)
        self.assertEqual(self.count('m4h_alerts'),1)
        with self.assertRaises(Invalid):self.store.select_evaluations(old,[])

    def test_pending_snapshot_needs_no_source_reread(self):
        self.upgrade();self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        self.store.select_evaluations(self.source,[RULE])
        with patch.object(self.source,'read_page',side_effect=AssertionError('source unavailable')):
            self.store.evaluate_pending()
        self.assertEqual(self.count('m4h_alerts'),1)
        self.assertEqual(self.store.binding_pending(self.source.key),0)

    def test_entry_resumes_pending_at_cap_without_rereading_source(self):
        self.upgrade();self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        cfg=dict(version=2,enabled=True,**self.source.scope,max_pages=512,storage=dict(POLICY),max_events=1,max_seconds=120,rules=[dict(REFERENCE)])
        with patch.object(m4_service,'config',return_value=cfg),patch.object(m4_service,'LiveSource',return_value=self.source),\
             patch.object(m4_service,'isolation_probe',return_value={'source_readonly':True}),patch.object(m4_service,'private'),\
             patch.object(m4_service,'STATE_DIRECTORY',self.directory),patch.object(m4_service,'load_rules',return_value=[RULE]),\
             patch('engine.detection.m4_rule_store.RuleStore',return_value=self.store),\
             patch.object(self.source,'read_page',side_effect=AssertionError('must use committed snapshot')):
            status,code=m4_service.run(once=True)
        self.assertEqual(code,0);self.assertTrue(status['completed']);self.assertEqual(status['alerts'],1)
        self.store=self.open(RuleStore);self.assertEqual(self.store.summary()['unevaluated'],16)

    def test_disabled_entry_performs_no_source_or_store_work(self):
        before=snapshot(self.store.db)
        with patch.object(m4_service,'config',return_value={'enabled':False}),\
             patch.object(m4_service,'LiveSource',side_effect=AssertionError('disabled source read')):
            status,code=m4_service.run()
        self.assertEqual(status['mode'],'disabled');self.assertEqual(code,0)
        self.assertEqual(snapshot(self.store.db),before)

    def test_versioned_root_config_requires_exact_opt_in(self):
        cfg=dict(version=2,enabled=True,source=self.source.scope['source'],activation=self.source.scope['activation'],generation=self.source.scope['generation'],
                 max_pages=512,storage=dict(POLICY),max_events=3,max_seconds=120,rules=[dict(REFERENCE)])
        self.assertEqual(validate_config(cfg),cfg)
        for changes in ({'rules':['*']},{'rules':[dict(REFERENCE,revision='2')]},{'rules':[dict(REFERENCE,hash='bad')]},{'rule_path':'/tmp/x'}):
            value=dict(cfg,**changes)
            with self.assertRaises(Invalid):validate_config(value)
        self.assertEqual(validate_config(dict(cfg,enabled=False))['enabled'],False)
        # Ordinary source-snapshot ownership must not satisfy production rule-file trust.
        if os.getuid()!=0:
            with self.assertRaises(Invalid):load_rules([dict(REFERENCE)])

    def worker_crash(self, operation, committed):
        self.upgrade();self.new_source();self.add(1)
        if operation=='evaluate':self.store.import_page(self.source,[RULE])
        self.store.close()
        code='''import os,sys,signal,json
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from engine.detection.m4_handoff import Store
from engine.detection.m4_live import LiveSource,POLICY
from engine.detection.m4_rule_store import RuleStore
from engine.detection.m4_pilot import digest,load_json
source=LiveSource.__new__(LiveSource);source.directory=Path(sys.argv[2]);source.scope=json.loads(sys.argv[3])
source.key=digest(source.BINDING_DOMAIN,source.scope)
with patch('engine.ingestion.m3_storage.Guard._available',return_value=8*1024**3):
 store=RuleStore.__new__(RuleStore)
 Store.__init__(store,Path(sys.argv[1]),max_pages=512,storage=dict(POLICY),lab_only=False)
 original=store.transaction
 @contextmanager
 def crash_transaction():
  with original():
   yield
   if sys.argv[5]=='before':os.kill(os.getpid(),signal.SIGKILL)
  os.kill(os.getpid(),signal.SIGKILL)
 store.transaction=crash_transaction
 rule=load_json(Path('rules/process/configured-root-shell.json'))
 if sys.argv[4]=='import':store.import_page(source,[rule])
 else:store.select_evaluations(source,[rule]);store.evaluate_pending()
'''
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.directory),str(self.source.directory),
                               json.dumps(self.source.scope),operation,'after' if committed else 'before'],
                              cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,timeout=20)
        self.assertEqual(result.returncode,-signal.SIGKILL,result.stderr.decode())
        self.store=self.open(RuleStore)
        expected_events=17 if operation=='evaluate' or committed else 16
        self.assertEqual(self.count('m4h_events'),expected_events)
        self.assertEqual(self.count('m4h_alerts'),int(operation=='evaluate' and committed))
        self.assertEqual(self.store.summary()['pending'],int(expected_events==17 and not(operation=='evaluate' and committed)))
        # A real reopen/replay must complete once without changing old history.
        self.store.select_evaluations(self.source,[RULE])
        self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
        self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
        self.assertEqual(self.count('m4h_events'),17);self.assertEqual(self.count('m4h_alerts'),1)
        self.assertEqual(self.store.summary()['unevaluated'],16)
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        for row in self.original['m4h_events']:
            self.assertEqual(self.store.db.execute('SELECT * FROM m4h_events WHERE event_key=?',(row[0],)).fetchone(),row)

    def test_v2_process_killed_before_import_commit(self):self.worker_crash('import',False)
    def test_v2_process_killed_after_import_commit(self):self.worker_crash('import',True)
    def test_v2_process_killed_before_finding_commit(self):self.worker_crash('evaluate',False)
    def test_v2_process_killed_after_finding_commit(self):self.worker_crash('evaluate',True)

    def test_competing_destination_writer_does_not_block_source_acceptance(self):
        from engine.detection.m4_handoff import Worker
        self.upgrade();self.new_source();self.add(1)
        blocker=sqlite3.connect(self.store.path,isolation_level=None)
        self.store.db.execute('PRAGMA busy_timeout=25')
        now=[0.0];worker=Worker(self.store,[self.source],[RULE],clock=lambda:now[0])
        try:
            blocker.execute('BEGIN IMMEDIATE')
            first=worker.step()
            self.assertEqual(first['bindings'][self.source.key],'source_or_destination_unavailable')
            self.assertEqual(self.count('m4h_events'),16)
            self.add(2)  # M3 commits independently while M4's destination is locked.
            self.assertEqual(len(self.source.read_page()[0]),2)
        finally:
            if blocker.in_transaction:blocker.execute('ROLLBACK')
            blocker.close()
        now[0]=3.0;status=worker.step();self.assertEqual(status['alerts'],2)
        self.assertEqual(self.count('m4h_events'),18);self.assertEqual(status['unevaluated'],16)
        worker.step();self.assertEqual(self.count('m4h_alerts'),2)

    def test_actual_sqlite_page_limit_preserves_progress_then_retry(self):
        self.upgrade();self.new_source()
        for n in range(1,17):self.add(n)
        before=snapshot(self.store.db)
        pages=self.store.db.execute('PRAGMA page_count').fetchone()[0]
        self.store.db.execute('PRAGMA max_page_count='+str(pages))
        try:
            with self.assertRaises(sqlite3.DatabaseError) as caught:self.store.import_page(self.source,[RULE])
            self.assertIn('full',str(caught.exception).lower())
            self.assertEqual(snapshot(self.store.db),before)
            self.assertEqual(len(self.source.read_page()[0]),16)
        finally:self.store.db.execute('PRAGMA max_page_count=512')
        self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
        self.assertEqual(self.count('m4h_events'),32);self.assertEqual(self.count('m4h_alerts'),16)
        self.assertEqual(self.store.summary()['unevaluated'],16)

    def test_pinned_source_read_snapshot_does_not_hide_new_commits(self):
        self.upgrade();self.new_source();self.add(1)
        path=self.env.source_dir/(self.source.scope['activation']+'.sqlite')
        reader=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)
        try:
            reader.execute('BEGIN');self.assertEqual(reader.execute('SELECT count(*) FROM m3_execution').fetchone(),(1,))
            self.add(2)
            self.assertEqual(reader.execute('SELECT count(*) FROM m3_execution').fetchone(),(1,))
            self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
            self.assertEqual(self.count('m4h_alerts'),2)
            self.assertEqual(self.store.summary()['unevaluated'],16)
        finally:reader.close()


    def test_retained_backup_bytes_block_live_import_then_recover(self):
        self.upgrade();self.new_source();self.add(1)
        directory=self.directory.parent/'backups'/'accounting-test';directory.mkdir(mode=0o700)
        extra=directory/'reserved.bin'
        fd=os.open(extra,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
        try:
            os.ftruncate(fd,POLICY['max_state_bytes']*3//4)
            status=self.store.guard.observe(self.store.path,force=True)
            self.assertEqual(status['reason'],'state_budget')
            before=snapshot(self.store.db)
            with self.assertRaises(m3_storage.StoragePressure):self.store.import_page(self.source,[RULE])
            self.assertEqual(snapshot(self.store.db),before)
            os.ftruncate(fd,0)
        finally:os.close(fd)
        self.assertEqual(self.store.guard.observe(self.store.path,force=True)['state'],'normal')
        self.store.import_page(self.source,[RULE]);self.store.evaluate_pending()
        self.assertEqual(self.count('m4h_events'),17);self.assertEqual(self.count('m4h_alerts'),1)
        self.assertEqual(self.store.summary()['unevaluated'],16)

    def test_unsafe_backup_link_blocks_without_following_or_changing_history(self):
        self.upgrade();self.new_source();self.add(1)
        link=self.directory.parent/'backups'/'unsafe-link';link.symlink_to(self.directory/'handoff.sqlite')
        before=snapshot(self.store.db)
        status=self.store.guard.observe(self.store.path,force=True)
        self.assertEqual(status['state'],'unknown')
        with self.assertRaises(m3_storage.StoragePressure):self.store.import_page(self.source,[RULE])
        self.assertEqual(snapshot(self.store.db),before)

    def test_real_pinned_wal_guard_keeps_pending_until_checkpoint_recovers(self):
        self.upgrade();self.new_source();self.add(1);self.store.import_page(self.source,[RULE])
        self.store.select_evaluations(self.source,[RULE]);before=snapshot(self.store.db)
        reader=sqlite3.connect(self.store.path.as_uri()+'?mode=ro',uri=True,isolation_level=None)
        try:
            reader.execute('BEGIN');reader.execute('SELECT count(*) FROM m4h_events').fetchone()
            # Repeat the same approved header marker to generate real WAL frames
            # without altering event history, schema meaning or cursor contents.
            for n in range(4096):
                try:
                    with self.store.transaction():self.store.db.execute('PRAGMA user_version=2')
                except m3_storage.StoragePressure:break
            else:self.fail('normal WAL budget did not refuse bounded header churn')
            status=self.store.guard.observe(self.store.path,force=True)
            self.assertEqual(status['reason'],'wal_budget');self.assertEqual(status['state'],'critical')
            self.assertLess(status['wal_bytes'],POLICY['max_wal_bytes'])
            with self.assertRaises(m3_storage.StoragePressure):self.store.evaluate_pending()
            self.assertEqual(snapshot(self.store.db),before)
            self.assertEqual(self.store.summary()['pending'],1)
        finally:reader.close()
        self.store.guard.checkpoint(self.store.db,self.store.path)
        self.assertEqual(self.store.guard.observe(self.store.path,force=True)['state'],'normal')
        self.store.evaluate_pending();self.store.evaluate_pending()
        self.assertEqual(self.count('m4h_alerts'),1);self.assertEqual(self.store.summary()['pending'],0)
        self.assertEqual(self.store.summary()['unevaluated'],16)



if __name__=='__main__':unittest.main()
