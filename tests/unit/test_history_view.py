"""Synthetic fixtures only; no production path or real-event payloads."""
import base64
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from api.history_view import FrozenView,ViewError,_load,_hash,escaped
from api.history_bounds import BoundedRows
from engine.detection.m4_pilot import canonical,digest
from engine.detection.m4_rules import REFERENCE
from engine.detection.m4_handoff import FORMAT
from engine.detection.m4_schema import DDL_V2

ROOT=Path(__file__).resolve().parents[2]
NOW='2026-11-13T00:00:00.000000Z'

def fixture(count=25):
 rows={t:[] for t in ('m4h_bindings','m4h_events','m4h_rules','m4h_evaluations','m4h_alerts')}
 rule=json.loads((ROOT/'rules/process/configured-root-shell.json').read_text())
 scopes=[]
 for i in range(2):
  scope=dict(source='11111111-1111-4111-8111-111111111111',activation=f'22222222-2222-4222-8222-{i:012d}',generation=f'33333333-3333-4333-8333-{i:012d}')
  key=_hash('binding',scope);scopes.append((scope,key))
  state=dict(boundary=0,settled=10000,target=None,after=9999,seen_frontier=10000,seen_scanned=10000,fingerprint=[[1,2],[1,3],[1,4]])
  rows['m4h_bindings'].append(dict(binding_key=key,scope=canonical(scope),directory='/var/lib/hids/m3',state=canonical(state),rule_plan=canonical([] if i==0 else [REFERENCE])))
 rows['m4h_rules']=[dict(rule_id=rule['id'],revision=rule['revision'],definition=canonical(rule),content_hash=REFERENCE['hash'])]
 for n in range(count):
  scope,binding=scopes[int(n>=16)]
  exe=base64.b64encode(b'/usr/bin/dash' if n==16 else b'/synthetic/<img src=x onerror=window.hidsInjected=true>\x1b\xe2\x80\xae\xff').decode()
  execution=dict(syscall=221,pid=n+1,ppid=1,uid=1000,euid=0 if n==16 else 1000,suid=1000,fsuid=1000,path_count=1,auid=None,session=None,success=True,cwd_present=False,proctitle_present=False,result=0,exe_base64=exe,comm_base64=base64.b64encode(b'test').decode())
  event=dict(format=FORMAT,origin='audit_plugin',**scope,identity=f'1234567890.123:{n}',first_offset=n,execution=execution,metadata=dict(format=1,arch=0xc00000b7,profile='linux.audit.aarch64.string/1',first_observed_unix_ns=2**63-1,received_at=NOW,persistence_started_at=NOW))
  key=_hash('event',[event[k] for k in ('source','activation','generation','identity')])
  rows['m4h_events'].append(dict(event_key=key,binding_key=binding,identity=event['identity'],first_offset=n,envelope=canonical(event),content_hash=_hash('content',event),imported_at=NOW))
  if n>=16:
   rows['m4h_evaluations'].append(dict(event_key=key,rule_id=rule['id'],revision=rule['revision'],state='matched' if n==16 else 'no_match',reason='all_predicates_equal' if n==16 else 'predicate_not_equal',evaluated_at=NOW))
   if n==16:rows['m4h_alerts'].append(dict(alert_id=_hash('alert',[key,rule['id'],rule['revision']]),event_key=key,rule_id=rule['id'],revision=rule['revision'],explanation=rule['explanation']+' Audit login identity is unavailable.',matched_values=canonical(dict(exe_base64=execution['exe_base64'],euid=0,success=True)),demo=0,severity='informational',created_at=NOW))
 return rows

