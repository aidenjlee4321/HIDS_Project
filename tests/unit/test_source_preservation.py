import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from source_preservation import verify_prefixes,PreservationError

class PreservationTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name).resolve();self.root.chmod(0o700);self.p=self.root/'audit.log';self.p.write_bytes(b'original prefix');self.p.chmod(0o600)
  self.row=dict(path=str(self.p),inode=self.p.stat().st_ino,bytes=self.p.stat().st_size,sha256=hashlib.sha256(self.p.read_bytes()).hexdigest())
 def check(self):return verify_prefixes([self.row],owner=os.getuid())
 def test_original_file(self):self.assertEqual(self.check()[0]['current'],str(self.p))
 def test_renamed_original_inode_and_prefix_remain_required(self):
  rotated=self.root/'audit.log.1';self.p.rename(rotated);self.p.write_bytes(b'new log');self.p.chmod(0o600);self.assertEqual(self.check()[0]['current'],str(rotated))
 def test_rotation_from_numbered_baseline(self):
  self.p.rename(self.root/'audit.log.3');self.row['path']=str(self.root/'audit.log.2');self.assertEqual(self.check()[0]['current'],str(self.root/'audit.log.3'))
 def test_appended_bytes_do_not_rewrite_prefix(self):
  with self.p.open('ab') as f:f.write(b' later data')
  self.check()
 def test_same_bytes_wrong_inode_refused(self):
  self.p.rename(self.root/'saved');self.p.write_bytes(b'original prefix');self.p.chmod(0o600)
  with self.assertRaises(PreservationError):self.check()
 def test_mutated_prefix_refused(self):
  self.p.write_bytes(b'changed prefix')
  with self.assertRaises(PreservationError):self.check()
 def test_truncation_refused(self):
  self.p.write_bytes(b'x')
  with self.assertRaises(PreservationError):self.check()
 def test_symlink_refused(self):
  self.p.rename(self.root/'saved');self.p.symlink_to(self.root/'saved')
  with self.assertRaises(PreservationError):self.check()
 def test_hardlink_refused(self):
  os.link(self.p,self.root/'audit.log.1')
  with self.assertRaises(PreservationError):self.check()
 def test_world_readable_or_writable_refused(self):
  for mode in (0o644,0o620,0o666):
   self.p.chmod(mode)
   with self.assertRaises(PreservationError):self.check()
 def test_file_outside_rotation_namespace_not_used(self):
  self.p.rename(self.root/'unrelated')
  with self.assertRaises(PreservationError):self.check()
 def test_invalid_or_oversized_manifest_refused(self):
  for key,value in (('inode',True),('bytes',64*1024*1024+1),('sha256','x'),('path',str(self.root/'other'))):
   old=dict(self.row);self.row[key]=value
   with self.assertRaises(PreservationError):self.check()
   self.row=old
if __name__=='__main__':unittest.main()
