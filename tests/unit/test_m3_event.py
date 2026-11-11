import json
import sqlite3
import unittest
from unittest import mock
from engine.ingestion import m3_event
from engine.ingestion.m3_progress import ProgressError
from engine.ingestion.m2_contract import frame
import test_m3_progress as fixtures


class EventMetadataTests(unittest.TestCase):
    A,B=fixtures.ProgressTests.A,fixtures.ProgressTests.B
    setUp=fixtures.ProgressTests.setUp
    open_ledger=fixtures.ProgressTests.open_ledger
    execution=fixtures.ProgressTests.execution

    def observation(self,**changes):
        value=dict(version=1,arch=m3_event.ARCH,profile=m3_event.PROFILE,first_observed_unix_ns=123456789)
        value.update(changes)
        return value

    def eligible(self):
        self.ledger.register(self.A,100,110)
        self.ledger.register(self.A,110,120,eoe=True)

    def test_distinct_clocks_and_architecture_are_atomic_and_immutable_on_retry(self):
        self.eligible()
        observation=self.observation()
        receipt='2026-11-11T02:00:00.000000Z'
        started='2026-11-11T01:00:00.000001Z'
        with mock.patch('engine.ingestion.m3_progress.utc_now',return_value=started):
            self.assertEqual(self.ledger.accept(self.A,self.execution(),observation=observation,received_at=receipt),'accepted')
        row=self.ledger.db.execute('SELECT * FROM m3_event_metadata').fetchone()
        self.assertEqual(row,(self.A,1,m3_event.ARCH,m3_event.PROFILE,123456789,receipt,started))
        self.assertEqual(self.ledger.accept(self.A,self.execution(),observation=observation),'duplicate')
        changed=dict(observation,first_observed_unix_ns=123456790)
        with self.assertRaises(ProgressError):self.ledger.accept(self.A,self.execution(),observation=changed)
        self.assertEqual(self.ledger.accept(self.A,self.execution()),'duplicate')
        self.assertEqual(self.ledger.db.execute('SELECT * FROM m3_event_metadata').fetchone(),row)
        self.assertEqual(self.ledger.event_health()['observed_executions'],1)

    def test_closed_metadata_rejects_untrusted_values_without_acceptance(self):
        self.eligible()
        base=self.observation()
        for changes in ({'version':True},{'version':2},{'arch':True},{'arch':0xc000003e},
                        {'first_observed_unix_ns':-1},{'first_observed_unix_ns':2**63},
                        {'profile':'untrusted'},{'argv':['private']}):
            with self.subTest(changes=changes),self.assertRaises(ProgressError):
                self.ledger.accept(self.A,self.execution(),observation=dict(base,**changes))
        with self.assertRaises(ProgressError):self.ledger.accept(self.A,self.execution(),received_at='not a timestamp')
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM m3_execution').fetchone(),(0,))
        self.assertEqual(self.ledger.positions(),(120,100))

    def test_metadata_insert_failure_rolls_back_execution_and_frontier(self):
        self.ledger.register(self.A,100,110)
        self.ledger.register(self.B,110,120,eoe=True)
        self.ledger.accept(self.B,self.execution())
        self.ledger.register(self.A,120,130,eoe=True)
        self.ledger.db.execute("CREATE TRIGGER fail_event_metadata BEFORE INSERT ON m3_event_metadata BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.ledger.accept(self.A,self.execution(),observation=self.observation())
        self.assertEqual(self.ledger.db.execute('SELECT identity FROM m3_execution').fetchall(),[(self.B,)])
        self.assertEqual(self.ledger.db.execute('SELECT identity FROM m3_event_metadata').fetchall(),[(self.B,)])
        self.assertEqual(self.ledger.positions(),(130,100))
        self.ledger.db.execute('DROP TRIGGER fail_event_metadata');self.ledger.recover()
        self.assertEqual(self.ledger._state(self.A),'interrupted')

    def test_rejection_cause_is_closed_atomic_and_not_replaceable(self):
        self.eligible()
        for reason in ('raw_private_data','argv=secret',True):
            with self.assertRaises(ProgressError):self.ledger.reject(self.A,reason=reason)
        self.ledger.db.execute("CREATE TRIGGER fail_rejection BEFORE INSERT ON m3_rejections BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.ledger.reject(self.A,reason='invalid_syscall')
        self.assertEqual(self.ledger._state(self.A),'open')
        self.ledger.db.execute('DROP TRIGGER fail_rejection')
        self.ledger.reject(self.A,reason='invalid_syscall')
        row=self.ledger.db.execute('SELECT * FROM m3_rejections').fetchone()
        self.ledger.reject(self.A,reason='invalid_syscall')
        with self.assertRaises(ProgressError):self.ledger.reject(self.A,reason='invalid_path_record')
        self.assertEqual(self.ledger.db.execute('SELECT * FROM m3_rejections').fetchone(),row)
        self.assertEqual(self.ledger.positions(),(120,120))

    def test_root_diagnostics_are_bounded_and_do_not_include_payloads(self):
        for index in range(24):
            identity=f'1.001:{index+1}';begin=100+index*10
            self.ledger.register(identity,begin,begin+10,eoe=True)
            self.ledger.reject(identity,reason='execve_missing_argc')
        result=m3_event.diagnostics(self.ledger.db)
        self.assertEqual(len(result['items']),20)
        self.assertTrue(result['truncated'])
        m3_event.validate_diagnostics(result)
        maximum=dict(result,items=[dict(identity='18446744073709551615.123456789:18446744073709551615',
            reason='unsupported_execution_record',recorded_at='2026-11-11T01:00:00.000000Z') for _ in range(20)])
        response=dict(version=3,result='diagnostics',source='7d9b6873-c6a0-4e9a-88ab-5ec2c04dc592',
            activation='47e48803-cdf5-44c5-8b08-f873575470e7',**maximum)
        self.assertLessEqual(len(frame(response,4096)),4096)
        self.assertNotIn('payload',json.dumps(result))

    def test_legacy_history_is_not_backfilled_with_guessed_metadata(self):
        self.eligible();self.ledger.accept(self.A,self.execution())
        self.ledger.db.execute('DROP TABLE m3_event_metadata')
        self.ledger.close();self.ledger=self.open_ledger()
        self.assertEqual(self.ledger.accept(self.A,self.execution()),'duplicate')
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM m3_event_metadata').fetchone(),(0,))
        with self.assertRaises(ProgressError):self.ledger.accept(self.A,self.execution(),observation=self.observation())


if __name__=='__main__':unittest.main()
