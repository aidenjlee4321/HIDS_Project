"""Synthetic control/lifecycle tests. No root, NSS grants or journal access."""
import copy
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from engine.database.m2_store import Store, get_event
from engine.ingestion.m2_contract import decode, frame
from engine.ingestion.m2_receiver import Listener
from engine.ingestion.m2_service import RootPolicy, Service

ROOT=Path(__file__).resolve().parents[2]
BASE=json.loads((ROOT/'tests/fixtures/journal/ssh-event.json').read_text())
NOW='2026-11-07T00:00:00.000000Z'
RECONCILE={'protocol_version':2,'message_type':'reconcile'}
BOUNDARY={'protocol_version':2,'message_type':'boundary','cursor':'baseline','started_at':NOW,'ended_at':NOW}

class FixturePolicy:
    def check(self,sock):
        return os.getpid()  # Explicit fixture seam; production always SO_PEERCRED.

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hids-m2-loop-')
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name).resolve()
        ipc=root/'ipc';ipc.mkdir();os.chmod(ipc,0o750)
        self.data=Listener(ipc/'journal.sock',os.getuid(),os.getgid())
        self.addCleanup(self.data.close)
        self.control=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.control_path=root/'control.sock';self.control.bind(str(self.control_path));self.control.listen(4)
        self.addCleanup(self.control.close)
        self.store=Store(root/'journal.sqlite',max_records=100,max_pages=128)
        self.addCleanup(self.store.close)
        self.now=0.
        self.service=Service(self.store,BASE['source_id'],self.data.sock,self.control,FixturePolicy(),
                             control_peer=FixturePolicy(),clock=lambda:self.now)
        self.addCleanup(self.service.close)

    def pump(self,predicate):
        end=time.monotonic()+4
        while not predicate():
            self.service.run_once()
            if time.monotonic()>end:self.fail('bounded loop did not finish')

    def connect(self,control=False):
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        sock.settimeout(3);sock.connect(str(self.control_path if control else self.data.path))
        self.addCleanup(sock.close)
        self.service.run_once()
        return sock

    def rpc(self,sock,obj):
        result=[];errors=[]
        def client():
            try:
                sock.sendall(obj if isinstance(obj,bytes) else frame(obj))
                payload=bytearray()
                while True:
                    b=sock.recv(1)
                    if not b:raise EOFError('unconfirmed')
                    if b==b'\n':break
                    if len(payload)>=2048:raise ValueError('response_cap')
                    payload.extend(b)
                result.append(decode(bytes(payload),2048))
            except Exception as e:errors.append(e)
        thread=threading.Thread(target=client);thread.start()
        self.pump(lambda:not thread.is_alive());thread.join(1)
        return result[0] if result else errors[0]

    def command(self,name):
        obj={'protocol_version':2,'command':name}
        if name!='status':obj.update(source_id=BASE['source_id'],activation_id=BASE['activation_id'])
        return self.rpc(self.connect(True),obj)

    def initialized(self,empty=False):
        self.assertEqual(self.command('activate')['result'],'activated')
        sock=self.connect();self.assertEqual(self.rpc(sock,RECONCILE)['state'],'initializing')
        boundary=dict(BOUNDARY)
        if empty:boundary['cursor']=None
        self.assertEqual(self.rpc(sock,boundary)['message_type'],'boundary_ack')
        return sock

    def test_denial_no_event_can_activate_and_root_policy(self):
        response=self.rpc(self.connect(),BASE)
        self.assertEqual(response['code'],'inactive_source')
        self.assertIsNone(self.service.current())
        import struct
        peer=Mock();peer.getsockopt.return_value=struct.pack('3i',123,os.getuid(),os.getgid())
        with patch.object(socket,'SO_PEERCRED',17,create=True):
            with self.assertRaises(PermissionError):RootPolicy().check(peer)
        self.service.control_peer=RootPolicy()
        sock=self.connect(True)
        # On Darwin RootPolicy fails closed without SO_PEERCRED; on Linux nonroot is denied.
        self.assertEqual(sock.recv(1),b'')
        self.assertIsNone(self.service.current())

    def test_activation_boundary_event_deactivation(self):
        sock=self.initialized()
        self.assertEqual(self.rpc(sock,BASE)['result'],'stored')
        self.assertEqual(get_event(self.store.path,BASE['event_id']),BASE)
        self.assertEqual(self.command('deactivate')['result'],'deactivated')
        self.assertEqual(self.service.current()[2],'revoked')
        self.assertIsNone(self.service.reader)

    def test_ready_deactivation_precedes_event_commit(self):
        reader=self.initialized();control=self.connect(True)
        reader.sendall(frame(BASE))
        control.sendall(frame({'protocol_version':2,'command':'deactivate','source_id':BASE['source_id'],'activation_id':BASE['activation_id']}))
        self.service.run_once();self.service.run_once()
        self.assertEqual(self.service.current()[2],'revoked')
        self.assertIsNone(get_event(self.store.path,BASE['event_id']))

    def test_empty_journal_persisted_and_restart_gap(self):
        reader=self.initialized(empty=True);reader.close()
        self.pump(lambda:self.service.reader is None)
        replacement=self.connect();self.assertEqual(self.rpc(replacement,RECONCILE)['state'],'empty_unanchored')
        self.assertEqual(self.rpc(replacement,{'protocol_version':2,'message_type':'gap','code':'unanchored_restart_gap'})['message_type'],'gap_ack')
        self.assertEqual(self.service.current()[2],'gap')

    def test_crash_before_boundary_does_not_retail(self):
        self.command('activate');reader=self.connect();self.rpc(reader,RECONCILE)
        reader.close();self.pump(lambda:self.service.reader is None)
        self.assertEqual(self.service.current()[2],'gap')
        result=self.rpc(self.connect(),RECONCILE)
        self.assertEqual(result['code'],'inactive_source')

    def test_reader_crash_and_lease_expiry_preserve_checkpoint(self):
        reader=self.initialized();self.rpc(reader,BASE);reader.close()
        self.pump(lambda:self.service.reader is None)
        replacement=self.connect();p=self.rpc(replacement,RECONCILE)
        self.assertEqual((p['revision'],p['cursor']),(1,BASE['cursor']))
        self.now=6;self.service.run_once();self.assertIsNone(self.service.reader)
        row=self.store.conn.execute('SELECT code FROM gaps ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(row[0],'lease_expired')
        self.assertEqual(self.service.current()[2],'anchored')
        newest=self.connect();self.assertEqual(self.rpc(newest,RECONCILE)['revision'],1)

    def test_concurrent_reader_cannot_displace_lease(self):
        reader=self.initialized();old=self.service.reader
        other=self.connect();self.assertEqual(other.recv(1),b'')
        self.assertIs(self.service.reader,old)
        self.assertEqual(self.rpc(reader,RECONCILE)['revision'],0)

    def test_lost_event_ack_replay_is_idempotent(self):
        reader=self.initialized();lost=[False]
        def hook(response):
            if response.get('message_type')=='ack' and not lost[0]:
                lost[0]=True;raise BrokenPipeError('lost_ack')
            return response
        self.service.response_hook=hook
        self.assertIsInstance(self.rpc(reader,BASE),EOFError)
        retry=self.connect();self.assertEqual(self.rpc(retry,RECONCILE)['revision'],1)
        self.assertEqual(self.rpc(retry,BASE)['result'],'duplicate')
        self.assertEqual(self.service.current()[3],1)

    def test_lost_boundary_ack_never_chooses_new_tail(self):
        self.command('activate');reader=self.connect();self.rpc(reader,RECONCILE)
        lost=[False]
        def hook(response):
            if response.get('message_type')=='boundary_ack' and not lost[0]:
                lost[0]=True;raise BrokenPipeError('lost_boundary')
            return response
        self.service.response_hook=hook
        self.assertIsInstance(self.rpc(reader,BOUNDARY),EOFError)
        retry=self.connect();p=self.rpc(retry,RECONCILE)
        self.assertEqual((p['state'],p['cursor']),('anchored','baseline'))
        self.assertEqual(self.rpc(retry,BOUNDARY)['message_type'],'boundary_ack')
        changed=dict(BOUNDARY,cursor='later-tail')
        self.assertEqual(self.rpc(retry,changed)['code'],'stale_revision')
        self.assertEqual(self.service.current()[3],0)

    def test_rotation_gap_is_durable(self):
        reader=self.initialized()
        result=self.rpc(reader,{'protocol_version':2,'message_type':'gap','code':'cursor_gap'})
        self.assertEqual(result['message_type'],'gap_ack')
        self.assertEqual(self.service.current()[2],'gap')
        self.assertEqual(self.store.conn.execute('SELECT code FROM gaps').fetchone()[0],'cursor_gap')

    def test_uncertain_storage_commit_stops_events_preserves_record(self):
        reader=self.initialized()
        def fail(stage):
            if stage=='after_commit':raise sqlite3.OperationalError('uncertain')
        self.store.fault=fail
        result=self.rpc(reader,BASE)
        self.assertEqual(result['code'],'storage_error')
        self.assertEqual(get_event(self.store.path,BASE['event_id']),BASE)
        self.assertEqual(self.service.failure,'storage_outcome_unconfirmed')
        self.store.fault=lambda _:None
        self.assertEqual(self.command('status')['failure'],'storage_outcome_unconfirmed')
        self.assertEqual(self.rpc(self.connect(),BASE)['code'],'inactive_source')

    def test_shutdown_is_bounded_and_no_new_activation_processed(self):
        reader=self.initialized();self.service.stopped=lambda:True
        started=time.monotonic();self.service.run()
        self.assertLess(time.monotonic()-started,1)
        self.assertIsNone(self.service.reader)
        self.assertEqual(self.store.conn.execute('SELECT code FROM gaps ORDER BY id DESC LIMIT 1').fetchone()[0],'ingest_shutdown')
        self.assertEqual(reader.recv(1),b'')

    def test_slow_receiver_has_bounded_output_and_expires(self):
        reader=self.initialized()
        self.service.reader.sock.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1024)
        reader.sendall(frame(RECONCILE)*80)
        for _ in range(15):self.service.run_once()
        client=self.service.reader
        self.assertIsNotNone(client)
        self.assertLessEqual(len(client.output),2049)
        self.assertLessEqual(len(client.framer.buffer),65536)
        self.now=6;self.service.run_once()
        self.assertIsNone(self.service.reader)
        self.assertEqual(self.service.current()[2],'anchored')

    def test_shutdown_ready_control_request_is_not_applied(self):
        control=self.connect(True)
        control.sendall(frame({'protocol_version':2,'command':'activate','source_id':BASE['source_id'],'activation_id':BASE['activation_id']}))
        self.service.stopped=lambda:True
        self.service.run()
        self.assertIsNone(self.service.current())

