"""Local synthetic two-process test. Peer doubles on macOS are explicitly scoped."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from engine.database.m2_store import Store, get_event
from engine.ingestion.m2_receiver import Receiver, PeerPolicy

ROOT=Path(__file__).resolve().parents[2]
BASE=json.loads((ROOT/'tests/fixtures/journal/ssh-event.json').read_text())
PRODUCER=os.environ.get('HIDS_M2_FIXTURE_PRODUCER')


@unittest.skipUnless(PRODUCER,'set HIDS_M2_FIXTURE_PRODUCER to compiled synthetic producer')
class FixturePipeline(unittest.TestCase):
    def test_cpp_native_normalization_socket_python_sqlite_readonly(self):
        with tempfile.TemporaryDirectory(prefix='hids-m2-fixture-') as tmp:
            store=Store(Path(tmp).resolve()/'journal.sqlite',max_records=10,max_pages=128)
            self.addCleanup(store.close)
            store.activate(BASE['source_id'],BASE['activation_id'],authorized=True)
            now='2026-11-07T00:00:00.000000Z'
            store.boundary(BASE['source_id'],BASE['activation_id'],'baseline',now,now)
            parent,child=socket.socketpair()
            self.addCleanup(parent.close)
            proc=subprocess.Popen([PRODUCER,str(ROOT/'tests/fixtures/journal/ssh-event.json'),str(child.fileno())],pass_fds=(child.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            child.close()
            try:
                peer=PeerPolicy(os.getuid(),os.getgid()) if hasattr(socket,'SO_PEERCRED') else Mock()
                Receiver(store,BASE['source_id'],BASE['activation_id'],peer).serve(parent)
                stdout,stderr=proc.communicate(timeout=7)
                self.assertEqual(proc.returncode,0,stderr)
                self.assertEqual(json.loads(stdout)['result'],'stored')
                self.assertEqual(get_event(store.path,BASE['event_id']),BASE)
                self.assertEqual(store.progress(BASE['source_id'],BASE['activation_id'])['revision'],1)
            finally:
                if proc.poll() is None:proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
