from pathlib import Path
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from api import development_install as d

class ConfigureRefusalTests(unittest.TestCase):
 def refuse_before_accounts(self,release,conflict=False):
  def exists(path):return conflict and path==Path('/etc/systemd/system',d.UNITS[0])
  with patch.object(d.os,'getuid',return_value=0),patch.object(d.os,'geteuid',return_value=0),patch.object(d,'stopped'),patch.object(Path,'read_text',return_value=release),patch.object(Path,'exists',exists),patch.object(d.pwd,'getpwnam',side_effect=KeyError) as lookup,patch.object(d.subprocess,'run') as run:
   with self.assertRaises(ValueError):d.configure()
   lookup.assert_not_called();run.assert_not_called()
 def test_unsupported_ubuntu_refused_before_account_creation(self):
  self.refuse_before_accounts('ID=ubuntu\nVERSION_ID="24.04"\n')
 def test_conflicting_unit_refused_before_account_creation(self):
  self.refuse_before_accounts('ID=ubuntu\nVERSION_ID="26.04"\n',True)
 def test_existing_privileged_role_refused_before_creation(self):
  with patch.object(d.os,'getuid',return_value=0),patch.object(d.os,'geteuid',return_value=0),patch.object(d,'stopped'),patch.object(Path,'read_text',return_value='ID=ubuntu\nVERSION_ID="26.04"\n'),patch.object(Path,'exists',return_value=False),patch.object(d.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=0,pw_shell='/usr/sbin/nologin')),patch.object(d.subprocess,'run') as run:
   with self.assertRaises(ValueError):d.configure()
   run.assert_not_called()

class ConfigPublicationTests(unittest.TestCase):
 def test_genuinely_fresh_config_allowed(self):
  with tempfile.TemporaryDirectory() as directory:d.require_fresh_process_config(Path(directory)/'process.json')
 def test_missing_config_with_retained_metadata_refused(self):
  for kind in ('history','pending','broken_history_link'):
   with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
    parent=Path(directory)
    if kind=='history':(parent/'process-config-history').mkdir()
    elif kind=='pending':(parent/'process-old.pending').write_text('{}')
    else:(parent/'process-config-history').symlink_to(parent/'missing')
    with self.assertRaises(ValueError):d.require_fresh_process_config(parent/'process.json')
 def exercise(self,point):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'process.json';old=b'{ "source_id": "preserved", "binary_sha256": "old", "max_events": 123 }\n'
   path.write_bytes(old)
   def fault(value):
    if value==point:raise OSError('injected interruption')
   with patch.object(d,'safe'),patch.object(d.os,'fchown'):
    with self.assertRaises(OSError):d.update_process_config(path,json.loads(old),'new',os.getgid(),fault=fault)
    active=json.loads(path.read_bytes());self.assertEqual(active['source_id'],'preserved');self.assertEqual(active['max_events'],123)
    self.assertEqual(active['binary_sha256'],'old' if point=='before_publish' else 'new')
    backups=list((path.parent/'process-config-history').glob('*.json'))
    self.assertTrue(any(p.read_bytes()==old for p in backups))
    if active['binary_sha256']!='new':d.update_process_config(path,active,'new',os.getgid())
   self.assertEqual(json.loads(path.read_bytes())['binary_sha256'],'new')
 def test_failure_before_replace_keeps_old_config_and_retry(self):self.exercise('before_publish')
 def test_failure_after_replace_keeps_new_config_and_backup(self):self.exercise('after_publish')

if __name__=='__main__':unittest.main()
