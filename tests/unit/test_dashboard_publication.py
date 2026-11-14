import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api import dashboard_launch as d

class PublicationTests(unittest.TestCase):
 def exercise(self,after=False):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory).resolve()/'dashboard.json';old=b'{ "view": "old", "certificate": "preserved" }\n';path.write_bytes(old);path.chmod(0o440)
   def fault(point):
    if after and point=='after_publish':raise KeyboardInterrupt()
   with patch.object(d,'CONFIG',path),patch.object(d,'trusted'),patch.object(d.os,'getuid',return_value=0),patch.object(d.os,'geteuid',return_value=0),patch.object(d.os,'fchown'):
    with patch.object(d.os,'replace',side_effect=OSError('refused')) if not after else patch.object(d,'stop'):
     with self.assertRaises(KeyboardInterrupt if after else OSError):d.publish({'view':'new','certificate':'preserved'},os.getgid(),fault=fault)
    self.assertEqual(json.loads(path.read_bytes())['view'],'new' if after else 'old')
    self.assertEqual(json.loads(path.read_bytes())['certificate'],'preserved')
    backups=list((path.parent/'dashboard-config-history').glob('*.json'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),old)
    d.publish({'view':'new','certificate':'preserved'},os.getgid())
   self.assertEqual(path.stat().st_mode&0o777,0o440);self.assertEqual(path.stat().st_nlink,1)
 def test_failed_replace_preserves_active_config_and_backup(self):self.exercise()
 def test_interrupt_after_replace_leaves_complete_new_config(self):self.exercise(True)
 def test_symlink_refused_without_reading_or_changing_target(self):
  with tempfile.TemporaryDirectory() as directory:
   target=Path(directory)/'target';target.write_text('unchanged');link=Path(directory)/'dashboard.json';link.symlink_to(target)
   with patch.object(d,'CONFIG',link),patch.object(d.os,'getuid',return_value=0),patch.object(d.os,'geteuid',return_value=0):
    with self.assertRaises(d.Denied):d.publish({},os.getgid())
   self.assertEqual(target.read_text(),'unchanged');self.assertEqual(len(list(Path(directory).iterdir())),2)
 def test_first_publication_has_no_old_file_requirement(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory).resolve()/'dashboard.json'
   with patch.object(d,'CONFIG',path),patch.object(d,'trusted'),patch.object(d.os,'getuid',return_value=0),patch.object(d.os,'geteuid',return_value=0),patch.object(d.os,'fchown'):
    d.publish({'view':'first'},os.getgid())
   self.assertEqual(json.loads(path.read_bytes()),{'view':'first'})

if __name__=='__main__':unittest.main()
