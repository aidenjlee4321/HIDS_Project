import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest import mock
from engine.ingestion import m3_health,m3_storage
from engine.ingestion.m3_runtime import Runtime

SOURCE='7d9b6873-c6a0-4e9a-88ab-5ec2c04dc592'


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name).resolve()
        # Unit WAL/recovery expectations must not depend on host disk pressure.
        # Explicit space-level tests override this; installed VM tests use statvfs.
        available=mock.patch.object(m3_storage.Guard,'_available',return_value=2*1024*m3_storage.MIB)
        available.start();self.addCleanup(available.stop)

    def runtime(self,**kw):
        return Runtime(self.directory,SOURCE,max_activations=2,max_pages=64,position_limit=32,**kw)

    def sample(self,runtime,activation,generation,tick):
        m3_health.record(runtime.db,activation,generation,
            dict(sample_ns=tick,kernel=dict(state='observed',boot_id=SOURCE,
                auditd_pid=42,lost=0,backlog=0,backlog_limit=64,enabled=1),
                dispatcher=dict(state='missing')),now_ns=tick)

    def test_provisional_policy_requires_explicit_space_and_transaction_reserves(self):
        options=m3_storage.defaults(64,2)
        m3_storage.validate(options,64,2)
        for bad in (dict(options,minimum_free_bytes=True),dict(options,max_wal_bytes=1),
                    dict(options,critical_free_bytes=options['minimum_free_bytes']),
                    dict(options,extra=1),list(options.items())):
            with self.subTest(bad=type(bad)),self.assertRaises(ValueError):m3_storage.validate(bad,64,2)

    def test_cached_totals_track_growth_removal_and_full_rescan(self):
        now=[0.]
        guard=m3_storage.Guard(self.directory,64,256,clock=lambda:now[0])
        for index in range(200):
            path=self.directory/f'old-{index}.fixture';path.write_bytes(b'x');path.chmod(0o600)
        database=self.directory/'active.sqlite';database.write_bytes(b'x');database.chmod(0o600)
        first=guard.observe(database);self.assertEqual(first['state_bytes'],sum(guard.files.values()))
        wal=Path(str(database)+'-wal');wal.write_bytes(b'x'*8192);wal.chmod(0o600)
        grown=guard.observe(database);self.assertEqual(grown['state_bytes'],sum(guard.files.values()))
        self.assertEqual(grown['wal_bytes'],max(wal.stat().st_size,wal.stat().st_blocks*512))
        wal.unlink();removed=guard.observe(database)
        self.assertEqual(removed['wal_bytes'],0);self.assertEqual(removed['state_bytes'],first['state_bytes'])
        new=self.directory/'retained.sqlite-wal';new.write_bytes(b'x'*16384);new.chmod(0o600)
        now[0]=2;rescanned=guard.observe()
        self.assertEqual(rescanned['state_bytes'],sum(guard.files.values()))
        self.assertEqual(rescanned['wal_bytes'],max(new.stat().st_size,new.stat().st_blocks*512))
        new.chmod(0o644);now[0]=4;self.assertEqual(guard.observe()['state'],'unknown')
        new.chmod(0o600);self.assertEqual(guard.observe()['state_bytes'],sum(guard.files.values()))

    def test_free_space_levels_and_inspection_failure_are_distinct(self):
        guard=m3_storage.Guard(self.directory,64,2)
        for free,expected in ((2*1024*m3_storage.MIB,'normal'),(900*m3_storage.MIB,'warning'),
                              (512*m3_storage.MIB,'critical'),(256*m3_storage.MIB,'exhausted')):
            guard.space=lambda:free
            self.assertEqual(guard.observe()['state'],expected)
            if expected in ('critical','exhausted'):
                with self.assertRaises(m3_storage.StoragePressure):guard.before(self.directory/'a.sqlite')
        guard.space=mock.Mock(side_effect=OSError('injected'))
        status=guard.observe()
        self.assertEqual(status['state'],'unknown')
        self.assertIsNone(status['available_bytes'])
        with self.assertRaises(m3_storage.StoragePressure):guard.before(self.directory/'a.sqlite')
        m3_storage.validate_status(status)

    def test_pinned_reader_stops_wal_growth_before_budget_and_preserves_latest_commit(self):
        policy=m3_storage.defaults(64,2)
        policy['max_wal_bytes']=8*((64+2)*(4096+24)+32)
        runtime=self.runtime(storage=policy)
        reader=None
        try:
            activation=str(uuid.uuid4());interval=runtime.activate(activation)
            self.sample(runtime,activation,interval['generation'],100)
            reader=sqlite3.connect(runtime.path.as_uri()+'?mode=ro',uri=True,isolation_level=None)
            reader.execute('BEGIN');reader.execute('SELECT * FROM m3_health').fetchall()
            warning=False;last=100
            for tick in range(101,1001):
                try:self.sample(runtime,activation,interval['generation'],tick)
                except m3_storage.StoragePressure:break
                last=tick
                warning |= runtime.storage.observe()['state']=='warning'
            else:self.fail('pinned WAL never reached proactive stop')
            status=runtime.storage.observe()
            self.assertTrue(warning)
            self.assertEqual(status['state'],'critical')
            self.assertEqual(status['reason'],'wal_budget')
            self.assertLess(status['wal_bytes'],policy['max_wal_bytes'])
            observation=runtime.db.execute('SELECT observation FROM m3_health').fetchone()[0]
            self.assertEqual(json.loads(observation)['sample_ns'],last)
            before=Path(str(runtime.path)+'-wal').stat().st_size
            with self.assertRaises(m3_storage.StoragePressure):self.sample(runtime,activation,interval['generation'],last+1)
            self.assertEqual(Path(str(runtime.path)+'-wal').stat().st_size,before)
            reader.execute('ROLLBACK');reader.close();reader=None
            runtime.storage.last_checkpoint.clear()
            runtime.storage.checkpoint(runtime.db,runtime.path)
            self.assertEqual(runtime.storage.observe()['state'],'normal')
            self.assertEqual(runtime.db.execute('SELECT COUNT(*) FROM m3_health').fetchone(),(1,))
            self.assertEqual(runtime.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
        finally:
            if reader:reader.close()
            runtime.close()

    def test_unpinned_fast_writer_checkpoints_without_false_pressure_stop(self):
        policy=m3_storage.defaults(64,2)
        policy['max_wal_bytes']=8*((64+2)*(4096+24)+32)
        runtime=self.runtime(storage=policy)
        try:
            activation=str(uuid.uuid4());interval=runtime.activate(activation)
            for tick in range(100,1100):self.sample(runtime,activation,interval['generation'],tick)
            self.assertLess(runtime.storage.observe()['wal_bytes'],policy['max_wal_bytes'])
            self.assertEqual(runtime.db.execute('SELECT COUNT(*) FROM m3_health').fetchone(),(1,))
            self.assertEqual(runtime.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
        finally:runtime.close()

    def test_existing_low_space_startup_retains_status_and_requires_explicit_restart(self):
        runtime=self.runtime();activation=str(uuid.uuid4());runtime.activate(activation)
        runtime.claim();runtime.progress.register('1.001:1',0,10)
        runtime.close()
        with mock.patch.object(m3_storage.Guard,'_available',return_value=256*m3_storage.MIB):
            runtime=self.runtime()
            try:
                self.assertTrue(runtime.read_only)
                status=runtime.status()
                self.assertEqual(status['storage']['state'],'exhausted')
                self.assertFalse(status['source_ready'])
                self.assertTrue(status['possible_gap'])
                with self.assertRaises(m3_storage.StoragePressure):runtime.claim()
                with self.assertRaises(m3_storage.StoragePressure):runtime.activate(str(uuid.uuid4()))
                with self.assertRaises(m3_storage.StoragePressure):runtime.db.execute("UPDATE m3_intervals SET state='ready'")
            finally:runtime.close()
        runtime=self.runtime()
        try:
            self.assertFalse(runtime.read_only)
            self.assertEqual(runtime.current()['state'],'interrupted')
            self.assertEqual(runtime.current()['code'],'backend_restart')
            self.assertFalse(runtime.status()['source_ready'])
            self.assertEqual(runtime.storage.observe()['state'],'normal')
        finally:runtime.close()

    def test_directory_budget_and_unsafe_files_block_without_deletion(self):
        guard=m3_storage.Guard(self.directory,64,2)
        file=self.directory/'retained.sqlite';file.write_bytes(b'x');file.chmod(0o600)
        guard.options['max_state_bytes']=1
        self.assertEqual(guard.observe(force=True)['state'],'exhausted')
        self.assertTrue(file.exists())
        file.chmod(0o644)
        self.assertEqual(guard.observe(force=True)['state'],'unknown')
        self.assertTrue(file.exists())


if __name__=='__main__':unittest.main()
