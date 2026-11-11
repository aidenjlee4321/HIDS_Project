import os
from pathlib import Path
import socket
import tempfile
import unittest

from engine.ingestion.m3_service import open_data_listener


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve() / 'ipc'
        self.directory.mkdir(mode=0o750)
        os.chown(self.directory, os.getuid(), os.getgid())
        os.chmod(self.directory, 0o750)
        self.path = self.directory / 'audit.sock'

    def open_listener(self):
        listener = open_data_listener(self.path, os.getuid(), os.getgid())
        self.addCleanup(listener.close)
        return listener

    def test_recovers_only_a_closed_owned_socket(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
            stale.bind(str(self.path))
            self.path.chmod(0o660)
        listener = self.open_listener()
        self.assertTrue(self.path.is_socket())
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as caller:
            caller.connect(str(self.path))
            connection, _ = listener.sock.accept()
            connection.close()

    def test_live_listener_is_preserved(self):
        self.open_listener()
        original = self.path.stat()
        with self.assertRaisesRegex(PermissionError, 'still_listening'):
            self.open_listener()
        current = self.path.stat()
        self.assertEqual((current.st_dev, current.st_ino), (original.st_dev, original.st_ino))

    def test_regular_file_symlink_and_wrong_socket_mode_are_preserved(self):
        self.path.write_bytes(b'protected fixture')
        with self.assertRaises(PermissionError):
            self.open_listener()
        self.assertEqual(self.path.read_bytes(), b'protected fixture')
        self.path.unlink()
        target = self.directory / 'target'
        target.write_bytes(b'protected target')
        self.path.symlink_to(target)
        with self.assertRaises(PermissionError):
            self.open_listener()
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_bytes(), b'protected target')
        self.path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
            stale.bind(str(self.path))
            self.path.chmod(0o600)
        with self.assertRaises(PermissionError):
            self.open_listener()
        self.assertTrue(self.path.is_socket())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
