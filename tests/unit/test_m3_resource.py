import json
import sqlite3
import unittest
from engine.ingestion.m3_progress import Progress, ProgressError
import test_m3_progress as fixtures


class ResourceTests(unittest.TestCase):
    A, B = fixtures.ProgressTests.A, fixtures.ProgressTests.B
    setUp = fixtures.ProgressTests.setUp
    open_ledger = fixtures.ProgressTests.open_ledger
    execution = fixtures.ProgressTests.execution
    timeout_evidence = fixtures.ProgressTests.timeout_evidence
    def evidence(self, **changes):
        value=dict(policy=1, reason='event_bytes', event_bytes_before=10, event_records_before=1,
                   trigger_begin=110, trigger_end=120, incoming_for_event=True, group_limit=15,
                   group_record_limit=64, aggregate_limit=32768, retained_accounted_bytes=4096,
                   retained_records=1, retained_record_limit=4096, requested_accounted_bytes=1034,
                   observed_active_ms=10, observed_monotonic_ms=20, paused_ms=10)
        value.update(changes)
        return value

    def admitted(self):
        self.ledger.register(self.A,100,110)
        self.ledger.register(self.A,110,120)

    def test_resource_incident_waits_for_delimiter_and_blocks_resurrection(self):
        self.admitted()
        evidence=self.evidence()
        self.assertEqual(self.ledger.resource(self.A,evidence),'resource_recorded')
        self.assertEqual(self.ledger.resource(self.A,evidence),'resource_recorded')
        self.assertEqual(self.ledger.positions(),(120,100))
        self.assertEqual(self.ledger.event_health()['discarding'],1)
        with self.assertRaises(ProgressError): self.ledger.reject(self.A)
        self.ledger.register(self.B,120,130)
        self.ledger.register(self.B,130,140,eoe=True)
        self.ledger.accept(self.B,self.execution())
        self.assertEqual(self.ledger.positions(),(140,100))
        self.ledger.register(self.A,140,150,eoe=True)
        with self.assertRaises(ProgressError): self.ledger.accept(self.A,self.execution())
        self.ledger.reject(self.A)
        self.assertEqual(self.ledger.positions(),(150,150))
        self.assertEqual(self.ledger.register(self.A,150,160,eoe=True),'suppressed')
        self.assertEqual(self.ledger.event_health(),dict(timeouts=0,late_records=1,resource_incidents=1,discarding=0,rejected_groups=1,rejection_details=1,observed_executions=0))
        self.ledger.close();self.ledger=self.open_ledger()
        self.assertEqual(self.ledger.db.execute('SELECT evidence FROM m3_resources').fetchone(),(json.dumps(evidence,sort_keys=True,separators=(',',':')),))

    def test_resource_registration_rolls_back_before_payload_release_ack(self):
        self.admitted()
        self.ledger.db.execute("CREATE TRIGGER reject_resource BEFORE INSERT ON m3_resources BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.ledger.resource(self.A,self.evidence())
        self.assertEqual(self.ledger.event_health()['resource_incidents'],0)
        self.assertEqual(self.ledger.positions(),(120,100))
        self.assertEqual(self.ledger._state(self.A),'open')

    def test_resource_context_and_accounting_must_match_admitted_positions(self):
        self.admitted()
        changes=({'event_bytes_before':9},{'event_records_before':2},{'trigger_end':121},
                 {'incoming_for_event':False},{'requested_accounted_bytes':1},{'paused_ms':0},
                 {'policy':True},{'reason':'invented'},{'raw':'forbidden'}, {'group_limit':100})
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ProgressError): self.ledger.resource(self.A,self.evidence(**change))
        self.assertEqual(self.ledger.event_health()['resource_incidents'],0)
        self.ledger.resource(self.A,self.evidence())
        with self.assertRaises(ProgressError): self.ledger.resource(self.A,self.evidence(observed_active_ms=11,paused_ms=9))

    def test_resource_cause_survives_interruption_and_late_fragments(self):
        self.admitted();self.ledger.resource(self.A,self.evidence());self.ledger.recover()
        self.assertEqual(self.ledger._state(self.A),'interrupted')
        self.assertEqual(self.ledger.event_health()['resource_incidents'],1)
        self.assertEqual(self.ledger.event_health()['discarding'],0)
        self.assertEqual(self.ledger.register(self.A,120,130,eoe=True),'suppressed')
        with self.assertRaises(ProgressError):self.ledger.accept(self.A,self.execution())

    def test_resource_cause_is_preserved_when_discard_expires(self):
        self.admitted();self.ledger.resource(self.A,self.evidence())
        self.ledger.timeout(self.A,self.timeout_evidence())
        self.assertEqual(self.ledger.event_health(),dict(timeouts=1,late_records=0,resource_incidents=1,discarding=0,rejected_groups=1,rejection_details=1,observed_executions=0))
        self.assertEqual(self.ledger._state(self.A),'rejected')

    def test_historical_ledger_does_not_invent_resource_counters(self):
        from engine.ingestion.m3_progress import event_health
        self.ledger.db.execute('DROP TABLE m3_resources')
        self.ledger.db.execute('DROP TABLE m3_event_metadata')
        self.ledger.db.execute('DROP TABLE m3_rejections')
        self.assertEqual(event_health(self.ledger.db), dict(
            timeouts=0, late_records=0, resource_incidents=None, discarding=None, rejected_groups=0, rejection_details=None, observed_executions=None))
