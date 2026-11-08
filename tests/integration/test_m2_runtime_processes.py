"""Actual local lifecycle processes with synthetic JournalIo and fixture root control."""
import json
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from engine.database.m2_store import Store, get_event
from engine.ingestion.m2_contract import decode, frame
from engine.ingestion.m2_receiver import Listener, PeerPolicy
from engine.ingestion.m2_service import Service

ROOT=Path(__file__).resolve().parents[2]
BASE=json.loads((ROOT/'tests/fixtures/journal/ssh-event.json').read_text())
PRODUCER=os.environ.get('HIDS_M2_RUNTIME_FIXTURE')

class FixtureControlPolicy:
    def check(self,sock):return os.getpid()


def server(root,ready,stopped):
    root=Path(root);data=control=store=service=None
    try:
        ipc=root/'ipc';ipc.mkdir();os.chmod(ipc,0o750)
        data=Listener(ipc/'journal.sock',os.getuid(),os.getgid())
        control=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        control.bind(str(root/'control.sock'));control.listen(4)
        store=Store(root/'journal.sqlite',max_records=100,max_pages=128)
        peer=PeerPolicy(os.getuid(),os.getgid()) if hasattr(socket,'SO_PEERCRED') else FixtureControlPolicy()
        service=Service(store,BASE['source_id'],data.sock,control,peer,control_peer=FixtureControlPolicy(),stopped=stopped.is_set)
        ready.send('ready');service.run()
    except BaseException as exc:
        ready.send(type(exc).__name__)
        raise
    finally:
        if service:service.close()
        if store:store.close()
        if data:data.close()
        if control:control.close()
        ready.close()


@unittest.skipUnless(PRODUCER,'set HIDS_M2_RUNTIME_FIXTURE to compiled fake-journal lifecycle executable')
class RuntimeProcesses(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hids-m2-process-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        ctx=multiprocessing.get_context('fork');parent,child=ctx.Pipe(False)
        self.stop=ctx.Event();self.server=ctx.Process(target=server,args=(str(self.root),child,self.stop));self.server.start();child.close()
        self.addCleanup(self.cleanup_server)
        self.assertTrue(parent.poll(5));self.assertEqual(parent.recv(),'ready');parent.close()
        self.children=[];self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        for child in self.children:
            if child.poll() is None:child.terminate()
            try:child.communicate(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.communicate(timeout=3)

    def cleanup_server(self):
        self.stop.set();self.server.join(3)
        if self.server.is_alive():self.server.terminate();self.server.join(3)
        if self.server.is_alive():self.server.kill();self.server.join(3)

    def command(self,name):
        obj={'protocol_version':2,'command':name}
        if name!='status':obj.update(source_id=BASE['source_id'],activation_id=BASE['activation_id'])
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(3);sock.connect(str(self.root/'control.sock'));sock.sendall(frame(obj));raw=bytearray()
            while True:
                b=sock.recv(1)
                if not b:raise EOFError('control_unconfirmed')
                if b==b'\n':break
                if len(raw)>=2048:raise ValueError('response_cap')
                raw.extend(b)
            return decode(bytes(raw),2048)

    def child(self,mode):
        p=subprocess.Popen([PRODUCER,str(ROOT/'tests/fixtures/journal/ssh-event.json'),str(self.root/'ipc/journal.sock'),mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.children.append(p);return p

    def wait(self,predicate):
        end=time.monotonic()+4
        while not predicate():
            if time.monotonic()>=end:self.fail('lifecycle state not established')
            time.sleep(.02)

    def test_denial_then_full_runtime_pipeline(self):
        denied=self.child('once');out,err=denied.communicate(timeout=4)
        self.assertEqual(denied.returncode,0,err);self.assertEqual(json.loads(out)['opens'],0)
        self.command('activate');producer=self.child('once');out,err=producer.communicate(timeout=5)
        self.assertEqual(producer.returncode,0,err);self.assertTrue(json.loads(out)['emitted'])
        self.assertEqual(get_event(self.root/'journal.sqlite',BASE['event_id']),BASE)
        self.assertEqual(self.command('status')['revision'],1)

    def test_reader_crash_restarts_from_same_checkpoint(self):
        self.command('activate');idle=self.child('idle')
        self.wait(lambda:self.command('status')['state']=='anchored')
        idle.kill();idle.communicate(timeout=3)
        self.wait(lambda:not self.command('status')['reader_connected'])
        restarted=self.child('once');out,err=restarted.communicate(timeout=5)
        self.assertEqual(restarted.returncode,0,err);self.assertTrue(json.loads(out)['emitted'])
        self.assertEqual(self.command('status')['revision'],1)
        self.assertEqual(get_event(self.root/'journal.sqlite',BASE['event_id']),BASE)

    def test_empty_crash_records_gap_instead_of_retail(self):
        self.command('activate');empty=self.child('empty')
        self.wait(lambda:self.command('status')['state']=='empty_unanchored')
        empty.kill();empty.communicate(timeout=3)
        self.wait(lambda:not self.command('status')['reader_connected'])
        restarted=self.child('once');out,err=restarted.communicate(timeout=5)
        self.assertEqual(restarted.returncode,1,err);self.assertEqual(json.loads(out)['opens'],0)
        self.assertEqual(self.command('status')['state'],'gap')
        self.assertIsNone(get_event(self.root/'journal.sqlite',BASE['event_id']))

    def test_deactivation_and_sigterm_bounded_shutdown(self):
        self.command('activate');idle=self.child('idle')
        self.wait(lambda:self.command('status')['state']=='anchored')
        self.command('deactivate');started=time.monotonic();idle.communicate(timeout=3)
        self.assertLess(time.monotonic()-started,3)
        self.assertEqual(idle.returncode,0)
        self.assertEqual(self.command('status')['state'],'revoked')
        self.assertIsNone(get_event(self.root/'journal.sqlite',BASE['event_id']))

    def test_sigterm_closes_reader_without_revoking_checkpoint(self):
        self.command('activate');idle=self.child('idle')
        self.wait(lambda:self.command('status')['state']=='anchored')
        started=time.monotonic();idle.send_signal(signal.SIGTERM);idle.communicate(timeout=3)
        self.assertEqual(idle.returncode,0)
        self.assertLess(time.monotonic()-started,3)
        self.wait(lambda:not self.command('status')['reader_connected'])
        self.assertEqual(self.command('status')['state'],'anchored')
