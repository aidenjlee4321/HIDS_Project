import os
from pathlib import Path
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from api import dashboard_launch as launch
from api.dashboard_browser import reap

class CleanupTests(unittest.TestCase):
 def test_interrupt_during_preparation_reap_still_revokes_viewer(self):
  child=SimpleNamespace(stdin=SimpleNamespace(close=lambda:None),wait=lambda **kw:(_ for _ in ()).throw(KeyboardInterrupt()))
  with patch.object(launch,'reap') as reap_child,patch.object(launch,'stop') as stop:
   with self.assertRaises(KeyboardInterrupt):launch.finish_preparation(child)
   reap_child.assert_called_once_with(child,timeout=1);stop.assert_called_once()
 def test_interrupt_after_viewer_start_stops_viewer(self):
  for interruption in (KeyboardInterrupt,SystemExit):
   with self.subTest(interruption=interruption),patch.object(launch.os,'getuid',return_value=0),patch.object(launch.os,'geteuid',return_value=0),patch.object(launch.pwd,'getpwnam',return_value=SimpleNamespace(pw_gid=1)),patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'exists',return_value=False),patch.object(launch,'stop') as stop,patch.object(launch,'ensure_leaf',return_value=dict(tls_generation='test',certificate_sha256='a'*64)),patch.object(launch,'publish'),patch.object(launch,'TLS',SimpleNamespace(iterdir=lambda:[])),patch.object(launch,'system',side_effect=interruption):
    with self.assertRaises(interruption):launch.prepare([],[])
    self.assertEqual(stop.call_count,2)
 def test_timed_out_load_still_removes_policy(self):
  with tempfile.TemporaryDirectory() as parent:
   work=Path(parent)/'policy';work.mkdir()
   with patch.object(launch,'trusted_binary',return_value=Path('/usr/bin/true')),patch.object(launch.tempfile,'mkdtemp',return_value=str(work)),patch.object(launch,'profile_present',return_value=False),patch.object(launch.subprocess,'run',side_effect=[subprocess.TimeoutExpired('load',5),SimpleNamespace(returncode=1)]) as run:
    with self.assertRaises(subprocess.TimeoutExpired):launch.browser(SimpleNamespace(pw_uid=1),'/usr/bin/true','/usr/bin/true',Path('/unused'),temporary_userns=True)
    self.assertIn('--remove',run.call_args_list[-1].args[0]);self.assertFalse(work.exists())
 def test_unconfirmed_policy_cleanup_retains_its_file(self):
  with tempfile.TemporaryDirectory() as parent:
   policy=Path(parent)/'profile';policy.write_text('test policy')
   with patch.object(launch,'profile_present',return_value=True),patch.object(launch.subprocess,'run',side_effect=subprocess.TimeoutExpired('remove',5)):
    with self.assertRaises(launch.Denied):launch.remove_policy(policy,'owned-test-profile')
   self.assertTrue(policy.exists())
 def test_stubborn_owned_child_is_killed_and_reaped(self):
  script='import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(60)'
  child=subprocess.Popen([os.sys.executable,'-B','-c',script],stdout=subprocess.PIPE,text=True)
  try:
   self.assertEqual(child.stdout.readline().strip(),'ready');reap(child,timeout=.05)
   self.assertEqual(child.returncode,-signal.SIGKILL)
  finally:
   if child.poll() is None:child.kill();child.wait()
   child.stdout.close()

if __name__=='__main__':unittest.main()
