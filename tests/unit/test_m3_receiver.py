import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from engine.ingestion.m3_progress import Progress, ProgressError
from engine.ingestion.m3_receiver import Receiver


class FixturePeer:
    def check(self, connection):
        pass


class ReceiverTests(unittest.TestCase):
    scope = {"activation": "a", "generation": "g", "lease": "l"}

    def test_idle_connection_survives_until_partial_frame_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Progress(Path(directory) / "ledger", "a", "g", 0)
            receiver = Receiver(ledger, self.scope, FixturePeer(), timeout=0.05)
            server, client = socket.socketpair()
            release = threading.Event()
            sent = threading.Event()

            def send_partial():
                with client:
                    if release.wait(0.15):
                        return
                    try:
                        client.sendall(b"{")
                        sent.set()
                        client.settimeout(1)
                        client.recv(1)
                    except OSError:
                        pass

            thread = threading.Thread(target=send_partial)
            thread.start()
            try:
                with self.assertRaises(TimeoutError):
                    receiver.serve(server)
                self.assertEqual(ledger.positions(), (0, 0))
                # A timeout before the client sends would break a quiet Audit stream.
                self.assertTrue(sent.is_set())
            finally:
                release.set()
                thread.join(2)
                ledger.close()

    def test_disconnect_suppresses_and_cannot_reopen_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Progress(Path(directory) / "ledger", "a", "g", 0)
            receiver = Receiver(ledger, self.scope, FixturePeer())
            server, client = socket.socketpair()
            frame = json.dumps(dict(self.scope, version=3, op="register",
                                    identity="1.001:1", begin=0, end=10, eoe=False)).encode() + b"\n"
            replies = []

            def send():
                with client:
                    client.settimeout(3)
                    client.sendall(frame[:15])
                    client.sendall(frame[15:])
                    replies.append(client.recv(100))

            thread = threading.Thread(target=send)
            thread.start()
            try:
                receiver.serve(server)
                thread.join(3)
                self.assertEqual([json.loads(reply) for reply in replies],
                                 [{"version": 3, "status": "admit"}])
                self.assertEqual(ledger.positions(), (10, 10))
                self.assertEqual(ledger.register("1.001:1", 10, 20), "suppressed")
                other, caller = socket.socketpair()
                with caller, self.assertRaisesRegex(ProgressError, "lease"):
                    receiver.serve(other)
            finally:
                thread.join(4)
                ledger.close()

    def test_revocation_rejects_before_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Progress(Path(directory) / "ledger", "a", "g", 0)
            receiver = Receiver(ledger, self.scope, FixturePeer())
            receiver.revoke()
            server, client = socket.socketpair()
            try:
                with client, self.assertRaisesRegex(ProgressError, "lease"):
                    receiver.serve(server)
                self.assertEqual(ledger.positions(), (0, 0))
            finally:
                ledger.close()
