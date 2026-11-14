import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('gemini_review',Path(__file__).resolve().parents[2]/'scripts/gemini_review.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class ReviewPacketTests(unittest.TestCase):
 def packet(self,text='pass\n'):
  return dict(format=g.VERSION,task='Review this code.',files=[dict(path='api/example.py',content=text,sha256=hashlib.sha256(text.encode()).hexdigest())])
 def test_closed_packet_and_file_hash(self):
  value=self.packet();self.assertEqual(g.closed(g.validate(value)),value)
  value['files'][0]['content']='changed'
  with self.assertRaises(ValueError):g.validate(value)
 def test_traversal_secret_and_non_source_paths_rejected(self):
  for path in ('api/../secret.py','api/.gemini/settings.json','/etc/shadow','api//example.py','docs/validation/report.md','api/events.sqlite'):
   value=self.packet();value['files'][0]['path']=path
   with self.subTest(path=path),self.assertRaises(ValueError):g.validate(value)
  with self.assertRaises(ValueError):g.validate(self.packet('-----BEGIN PRIVATE KEY-----'))
 def test_unknown_keys_duplicates_and_large_packets_rejected(self):
  value=self.packet();value['authority']='root'
  with self.assertRaises(ValueError):g.validate(value)
  with self.assertRaises(ValueError):g.closed('{"task":"a","task":"b"}')
  with self.assertRaises(ValueError):g.validate(self.packet('x'*65537))
 def test_local_source_snapshot_and_symlink_refusal(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d).resolve();(root/'api').mkdir();(root/'api/example.py').write_text('pass\n')
   self.assertEqual(len(g.make_packet(root,'Review',['api/example.py'])['files']),1)
   (root/'api/link.py').symlink_to('/etc/passwd')
   with self.assertRaises(ValueError):g.make_packet(root,'Review',['api/link.py'])
   with self.assertRaises(ValueError):g.make_packet(root,'Review',['../../etc/passwd'])
 def test_missing_auth_never_starts_gemini(self):
  with patch.object(g,'identity',return_value=object()),patch.object(g,'auth_available',return_value=False),patch.object(g.subprocess,'Popen') as spawn:
   self.assertEqual(g.run(self.packet())['status'],'needs_auth');spawn.assert_not_called()
 def test_fixed_command_denies_tools_and_hides_hids(self):
  cmd=g.command('hids-gemini-test')
  self.assertIn('--approval-mode',cmd);self.assertIn('plan',cmd);self.assertIn('--admin-policy',cmd)
  self.assertIn('--property=CapabilityBoundingSet=',cmd);self.assertIn('--property=ProtectHome=yes',cmd)
  self.assertTrue(any(v.startswith('--property=InaccessiblePaths=') and '/var/lib/hids' in v for v in cmd))
  self.assertNotIn('--yolo',cmd)
 def test_interrupt_stops_unit_and_records_failure(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);(base/'jobs').mkdir()
   with patch.object(g,'BASE',base),patch.object(g,'identity',return_value=object()),patch.object(g,'auth_available',return_value=True),patch.object(g.subprocess,'Popen',side_effect=KeyboardInterrupt),patch.object(g,'stop') as stop:
    result=g.run(self.packet())
   self.assertEqual(result['status'],'failed');self.assertEqual(result['error_type'],'KeyboardInterrupt')
   stop.assert_called_once()
   self.assertEqual(json.loads((base/'jobs'/result['job_id']/'result.json').read_text())['status'],'failed')
if __name__=='__main__':unittest.main()