class HistoryTest(unittest.TestCase):
 def setUp(self):self.rows=fixture()
 def refuse(self,edit):
  rows=copy.deepcopy(self.rows);edit(rows)
  with self.assertRaises(ViewError):FrozenView(rows)
 def test_valid_snapshot_linkage_lossless_types(self):
  v=FrozenView(self.rows);self.assertEqual(v.summary()['counts'],dict(events=25,findings=1,evaluations=9,bindings=2,rules=1,unevaluated=16,pending=0))
  e=v.detail('events',self.rows['m4h_events'][0]['event_key']);self.assertEqual(e['metadata']['first_observed_unix_ns'],str(2**63-1));self.assertEqual(e['first_offset'],'0');self.assertEqual(e['execution']['result'],'0');self.assertIsNone(e['execution']['auid']);self.assertEqual(e['evaluation_state'],'unevaluated')
  self.assertNotIn('/var/lib',canonical(e));f=v.detail('findings',self.rows['m4h_alerts'][0]['alert_id']);self.assertEqual(v.detail('events',f['event_id'])['evaluation_state'],'matched')
 def test_native_negative_result_and_unknown_observation(self):
  row=self.rows['m4h_events'][0];e=json.loads(row['envelope']);e['execution'].update(result=-(2**63),success=False);e['metadata'].update(arch=None,profile=None,first_observed_unix_ns=None);row.update(envelope=canonical(e),content_hash=_hash('content',e));v=FrozenView(self.rows);d=v.detail('events',row['event_key']);self.assertEqual(d['execution']['result'],str(-(2**63)));self.assertIsNone(d['metadata']['first_observed_unix_ns'])
 def test_cursors_bound_view_route_and_session(self):
  v=FrozenView(self.rows);first=v.page('events','A'*43);self.assertEqual(len(first['items']),20);cursor=first['next_cursor'];second=v.page('events','A'*43,cursor);self.assertEqual(len(second['items']),5);self.assertIsNone(second['next_cursor']);self.assertEqual(second,v.page('events','A'*43,cursor))
  for kind,token,c in [('events','B'*43,cursor),('findings','A'*43,cursor),('events','A'*43,cursor[:-1]+'!'),('events','A'*43,'x'*513)]:
   with self.assertRaises(ViewError):v.page(kind,token,c)
  with self.assertRaises(ViewError):FrozenView(self.rows).page('events','A'*43,cursor)
 def test_frozen_copy(self):
  v=FrozenView(self.rows);self.rows.clear();s=v.summary();s['counts']['events']=0;self.assertEqual(v.summary()['counts']['events'],25)
 def test_escape_controls_bidi_invalid_bytes(self):
  p=escaped(base64.b64encode(b'a\x1b\xe2\x80\xae\xff').decode());self.assertEqual(p['text'],'a\\x1b\\u202e\\xff');self.assertFalse(p['truncated']);self.assertTrue(escaped(base64.b64encode(b'a'*300).decode())['truncated'])
 def test_corrupt_relationships_and_hashes(self):
  for table,field,value in [('m4h_bindings','binding_key','a'*64),('m4h_events','content_hash','a'*64),('m4h_events','binding_key','a'*64),('m4h_events','event_key','a'*64),('m4h_events','identity','invalid'),('m4h_events','first_offset',-1),('m4h_rules','content_hash','a'*64),('m4h_rules','definition','{}'),('m4h_alerts','demo',1),('m4h_alerts','explanation','wrong'),('m4h_alerts','event_key','a'*64),('m4h_alerts','matched_values','{}'),('m4h_evaluations','reason','wrong'),('m4h_evaluations','event_key','a'*64)]:
   with self.subTest(table=table,field=field):self.refuse(lambda r:r[table][0].update({field:value}))
 def test_missing_or_extra_witnesses(self):
  self.refuse(lambda r:r['m4h_evaluations'].pop());self.refuse(lambda r:r['m4h_alerts'].clear());self.refuse(lambda r:r['m4h_alerts'].append(r['m4h_alerts'][0]));self.refuse(lambda r:r['m4h_bindings'][0].update(rule_plan=canonical([REFERENCE])))
 def test_no_silent_new_keys_or_noncanonical_envelopes(self):
  self.refuse(lambda r:r['m4h_events'][0].update(envelope=r['m4h_events'][0]['envelope']+' '))
  def edit(r):
   row=r['m4h_events'][0];e=json.loads(row['envelope']);e['secret']='bad';row.update(envelope=canonical(e),content_hash=_hash('content',e))
  self.refuse(edit)
 def test_each_stored_outcome_preserved(self):
  for state,reason in [('pending',None),('unable','source_profile_unavailable'),('error','evaluation_failed')]:
   rows=copy.deepcopy(self.rows);rows['m4h_evaluations'][1].update(state=state,reason=reason,evaluated_at=None if state=='pending' else NOW);v=FrozenView(rows);self.assertEqual(v.detail('events',rows['m4h_evaluations'][1]['event_key'])['evaluation_state'],state)
 def test_caps_and_oversized_value_refuse(self):
  with self.assertRaises(ViewError):FrozenView(fixture(129))
  self.refuse(lambda r:r['m4h_events'][0].update(envelope='x'*16385))

class FileHistoryTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='hids-history-test.');self.addCleanup(self.temp.cleanup);self.directory=Path(self.temp.name).resolve();self.directory.chmod(0o700);self.path=self.directory/'handoff.sqlite'
  self.db=sqlite3.connect(self.path,isolation_level=None);self.addCleanup(self.db.close);self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA application_id=0x48344c31');self.db.execute('PRAGMA user_version=2');self.db.executescript(DDL_V2);self.rows=fixture()
  for table,rows in self.rows.items():
   for row in rows:self.db.execute('INSERT INTO '+table+' ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
  for p in self.directory.iterdir():p.chmod(0o600)
  st=self.path.stat();self.identity=[st.st_dev,st.st_ino];self.bindings=[r['binding_key'] for r in self.rows['m4h_bindings']]
 def load(self):return _load(self.path,self.bindings,self.identity)
 def test_wal_read_preserves_files_and_releases_reader(self):
  before={p.name:p.read_bytes() for p in self.directory.iterdir() if not p.name.endswith('-shm')};v=self.load();self.assertEqual(v.summary()['counts']['events'],25);self.db.execute('BEGIN IMMEDIATE');self.db.execute('DELETE FROM m4h_alerts');self.db.execute('COMMIT');self.assertEqual(v.summary()['counts']['findings'],1);self.assertEqual(self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0],0)
 def test_read_does_not_mutate_main_or_wal(self):
  before={p.name:p.read_bytes() for p in self.directory.iterdir() if not p.name.endswith('-shm')};self.load();self.assertEqual(before,{p.name:p.read_bytes() for p in self.directory.iterdir() if not p.name.endswith('-shm')})
 def test_schema_application_id_and_version_refuse(self):
  for sql in ('PRAGMA user_version=9','PRAGMA application_id=42','CREATE TABLE injected(x)'):
   with self.subTest(sql=sql):
    self.db.execute(sql)
    with self.assertRaises(ViewError):self.load()
 def test_wrong_inode_and_symlink_refuse(self):
  self.identity[1]+=1
  with self.assertRaises(ViewError):self.load()
  self.identity[1]-=1;other=self.directory/'other';self.path.rename(other);self.path.symlink_to(other)
  with self.assertRaises(ViewError):self.load()
 def test_unsafe_modes_refuse(self):
  self.path.chmod(0o644)
  with self.assertRaises(ViewError):self.load()
 def test_missing_sidecar_no_creation(self):
  p=Path(str(self.path)+'-shm');p.unlink()
  with self.assertRaises(ViewError):self.load()
  self.assertFalse(p.exists())
 def test_missing_wal_no_creation(self):
  p=Path(str(self.path)+'-wal');p.unlink()
  with self.assertRaises(ViewError):self.load()
  self.assertFalse(p.exists())
 def test_unselected_data_not_projected(self):
  v=_load(self.path,[self.bindings[0]],self.identity);self.assertEqual(v.summary()['counts']['events'],16);self.assertEqual(v.summary()['counts']['rules'],0)
 def test_writer_uncommitted_not_exposed(self):
  self.db.execute('BEGIN IMMEDIATE');self.db.execute('DELETE FROM m4h_alerts');v=self.load();self.assertEqual(v.summary()['counts']['findings'],1);self.db.execute('ROLLBACK')
 def test_deadline_failure_closes_without_sidecar_changes(self):
  with patch('api.history_view.time.monotonic',side_effect=[0,3,3,3]):
   with self.assertRaises(ViewError):self.load()
  self.db.execute('BEGIN IMMEDIATE');self.db.execute('ROLLBACK')

if __name__=='__main__':unittest.main()
