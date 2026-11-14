"""Finite synthetic-pilot acceptance, including actual abrupt process termination."""
import base64
import copy
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from engine.detection.m4_pilot import Invalid, Store, evaluate, event_key, load_json, validate_event, validate_rule

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests/fixtures/m4/execution.json'
RULE = ROOT / 'rules/pilot/configured-executable.json'


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hids-m4-test.')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve() / 'store'
        self.event, self.rule = load_json(FIXTURE), load_json(RULE)
        self.store = Store(self.directory, create=True)
        self.addCleanup(lambda: self.store.close())

    def receive(self):
        return self.store.receive(self.event, self.rule)

    def run_event(self):
        key = self.receive()
        return self.store.evaluate(key, self.rule['id'], self.rule['revision'])

    def counts(self):
        return tuple(self.store.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                     for table in ('m4p_events', 'm4p_evaluations', 'm4p_alerts'))

    def test_match_linkage_explanation_snapshot_and_processing_clocks(self):
        self.assertEqual(self.run_event(), 'matched')
        self.assertEqual(self.counts(), (1, 1, 1))
        row = self.store.db.execute('''SELECT a.event_key,a.explanation,a.matched_values,a.demo,a.severity,
            r.definition,e.payload,e.received_at,a.created_at FROM m4p_alerts a
            JOIN m4p_events e USING(event_key) JOIN m4p_rules r USING(rule_id,revision)''').fetchone()
        self.assertEqual(row[0], event_key(self.event))
        self.assertEqual(row[1], self.rule['explanation'])
        self.assertEqual(json.loads(row[2]), {'exe_base64': self.event['execution']['exe_base64']})
        self.assertEqual(row[3:5], (1, 'informational'))
        self.assertEqual(json.loads(row[5]), self.rule)
        self.assertEqual(json.loads(row[6]), self.event)
        self.assertTrue(row[7] and row[8])
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_nonmatch(self):
        self.event['execution']['exe_base64'] = base64.b64encode(b'/bin/other').decode()
        self.assertEqual(self.run_event(), 'no_match')
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_unknown_required_checked_before_false_predicate(self):
        self.rule['required'].append('auid')
        self.rule['all_of'].append({'field': 'auid', 'eq': 1000})
        self.event['execution']['exe_base64'] = base64.b64encode(b'/other').decode()
        self.assertEqual(self.run_event(), 'unable')
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_known_auid_and_optional_unknown(self):
        self.assertEqual(self.run_event(), 'matched')  # Unknown auid is not required.
        self.rule['revision'] = '2'
        self.rule['required'] = ['auid']
        self.rule['all_of'] = [{'field': 'auid', 'eq': 1000}]
        self.event['identity'] = '1.001:2'
        self.event['execution']['auid'] = 1000
        self.assertEqual(self.run_event(), 'matched')

    def test_invalid_events_never_persist(self):
        variants = []
        for key, value in [('version', True), ('version', 2), ('synthetic', False),
                           ('profile', 'unknown'), ('source', 'invalid'), ('generation', True),
                           ('identity', '42'), ('unexpected', 1)]:
            e = copy.deepcopy(self.event); e[key] = value; variants.append(e)
        for key, value in [('pid', True), ('pid', 0), ('uid', -1), ('success', 1),
                           ('exe_base64', '%%%'), ('exe_base64', 'eAA='), ('result', 1)]:
            e = copy.deepcopy(self.event); e['execution'][key] = value; variants.append(e)
        e = copy.deepcopy(self.event); del e['execution']['auid']; variants.append(e)
        for e in variants:
            with self.subTest(event=e), self.assertRaises((Invalid, ValueError)):
                self.store.receive(e, self.rule)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_unsupported_rules_rejected_before_persistence(self):
        variants = []
        for key, value in [('version', True), ('severity', 'high'), ('demo', False),
                           ('profile', 'unknown'), ('script', 'run()'), ('required', ['history']),
                           ('required', ['uid', 'uid']), ('all_of', []), ('all_of', [None]),
                           ('explanation', 'bad\ntext')]:
            r = copy.deepcopy(self.rule); r[key] = value; variants.append(r)
        for predicate in ({'field': 'uid', 'eq': True}, {'field': 'uid', 'gt': 3},
                          {'field': 'history', 'eq': 1}, {'field': 'exe_base64', 'eq': 'eAA='},
                          {'field': 'success', 'eq': 1}, {'field': [], 'eq': 'x'}):
            r = copy.deepcopy(self.rule); r['all_of'] = [predicate]
            if type(predicate['field']) is str and predicate['field'] in ('uid', 'success'):
                r['required'] = [predicate['field']]
            variants.append(r)
        for r in variants:
            with self.subTest(rule=r), self.assertRaises(Invalid):
                self.store.receive(self.event, r)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_duplicate_delivery_and_evaluation_after_reopen(self):
        self.assertEqual(self.run_event(), 'matched')
        key = self.receive()
        self.store.close(); self.store = Store(self.directory)
        self.assertEqual(self.receive(), key)
        self.assertEqual(self.store.evaluate(key, self.rule['id'], self.rule['revision']), 'matched')
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_event_conflict_rolls_back_new_rule(self):
        key = self.receive()
        self.rule['revision'] = 'new'
        self.event['execution']['uid'] += 1
        with self.assertRaisesRegex(Invalid, 'event identity conflict'):
            self.receive()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM m4p_rules').fetchone()[0], 1)
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.store.db.execute('SELECT event_key FROM m4p_events').fetchone()[0], key)

    def test_rule_revision_conflict_preserves_old_finding(self):
        self.run_event()
        self.rule['explanation'] = 'Changed meaning'
        with self.assertRaisesRegex(Invalid, 'rule revision conflict'):
            self.receive()
        self.assertEqual(self.store.db.execute('SELECT explanation FROM m4p_alerts').fetchone()[0], 'Configured executable matched (demo).')
        self.rule['revision'] = '2'
        self.assertEqual(self.run_event(), 'matched')
        self.assertEqual(self.counts(), (1, 2, 2))

    def test_scope_identity_separates_source_activation_generation_and_native(self):
        original = copy.deepcopy(self.event)
        keys = {self.receive()}
        for field in ('source', 'activation', 'generation'):
            self.event = copy.deepcopy(original)
            self.event[field] = '00000000-0000-4000-8000-000000000099'
            keys.add(self.receive())
        self.event = copy.deepcopy(original); self.event['identity'] = '1.001:2'
        keys.add(self.receive())
        self.assertEqual(len(keys), 5)
        self.assertEqual(self.counts(), (5, 5, 0))

    def test_alert_failure_rolls_back_completion_then_retry(self):
        key = self.receive()
        self.store.db.execute("CREATE TRIGGER fail_alert BEFORE INSERT ON m4p_alerts BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.evaluate(key, self.rule['id'], self.rule['revision'])
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.store.db.execute('SELECT state FROM m4p_evaluations').fetchone()[0], 'pending')
        self.store.db.execute('DROP TRIGGER fail_alert')
        self.assertEqual(self.store.evaluate(key, self.rule['id'], self.rule['revision']), 'matched')
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_event_commit_failure_leaves_no_partial_work(self):
        self.store.db.execute("CREATE TRIGGER fail_work BEFORE INSERT ON m4p_evaluations BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.receive()
        self.assertEqual(self.counts(), (0, 0, 0))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM m4p_rules').fetchone()[0], 0)

    def test_evaluator_error_is_explicit_not_nonmatch(self):
        key = self.receive()
        with patch('engine.detection.m4_pilot.evaluate', side_effect=RuntimeError('sensitive details')):
            self.assertEqual(self.store.evaluate(key, self.rule['id'], self.rule['revision']), 'error')
        self.assertEqual(self.store.db.execute('SELECT reason FROM m4p_evaluations').fetchone()[0], 'evaluation_failed')
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_stored_payload_hash_conflict_is_error(self):
        key = self.receive()
        self.store.db.execute("UPDATE m4p_events SET payload_hash='invalid'")
        self.assertEqual(self.store.evaluate(key, self.rule['id'], self.rule['revision']), 'error')
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_unknown_rule_cannot_be_evaluated(self):
        key = self.receive()
        with self.assertRaises(Invalid):
            self.store.evaluate(key, 'not.enabled', '1')

    def test_private_files_wal_and_exclusive_writer(self):
        self.receive()
        self.assertEqual(self.store.db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        self.assertEqual(self.store.db.execute('PRAGMA synchronous').fetchone()[0], 2)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        for p in self.directory.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        with self.assertRaises(BlockingIOError):
            Store(self.directory)
        with self.assertRaises(FileExistsError):
            Store(self.directory, create=True)

    def test_unknown_version_refused_without_changing_database(self):
        self.receive(); self.store.db.execute('PRAGMA user_version=99'); self.store.close()
        before = self.store.path.read_bytes()
        with self.assertRaises(Invalid):
            Store(self.directory)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_foreign_database_refused_unchanged(self):
        self.store.close()
        foreign = Path(self.temp.name).resolve() / 'foreign'; foreign.mkdir(mode=0o700)
        path = foreign / 'pilot.sqlite'
        db = sqlite3.connect(path); db.execute('CREATE TABLE m3_execution(payload TEXT)'); db.commit(); db.close()
        path.chmod(0o600); (foreign / 'writer.lock').touch(mode=0o600)
        before = path.read_bytes()
        with self.assertRaises(Invalid):
            Store(foreign)
        self.assertEqual(path.read_bytes(), before)

    def test_unsafe_directory_file_symlink_and_hardlink_refused(self):
        self.store.close()
        self.directory.chmod(0o755)
        with self.assertRaises(Invalid): Store(self.directory)
        self.directory.chmod(0o700)
        self.store.path.chmod(0o644)
        with self.assertRaises(Invalid): Store(self.directory)
        self.store.path.chmod(0o600)
        alias = Path(self.temp.name).resolve() / 'alias'; alias.symlink_to(self.directory)
        with self.assertRaises(Invalid): Store(alias)
        link = Path(self.temp.name).resolve() / 'hardlink'; os.link(self.store.path, link)
        with self.assertRaises(Invalid): Store(self.directory)

    def crash_child(self, body):
        self.store.close()
        prefix = '''from pathlib import Path
import os,signal
from engine.detection.m4_pilot import Store,load_json
'''
        args = [sys.executable, '-B', '-c', prefix + body, str(self.directory), str(FIXTURE), str(RULE)]
        child = subprocess.run(args, cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT)}, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr.decode())
        self.store = Store(self.directory)
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_actual_sigkill_after_event_commit_retries_persisted_work(self):
        self.crash_child('''import sys
s=Store(Path(sys.argv[1]));s.receive(load_json(sys.argv[2]),load_json(sys.argv[3]))
os.kill(os.getpid(),signal.SIGKILL)
''')
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.store.db.execute('SELECT state FROM m4p_evaluations').fetchone()[0], 'pending')
        self.assertEqual(self.run_event(), 'matched')
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_actual_sigkill_during_alert_transaction_retries_once(self):
        self.crash_child('''import sys
s=Store(Path(sys.argv[1]));r=load_json(sys.argv[3]);key=s.receive(load_json(sys.argv[2]),r)
s.db.create_function('crash_now',0,lambda:os.kill(os.getpid(),signal.SIGKILL))
s.db.execute("CREATE TEMP TRIGGER crash_alert AFTER INSERT ON m4p_alerts BEGIN SELECT crash_now(); END")
s.evaluate(key,r['id'],r['revision'])
''')
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.store.db.execute('SELECT state FROM m4p_evaluations').fetchone()[0], 'pending')
        self.assertEqual(self.run_event(), 'matched')
        self.assertEqual(self.run_event(), 'matched')
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_actual_sigkill_after_alert_commit_keeps_single_alert(self):
        self.crash_child('''import sys
s=Store(Path(sys.argv[1]));r=load_json(sys.argv[3]);key=s.receive(load_json(sys.argv[2]),r)
s.evaluate(key,r['id'],r['revision'])
os.kill(os.getpid(),signal.SIGKILL)
''')
        self.assertEqual(self.counts(), (1, 1, 1))
        self.assertEqual(self.run_event(), 'matched')
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_bounded_json_duplicate_constants_and_depth(self):
        path = Path(self.temp.name) / 'input.json'
        for raw in (b'{"version":1,"version":2}', b'{"x":NaN}', b'x' * 32769, b'[' * 2000 + b']' * 2000):
            path.write_bytes(raw)
            with self.subTest(raw=raw[:30]), self.assertRaises(Invalid): load_json(path)


if __name__ == '__main__':
    unittest.main()
