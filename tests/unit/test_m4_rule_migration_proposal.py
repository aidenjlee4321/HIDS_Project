"""Test-only verification of proposed D-07 SQL, never a production migrator."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from engine.detection.m4_handoff import DDL
from engine.detection.m4_pilot import canonical,digest,load_json
from engine.detection.m4_service import LiveStore

ROOT=Path(__file__).resolve().parents[2]
REVIEW=ROOT/'docs/implementation/m4-first-rule-review.md'


def proposed_sql():
    return REVIEW.read_text().split('```sql\n',1)[1].split('\n```',1)[0]


def proposed_migration(db,backup,*,fail_after=None,crash=None):
    """Private fixture only: backup, explicit transaction and injected boundaries."""
    fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd)
    copy=sqlite3.connect(backup)
    try:db.backup(copy,pages=16)
    finally:copy.close()
    # Finalize only the NEW backup as a standalone read-only-inspectable snapshot.
    # Some SQLite versions cannot open a WAL-mode backup read-only without sidecars.
    copy=sqlite3.connect(backup,isolation_level=None)
    try:
        if copy.execute('PRAGMA journal_mode=DELETE').fetchone()!=('delete',):raise RuntimeError('backup finalization failed')
        if copy.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise RuntimeError('backup integrity failed')
    finally:copy.close()
    db.execute('BEGIN IMMEDIATE')
    try:
        for n,statement in enumerate((s.strip() for s in proposed_sql().split(';') if s.strip()),1):
            db.execute(statement)
            if n==fail_after:raise RuntimeError('injected migration interruption')
            if n==4 and crash=='during':os.kill(os.getpid(),signal.SIGKILL)
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:db.execute('ROLLBACK')
        raise
    if crash=='after':os.kill(os.getpid(),signal.SIGKILL)


class MigrationProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hids-m4-rule-migration-proposal.')
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name).resolve();self.path=self.directory/'handoff.sqlite';self.path.touch(mode=0o600)
        self.db=sqlite3.connect(self.path,isolation_level=None)
        self.addCleanup(lambda:self.db.close())
        self.db.execute('PRAGMA foreign_keys=ON');self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('BEGIN IMMEDIATE;'+DDL+'PRAGMA application_id=0x48344c31;PRAGMA user_version=1;COMMIT;')
        fixture=load_json(ROOT/'tests/fixtures/m4/execution.json')
        scope={k:fixture[k] for k in ('source','activation','generation')}
        binding=digest('hids.m4.live.binding/1',scope)
        self.db.execute('INSERT INTO m4h_bindings VALUES (?,?,?,?)',(binding,canonical(scope),'/synthetic/source',canonical(dict(boundary=0,settled=160,target=None,after=159,seen_frontier=160,seen_scanned=160,fingerprint=[[1,1],[1,2],[1,3]]))))
        for n in range(16):
            envelope=dict(format='m4.audit-exec-handoff/1',origin='audit_plugin',**scope,identity=f'1.001:{n+1}',first_offset=n*10,
                          execution=fixture['execution'],metadata=dict(format=1,arch=0xc00000b7,profile=fixture['profile'],first_observed_unix_ns=123,
                          received_at='2026-11-11T00:00:00Z',persistence_started_at='2026-11-11T00:00:00Z'))
            key=digest('hids.m4.live.event/1',[envelope[k] for k in ('source','activation','generation','identity')])
            self.db.execute('INSERT INTO m4h_events VALUES (?,?,?,?,?,?,?)',(key,binding,envelope['identity'],n*10,canonical(envelope),digest('hids.m4.live.content/1',envelope),'2026-11-11T00:00:00Z'))
        self.original=self.events()

    def events(self):return self.db.execute('SELECT * FROM m4h_events ORDER BY event_key').fetchall()

    def assert_state(self,version):
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone(),(version,))
        self.assertEqual(self.db.execute('PRAGMA application_id').fetchone(),(0x48344c31,))
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.events(),self.original)

    def test_upgrade_preserves_all_events_and_existing_schema_valid_demo_alert(self):
        key=self.original[0][0];rule=load_json(ROOT/'rules/pilot/configured-executable.json')
        self.db.execute('INSERT INTO m4h_rules VALUES (?,?,?,?)',(rule['id'],rule['revision'],canonical(rule),digest('hids.m4.live.rule/1',rule)))
        self.db.execute("INSERT INTO m4h_evaluations VALUES (?,?,?,'matched','fixture','2026-11-11T00:00:00Z')",(key,rule['id'],rule['revision']))
        self.db.execute("INSERT INTO m4h_alerts VALUES ('fixture-alert',?,?,?,'demo','{}',1,'informational','2026-11-11T00:00:00Z')",(key,rule['id'],rule['revision']))
        alert=self.db.execute('SELECT * FROM m4h_alerts').fetchall()
        proposed_migration(self.db,self.directory/'before.sqlite')
        self.assert_state(2)
        self.assertEqual(self.db.execute('SELECT rule_plan FROM m4h_bindings').fetchall(),[('[]',)])
        self.assertEqual(self.db.execute('SELECT * FROM m4h_alerts').fetchall(),alert)
        with self.assertRaises(ValueError):LiveStore._identity(self.db)  # Current v1 code refuses v2.

    def test_backup_sees_committed_WAL_and_remains_v1(self):
        backup=self.directory/'before.sqlite';proposed_migration(self.db,backup)
        db=sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True)
        try:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone(),(1,))
            self.assertEqual(db.execute('SELECT * FROM m4h_events ORDER BY event_key').fetchall(),self.original)
            self.assertEqual(db.execute('SELECT count(*) FROM m4h_rules').fetchone(),(0,))
        finally:db.close()
        self.assert_state(2)

    def test_existing_backup_refuses_before_schema_writes(self):
        backup=self.directory/'before.sqlite';backup.write_bytes(b'preserve existing backup')
        with self.assertRaises(FileExistsError):proposed_migration(self.db,backup)
        self.assertEqual(backup.read_bytes(),b'preserve existing backup');self.assert_state(1)

    def test_failure_after_new_table_rolls_back_entire_schema(self):
        with self.assertRaises(RuntimeError):proposed_migration(self.db,self.directory/'before.sqlite',fail_after=2)
        self.assert_state(1)
        self.assertNotIn('rule_plan',[r[1] for r in self.db.execute('PRAGMA table_info(m4h_bindings)')])
        self.assertEqual(self.db.execute("SELECT count(*) FROM sqlite_master WHERE name='m4h_alerts_v2'").fetchone(),(0,))

    def crash(self,stage):
        self.db.close()
        code='''import sys,sqlite3
from pathlib import Path
from test_m4_rule_migration_proposal import proposed_migration
p=Path(sys.argv[1]);db=sqlite3.connect(p/'handoff.sqlite',isolation_level=None)
db.execute('PRAGMA foreign_keys=ON')
proposed_migration(db,p/'before.sqlite',crash=sys.argv[2])
'''
        child=subprocess.run([sys.executable,'-B','-c',code,str(self.directory),stage],cwd=ROOT,
                             env={**os.environ,'PYTHONPATH':str(ROOT/'tests/unit')+os.pathsep+str(ROOT)},capture_output=True,timeout=15)
        self.assertEqual(child.returncode,-signal.SIGKILL,child.stderr.decode())
        self.db=sqlite3.connect(self.path,isolation_level=None);self.db.execute('PRAGMA foreign_keys=ON')
        self.assert_state(1 if stage=='during' else 2)

    def test_actual_sigkill_after_old_table_drop_before_commit_is_intact_v1(self):self.crash('during')
    def test_actual_sigkill_after_commit_is_complete_v2(self):self.crash('after')


if __name__=='__main__':unittest.main()
