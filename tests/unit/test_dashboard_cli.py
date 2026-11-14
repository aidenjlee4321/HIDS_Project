"""Boundary cases for the root client; actual Linux credentials are exercised in Ubuntu."""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import stat
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from api import pilot_cli
from api.pilot_sessions import Denied

class CLITest(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        def mocked(target,**kw):return self.stack.enter_context(patch('api.pilot_cli.'+target,**kw))
        mocked('os.getuid',return_value=0);mocked('os.geteuid',return_value=0)
        self.config=mocked('config',return_value={'port':18765})
        mocked('pwd.getpwnam',return_value=SimpleNamespace(pw_uid=994))
        self.path=mocked('Path').return_value
        self.path.parent.lstat.return_value=SimpleNamespace(st_uid=0,st_mode=stat.S_IFDIR|0o700)
        self.path.lstat.return_value=SimpleNamespace(st_uid=0,st_mode=stat.S_IFSOCK|0o600)
        # This fake socket never makes an OS call; Linux credentials themselves
        # are covered by the Ubuntu harness, not emulated on the Mac.
        mocked('socket.SO_PEERCRED',create=True,new=getattr(socket,'SO_PEERCRED',17))
        self.sock=mocked('socket.socket').return_value.__enter__.return_value
        self.sock.getsockopt.return_value=struct.pack('3i',432,994,971)
        self.url='http://127.0.0.1:18765/#grant='+'A'*43
        self.response({'version':1,'url':self.url})
    def response(self,value):self.sock.recv.side_effect=[json.dumps(value).encode()+b'\n',b'']
    def test_designated_backend_or_root_server(self):
        for uid in (0,994):
            self.sock.getsockopt.return_value=struct.pack('3i',432,uid,971);self.response({'version':1,'url':self.url})
            self.assertEqual(pilot_cli.request('mint'),self.url)
    def test_foreign_server_never_receives_operation(self):
        self.sock.getsockopt.return_value=struct.pack('3i',432,1000,1000)
        with self.assertRaises(Denied):pilot_cli.request('mint')
        self.sock.sendall.assert_not_called()
    def test_ordinary_uid_never_connects(self):
        with patch('api.pilot_cli.os.getuid',return_value=1000):
            with self.assertRaises(Denied):pilot_cli.request('mint')
        self.config.assert_not_called();self.sock.connect.assert_not_called()
    def test_unknown_operation_never_connects(self):
        with self.assertRaises(Denied):pilot_cli.request('shell')
        self.sock.connect.assert_not_called()
    def test_unsafe_socket_metadata_refuses(self):
        for mode in (stat.S_IFLNK|0o600,stat.S_IFSOCK|0o666,stat.S_IFREG|0o600):
            self.path.lstat.return_value=SimpleNamespace(st_uid=0,st_mode=mode)
            with self.assertRaises(Denied):pilot_cli.request('mint')
        self.sock.connect.assert_not_called()
    def test_unprotected_parent_refuses(self):
        self.path.parent.lstat.return_value=SimpleNamespace(st_uid=0,st_mode=stat.S_IFDIR|0o755)
        with self.assertRaises(Denied):pilot_cli.request('mint')
        self.sock.connect.assert_not_called()
    def test_redirect_and_wrong_response_schema_refuse(self):
        for value in ({'version':1,'url':'http://evil.example/#grant='+'A'*43},{'version':True,'url':self.url},{'version':1,'url':self.url,'extra':1}):
            self.response(value)
            with self.assertRaises(Denied):pilot_cli.request('mint')

if __name__=='__main__':unittest.main()
