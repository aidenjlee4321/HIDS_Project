from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api.setup_manager import ProcessAdapter
from api.pilot_sessions import Denied
from engine.ingestion import process_control as p

ENTRY=dict(source='11111111-1111-4111-8111-111111111111',activation='22222222-2222-4222-8222-222222222222',generation='33333333-3333-4333-8333-333333333333',state='stop_unconfirmed')

class CancellationTests(unittest.TestCase):
 def exercise(self,foreign=False,active=False,expired=False):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve();grant=root/'next-start.json'
   value=dict(version=1,source_id=ENTRY['source'],activation_id='foreign' if foreign else ENTRY['activation'],generation=ENTRY['generation'],expires=1 if expired else 1000000000)
   raw=json.dumps(value).encode();grant.write_bytes(raw)
   adapter=ProcessAdapter()
   with patch.object(adapter,'owner_lock',return_value=nullcontext()),patch.object(p,'RUNTIME',root),patch.object(p,'GRANT',grant),patch.object(p,'trusted',side_effect=lambda path,*args:Path(path).read_bytes()),patch('api.setup_manager.setup_preflight.unit',return_value={'ActiveState':'active' if active else 'inactive'}),patch('api.setup_manager.subprocess.run') as command:
    if foreign:
     with self.assertRaises(Denied):adapter.cancel_pending(ENTRY)
    else:self.assertEqual(adapter.cancel_pending(ENTRY),not active)
    command.assert_not_called()
   if foreign:self.assertEqual(grant.read_bytes(),raw)
   else:self.assertFalse(grant.exists())
 def test_exact_unconsumed_grant_revoked_without_status(self):self.exercise()
 def test_expired_exact_grant_can_be_revoked(self):self.exercise(expired=True)
 def test_foreign_grant_preserved(self):self.exercise(foreign=True)
 def test_unknown_active_component_does_not_retain_grant_or_confirm_stop(self):self.exercise(active=True)
 def test_legacy_active_status_never_signals_runtime(self):
  adapter=ProcessAdapter();state=dict(ENTRY,version=1,backend_exit=None,collector_exit=None)
  with patch.object(adapter,'cancel_pending',return_value=False),patch.object(p,'trusted',return_value=json.dumps(state).encode()),patch.object(p,'runtime_scope',return_value=dict(ActiveState='active',MainPID=123,InvocationID='a'*32)),patch('api.setup_manager.os.pidfd_open',create=True) as open_pid:
   with self.assertRaises(Denied):adapter.stop(ENTRY)
   open_pid.assert_not_called()
 def test_foreign_live_invocation_never_signalled(self):
  adapter=ProcessAdapter();state=dict(ENTRY,version=2,runtime_pid=123,runtime_invocation='a'*32)
  with patch.object(adapter,'cancel_pending',return_value=False),patch.object(p,'trusted',return_value=json.dumps(state).encode()),patch.object(p,'runtime_scope',return_value=dict(ActiveState='active',MainPID=123,InvocationID='b'*32)),patch('api.setup_manager.os.pidfd_open',create=True) as open_pid:
   with self.assertRaises(Denied):adapter.stop(ENTRY)
   open_pid.assert_not_called()
 def test_unknown_leftover_parts_never_stopped(self):
  adapter=ProcessAdapter();state=dict(ENTRY,version=2,state='stopped',forced=False)
  with patch.object(adapter,'cancel_pending',return_value=False),patch.object(adapter,'owner_lock',return_value=nullcontext()),patch.object(p,'trusted',return_value=json.dumps(state).encode()),patch.object(p,'runtime_scope',return_value=dict(ActiveState='inactive',MainPID=0,InvocationID='a'*32)),patch('api.setup_manager.setup_preflight.unit',return_value={'ActiveState':'active'}),patch('api.setup_manager.subprocess.run') as command:
   with self.assertRaises(Denied):adapter.stop(ENTRY)
   command.assert_not_called()

if __name__=='__main__':unittest.main()
