import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from api.history_bounds import BoundedRows, BoundsError
from engine.detection.m4_schema import DDL_V2

class BoundsTest(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:',isolation_level=None);self.addCleanup(self.db.close);self.db.executescript(DDL_V2)
  self.binding='a'*64;self.db.execute('INSERT INTO m4h_bindings VALUES (?,?,?,?,?)',(self.binding,'{}','/synthetic','{}','[]'))
 def event(self,n=0,envelope='{}',binding=None):
  self.db.execute('INSERT INTO m4h_events VALUES (?,?,?,?,?,?,?)',(str(n).zfill(64),binding or self.binding,str(n),n,envelope,'b'*64,'2026-01-01T00:00:00Z'))
 def load(self):return BoundedRows(self.db).selected([self.binding])
 def test_valid_selected_rows_and_closed_transaction(self):
  self.event();self.assertEqual(len(self.load()['m4h_events']),1);self.assertFalse(self.db.in_transaction)
 def test_large_field_rejected_before_full_python_value(self):
  self.event(envelope='x'*1_000_000);seen=[]
  def capture(cursor,row):
   for value in row:
    if type(value) is bytes:seen.append(len(value))
   return row
  self.db.row_factory=capture
  with self.assertRaises(BoundsError):self.load()
  self.assertLessEqual(max(seen),16385);self.assertFalse(self.db.in_transaction)
 def test_utf8_limit_is_bytes(self):
  self.event(envelope='é'*8193)
  with self.assertRaises(BoundsError):self.load()
 def test_blob_type_refuses(self):
  self.event(envelope=sqlite3.Binary(b'{}'))
  with self.assertRaises(BoundsError):self.load()
 def test_row_cap_refuses_partial_view(self):
  for n in range(129):self.event(n)
  with self.assertRaises(BoundsError):self.load()
 def test_unselected_data_not_materialized(self):
  self.event(binding='c'*64,envelope='z'*1_000_000);self.assertEqual(self.load()['m4h_events'],[])
 def test_query_only_prohibits_mutation(self):
  self.load()
  with self.assertRaises(sqlite3.OperationalError):self.db.execute('DELETE FROM m4h_events')
 def test_missing_binding_refuses(self):
  with self.assertRaises(BoundsError):BoundedRows(self.db).selected(['c'*64])
 def test_bad_bindings_refuse(self):
  for values in ([],['x'],[self.binding]*2,['c'*64,'d'*64,'e'*64]):
   with self.assertRaises(BoundsError):BoundedRows(self.db).selected(values)
 def test_aggregate_budget(self):
  self.event();reader=BoundedRows(self.db);reader.MAX_BYTES=20
  with self.assertRaises(BoundsError):reader.selected([self.binding])
 def test_clock_deadline(self):
  clock=iter([0,3]);reader=BoundedRows(self.db,clock=lambda:next(clock,3))
  with self.assertRaises(BoundsError):reader.selected([self.binding])
 def test_returned_snapshot_does_not_hold_reader(self):
  self.event();view=self.load();self.db.execute('PRAGMA query_only=OFF');self.event(1);self.assertEqual(len(view['m4h_events']),1)

if __name__=='__main__':unittest.main()