class IdentityPolicyTests(unittest.TestCase):
    def test_ingest_never_inherits_journal_or_root_group(self):
        from types import SimpleNamespace
        from engine.ingestion.m2_receiver import service_policy
        accounts={'hids-journal':SimpleNamespace(pw_uid=997,pw_gid=1001),
                  'hids-ingest':SimpleNamespace(pw_uid=998,pw_gid=1002)}
        groups={'hids-journal':1001,'hids-ingest':1002,'hids-ipc':1003,'systemd-journal':190}
        with patch('engine.ingestion.m2_receiver.pwd.getpwnam',side_effect=accounts.get), \
             patch('engine.ingestion.m2_receiver.grp.getgrnam',side_effect=lambda name:SimpleNamespace(gr_gid=groups[name])), \
             patch('engine.ingestion.m2_receiver.os.getuid',return_value=998), \
             patch('engine.ingestion.m2_receiver.os.geteuid',return_value=998), \
             patch('engine.ingestion.m2_receiver.os.getgid',return_value=1002), \
             patch('engine.ingestion.m2_receiver.os.getegid',return_value=1002), \
             patch('engine.ingestion.m2_receiver.os.getgroups',return_value=[1002,1003]) as membership:
            peer,ipc=service_policy('ingest')
            self.assertEqual((peer.uid,peer.gid,ipc),(997,1001,1003))
            membership.return_value=[1002,1003,190]
            with self.assertRaises(PermissionError):service_policy('ingest')
            membership.return_value=[1002,1003]
            accounts['hids-ingest'].pw_gid=0
            with self.assertRaises(PermissionError):service_policy('ingest')
