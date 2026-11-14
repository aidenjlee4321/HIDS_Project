import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from api.dashboard_browser import Pipe,trusted_binary

class LaunchTests(unittest.TestCase):
    def exchange(self,error=False):
        incoming,send=os.pipe();receive,outgoing=os.pipe();seen=[]
        def server():
            raw=b''
            while b'\0' not in raw:raw+=os.read(incoming,4096)
            value=json.loads(raw[:-1]);seen.append(value)
            os.write(outgoing,json.dumps(dict(method='Target.targetCreated',params={})).encode()+b'\0')
            reply=dict(id=value['id'],error={'message':'private diagnostic'}) if error else dict(id=value['id'],result={'targetId':'closed-test-target'})
            os.write(outgoing,json.dumps(reply).encode()+b'\0')
        t=threading.Thread(target=server);t.start()
        try:
            pipe=Pipe(receive,send)
            if error:
                with self.assertRaisesRegex(ValueError,'^browser pipe refused$'):pipe.call('Target.createTarget',dict(url='https://127.0.0.1:18765/#grant=synthetic'))
            else:self.assertEqual(pipe.call('Target.createTarget',dict(url='https://127.0.0.1:18765/#grant=synthetic')),{'targetId':'closed-test-target'})
            t.join(timeout=1);self.assertFalse(t.is_alive());self.assertEqual(seen[0]['params']['url'],'https://127.0.0.1:18765/#grant=synthetic')
        finally:
            for fd in (incoming,send,receive,outgoing):os.close(fd)
    def test_bootstrap_pipe_and_interleaved_event(self):self.exchange()
    def test_protocol_error_does_not_expose_remote_diagnostic(self):self.exchange(True)
    def test_untrusted_browser_path_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'browser';p.write_text('x');p.chmod(0o777)
            for path in (p,Path('relative-browser')):
                with self.assertRaises(ValueError):trusted_binary(path)
            link=Path(d)/'link';link.symlink_to('/usr/bin/true')
            with self.assertRaises(ValueError):trusted_binary(link)
    def test_root_browser_refused_before_start(self):
        from api.dashboard_browser import run
        from unittest.mock import patch
        with patch('api.dashboard_browser.os.getuid',return_value=0),patch('api.dashboard_browser.subprocess.Popen') as child:
            with self.assertRaises(ValueError):run('/usr/bin/true','/usr/bin/true',{})
            child.assert_not_called()
if __name__=='__main__':unittest.main()
