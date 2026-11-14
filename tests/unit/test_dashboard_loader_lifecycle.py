"""Closed-store fixtures exercise the actual launcher's SQLite preparation."""
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from api.dashboard_launch import PREP
from api.history_view import _load as history_load,ViewError
from api.process_view import _load as process_load
from engine.database.process_store import Store
from engine.detection.m4_schema import DDL_V2
from engine.ingestion import process_contract as c
from test_history_view import fixture as history_fixture
from test_process_view import rows
from test_process_pipeline import status,PRODUCER

@unittest.skipUnless(sys.platform=='linux','SQLite preparation is an Ubuntu acceptance boundary')
class LoaderLifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='hids-closed-store.');self.addCleanup(self.tmp.cleanup)
  self.directory=Path(self.tmp.name).resolve();self.directory.chmod(0o700)
 def process(self):
  path=self.directory/'store.sqlite';values,selected=rows(3);source=c.decode(values['events'][0]['envelope'].encode())['source']
  store=Store(path,source)
  try:
   for row in values['events']:store.put(c.decode(row['envelope'].encode()),row['received_at'])
   st=status(delivery=True,stopped=True);st['source']=source;store.interval(st,PRODUCER)
  finally:store.close()
  return path,selected,process_load,3
 def history(self):
  path=self.directory/'handoff.sqlite';db=sqlite3.connect(path,isolation_level=None)
  try:
   db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA application_id=0x48344c31');db.execute('PRAGMA user_version=2');db.executescript(DDL_V2)
   values=history_fixture()
   for table,records in values.items():
    for row in records:db.execute('INSERT INTO '+table+' ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
  finally:db.close()
  path.chmod(0o600)
  return path,[r['binding_key'] for r in values['m4h_bindings']],history_load,25
 def exercise(self,family,corrupt=False):
  path,selected,load,count=getattr(self,family)()
  if corrupt:
   db=sqlite3.connect(path)
   try:db.execute("UPDATE "+('process_events' if family=='process' else 'm4h_events')+" SET envelope=CAST(x'ff' AS TEXT)");db.commit()
   finally:db.close()
  identity=[path.stat().st_dev,path.stat().st_ino];before=hashlib.sha256(path.read_bytes()).hexdigest()
  self.assertFalse(Path(str(path)+'-wal').exists());self.assertFalse(Path(str(path)+'-shm').exists())
  with self.assertRaises(ViewError):load(path,selected,identity)
  self.assertFalse(Path(str(path)+'-wal').exists());self.assertFalse(Path(str(path)+'-shm').exists())
  prep=subprocess.Popen([sys.executable,'-I','-B','-c',PREP,str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   import selectors
   with selectors.DefaultSelector() as poll:
    poll.register(prep.stdout,selectors.EVENT_READ);self.assertTrue(poll.select(3));self.assertEqual(prep.stdout.readline(),'prepared\n')
   for suffix in ('-wal','-shm'):self.assertTrue(Path(str(path)+suffix).exists())
   if corrupt:
    with self.assertRaises(ViewError):load(path,selected,identity)
   else:self.assertEqual(load(path,selected,identity).summary()['counts']['events'],count)
   self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
   self.assertEqual(Path(str(path)+'-wal').stat().st_size,0)
  finally:
   prep.communicate(timeout=3)
   self.assertEqual(prep.returncode,0)
 def test_closed_process_store_prepares_without_evidence_writes(self):self.exercise('process')
 def test_closed_history_store_prepares_without_evidence_writes(self):self.exercise('history')
 def test_invalid_utf8_process_store_refuses_after_preparation(self):self.exercise('process',True)
 def test_invalid_utf8_history_store_refuses_after_preparation(self):self.exercise('history',True)

if __name__=='__main__':unittest.main()
