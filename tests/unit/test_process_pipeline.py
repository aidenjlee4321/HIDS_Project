import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from engine.ingestion import process_contract as c
from engine.database.process_store import Store,APP_ID,WRITE_RESERVE

SOURCE=dict(adapter='linux.cn_proc',mode='synthetic',source_id='11000000-0000-4000-8000-000000000001',activation_id='22000000-0000-4000-8000-000000000002',boot_id='33000000-0000-4000-8000-000000000003',profile=c.PROFILE)
PRODUCER='44000000-0000-4000-8000-000000000004'
STAMP='2026-11-13T00:00:00.000000Z'
def fixture(kind='exec'):
    what,code,typ={'fork':('PROC_EVENT_FORK',1,'creation'),'exec':('PROC_EVENT_EXEC',2,'start'),'exit':('PROC_EVENT_EXIT',2147483648,'end')}[kind]
    n=dict(what=what,what_code=code,tid=42,tgid=41,parent=None if kind=='exec' else dict(tid=30,tgid=29),cpu=4294967295,connector_sequence=4294967295,timestamp_ns='18446744073709551615',native_exit_status=4294967295 if kind=='exit' else None,native_exit_signal=0 if kind=='exit' else None)
    event_id=str(uuid.uuid4());process={'pid':41,'thread':{'id':42}}
    if n['parent']:process['parent']={'pid':29}
    return dict(protocol_version=1,message_type='event',contract_version=c.CONTRACT,ecs_reference_version='9.5.0',event_id=event_id,producer_instance_id=PRODUCER,source=copy.deepcopy(SOURCE),native=n,timestamps=dict(activity_wall_time=None,activity_wall_time_reason='not_emitted_by_source',observed_at=STAMP,observation='native_decode'),normalized=dict(event=dict(id=event_id,kind='event',category=['process'],type=[typ],action=kind,provider='linux.cn_proc',created=STAMP),process=process))
def status(**kw):
    v=dict(protocol_version=1,message_type='status',contract_version=c.CONTRACT,source=copy.deepcopy(SOURCE),producer_instance_id=PRODUCER,acknowledged=False,delivery=False,incomplete=False,stopped=False,reason='none',diagnostic_counts=[0]*20);v.update(kw);return v

class ContractTests(unittest.TestCase):
    def test_all_native_kinds_lossless_and_thread_mapping(self):
        for k in ('fork','exec','exit'):
            e=fixture(k);c.validate(c.decode(c.dump(e).encode()),SOURCE,'synthetic',PRODUCER)
            self.assertEqual(e['native']['timestamp_ns'],'18446744073709551615')
            self.assertNotEqual(e['normalized']['process']['pid'],e['normalized']['process']['thread']['id'])
    def test_zero_parent_has_no_invented_normalized_parent(self):
        e=fixture('fork');e['native']['parent']={'tid':0,'tgid':0};del e['normalized']['process']['parent'];c.validate(e,SOURCE,'synthetic')
    def test_wrong_scope_mode_producer_and_versions(self):
        for path,value in [(('source','activation_id'),str(uuid.uuid4())),(('source','mode'),'live'),(('producer_instance_id',),str(uuid.uuid4())),(('protocol_version',),True),(('contract_version',),'other'),(('ecs_reference_version',),'other')]:
            e=fixture();d=e
            for key in path[:-1]:d=d[key]
            d[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(c.Invalid):c.validate(e,SOURCE,'synthetic',PRODUCER)
    def test_native_boundaries_and_bool_rejection(self):
        for name,values in {'tid':[0,-1,2**31,True,1.0],'tgid':[0,2**31],'cpu':[-1,2**32,False],'connector_sequence':[2**32,1.0],'timestamp_ns':['01','-1','18446744073709551616',1],'what_code':[True,1],'native_exit_status':[0],'parent':[{}]}.items():
            for value in values:
                e=fixture();e['native'][name]=value
                with self.subTest(name=name,value=value),self.assertRaises(c.Invalid):c.validate(e,SOURCE,'synthetic')
    def test_mapping_forgery_and_extra_fields_rejected(self):
        cases=[]
        for name,value in [('pid',42),('pid',True),('pid',41.0),('executable','/bin/sh')]:
            e=fixture();e['normalized']['process'][name]=value;cases.append(e)
        e=fixture();e['normalized']['event']['created']='2026-11-12T00:00:00.000000Z';cases.append(e)
        e=fixture();e['native']['args']=[];cases.append(e)
        e=fixture();e['timestamps']['activity_wall_time']=STAMP;cases.append(e)
        for e in cases:
            with self.assertRaises(c.Invalid):c.validate(e,SOURCE,'synthetic')
    def test_calendar_and_observation_reason(self):
        for t in ('0000-01-01T00:00:00.000000Z','2026-02-29T00:00:00.000000Z','2026-11-13T00:00:60.000000Z','2026-11-13T00:00:00Z'):
            e=fixture();e['timestamps']['observed_at']=t;e['normalized']['event']['created']=t
            with self.assertRaises(c.Invalid):c.validate(e,SOURCE,'synthetic')
    def test_closed_json_parser(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{}\n',b'{}\r',b'\xef\xbb\xbf{}',br'{"x":"\ud800"}',b'{"x":'+b'['*9+b'0'+b']'*9+b'}',b'x'*16385):
            with self.subTest(raw=raw[:30]),self.assertRaises(c.Invalid):c.decode(raw)
    def test_status_types_and_no_raw_diagnostics(self):
        c.status(status(),SOURCE,PRODUCER,'synthetic')
        for k,v in [('incomplete',1),('reason','raw process payload'),('extra','text')]:
            s=status();s[k]=v
            with self.assertRaises(c.Invalid):c.status(s,SOURCE,PRODUCER,'synthetic')

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hids-process-unit.');self.dir=Path(self.tmp.name).resolve();self.dir.chmod(0o700);self.store=None
    def tearDown(self):
        if self.store:self.store.close()
        self.tmp.cleanup()
    def open(self,**kw):
        self.store=Store(self.dir/'store.sqlite',SOURCE,'synthetic',**kw);return self.store
    def test_commit_duplicate_conflict_and_restart(self):
        s=self.open();e=fixture();self.assertEqual(s.put(e,STAMP),('stored',1));self.assertEqual(s.put(e,STAMP),('duplicate',1))
        other=copy.deepcopy(e);other['native']['connector_sequence']=1
        with self.assertRaises(c.Invalid) as x:s.put(other)
        self.assertEqual(x.exception.code,'id_conflict');s.close();s=self.open();self.assertEqual(s.put(e),('duplicate',1))
    def test_receipt_and_observation_roles_no_activity_fallback(self):
        s=self.open();e=fixture();receipt='2025-01-01T00:00:00.000000Z';s.put(e,receipt)
        row=s.conn.execute('SELECT observed_at,received_at,envelope FROM process_events').fetchone()
        self.assertEqual(row[:2],(STAMP,receipt));self.assertIsNone(json.loads(row[2])['timestamps']['activity_wall_time'])
    def test_before_commit_failure_rolls_back(self):
        def fail(stage):
            if stage=='before_commit':raise OSError('fixture')
        s=self.open(fault=fail);e=fixture()
        with self.assertRaises(OSError):s.put(e)
        self.assertEqual(s.conn.execute('SELECT count(*) FROM process_events').fetchone()[0],0)
        s.fault=lambda stage:None;self.assertEqual(s.put(e)[0],'stored')
    def test_after_commit_uncertain_retry_resolves_same_id(self):
        def fail(stage):
            if stage=='after_commit':raise OSError('fixture')
        s=self.open(fault=fail);e=fixture()
        with self.assertRaises(OSError):s.put(e)
        s.fault=lambda stage:None;self.assertEqual(s.put(e),('duplicate',1))
    def test_capacity_preserves_old_rows_and_duplicate(self):
        s=self.open(max_events=1);e=fixture();s.put(e)
        with self.assertRaises(c.Invalid) as x:s.put(fixture('exit'))
        self.assertEqual(x.exception.code,'capacity_exceeded');self.assertEqual(s.put(e)[0],'duplicate')
        self.assertEqual(s.conn.execute('SELECT count(*) FROM process_events').fetchone()[0],1)
    def test_space_pressure_before_write_and_duplicate_resolution(self):
        s=self.open();e=fixture();s.put(e);s.space=lambda:0
        with self.assertRaises(c.Invalid):s.put(fixture())
        self.assertEqual(s.put(e)[0],'duplicate')
    def test_untrusted_files_and_hardlinks_refused(self):
        s=self.open();p=self.dir/'foreign';p.write_text('x');p.chmod(0o644)
        with self.assertRaises(c.Invalid):s.put(fixture())
        p.chmod(0o600);os.link(p,self.dir/'linked')
        with self.assertRaises(c.Invalid):s.put(fixture())
    def test_unknown_schema_refused_without_repair(self):
        s=self.open();s.conn.execute('CREATE TABLE unexpected(x)');s.close()
        with self.assertRaises(c.Invalid):self.open()
        db=sqlite3.connect(self.dir/'store.sqlite');self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='unexpected'").fetchone());db.close()
    def test_foreign_application_id_refused(self):
        s=self.open();s.conn.execute('PRAGMA application_id=42');s.close()
        with self.assertRaises(c.Invalid):self.open()
    def test_interval_sticky_failure_and_ack_independent_delivery(self):
        s=self.open();s.interval(status(delivery=True,incomplete=True,reason='native_gap'),PRODUCER);s.interval(status(stopped=True,reason='stopped'),PRODUCER)
        self.assertEqual(s.conn.execute('SELECT acknowledged,delivery,incomplete,stopped FROM process_intervals').fetchone(),(0,1,1,1))
        with self.assertRaises(c.Invalid):s.interval(status(),PRODUCER)
    def test_private_files_and_sidecars(self):
        self.open()
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in self.dir.iterdir()))
    def test_real_writer_contention_rollback(self):
        s=self.open();other=sqlite3.connect(self.dir/'store.sqlite',isolation_level=None);other.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(sqlite3.OperationalError):s.put(fixture())
        finally:other.execute('ROLLBACK');other.close()
        self.assertEqual(s.put(fixture())[0],'stored')
    def test_symlink_database_refused(self):
        target=self.dir/'target';target.write_text('');target.chmod(0o600);(self.dir/'store.sqlite').symlink_to(target)
        with self.assertRaises((PermissionError,c.Invalid)):self.open()

if __name__=='__main__':unittest.main()
