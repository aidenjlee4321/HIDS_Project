import copy
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
from engine.ingestion.m1_contract import Invalid
from engine.ingestion.m2_contract import decode, validate_event, event_id, canonical, frame, validate_response
from engine.database.m2_store import Store, get_event, RetrievalFailure
from engine.ingestion.m2_receiver import Listener, Receiver, TerminalFailure, PeerPolicy, Framer

ROOT=Path(__file__).resolve().parents[2]
BASE=json.loads((ROOT/'tests/fixtures/journal/ssh-event.json').read_text())
NOW='2026-11-07T00:00:00.000000Z'


class ContractTests(unittest.TestCase):
    def test_shared_vectors(self):
        for case in json.loads((ROOT/'tests/fixtures/journal/contract-cases.json').read_text()):
            with self.subTest(case=case['name']):
                outcome='valid'
                try:validate_event(decode(case['input'].encode('ascii')))
                except Invalid as e:outcome=e.code
                self.assertEqual(outcome,case['expected'])

    def test_framing_caps_split_coalesced(self):
        framer=Framer(3)
        self.assertEqual(list(framer.feed(b'ab')),[])
        self.assertEqual(list(framer.feed(b'c\n{}\n')),[b'abc',b'{}'])
        list(framer.feed(b'abc'))
        with self.assertRaises(Invalid):list(framer.feed(b'd'))
        self.assertEqual(len(framer.buffer),3)
        with self.assertRaises(Invalid):decode(b'x'*65537)
        with self.assertRaises(Invalid):validate_event(decode(b'{"x":"\\ud800"}'))

    def test_response_closed_shapes(self):
        ack={'protocol_version':2,'message_type':'ack','event_id':BASE['event_id'],'result':'stored','checkpoint_revision':1,'code':None}
        validate_response(ack,BASE['event_id'])
        for key,value in [('protocol_version',True),('result','unknown'),('checkpoint_revision',True),('event_id','wrong'),('extra',1),('code','wrong')]:
            bad=dict(ack);bad[key]=value
            with self.subTest(key=key),self.assertRaises(Invalid):validate_response(bad,BASE['event_id'])
        for kind,code in [('reject','unknown'),('error','wrong')]:
            with self.assertRaises(Invalid):validate_response({'protocol_version':2,'message_type':kind,'event_id':BASE['event_id'],'code':code},BASE['event_id'])

    def test_peer_negative_policy(self):
        fake=unittest.mock.Mock()
        import struct
        with patch.object(socket,'SO_PEERCRED',17,create=True):
            for pid,uid,gid in [(0,22,33),(1,23,33),(1,22,34),(2,22,33)]:
                fake.getsockopt.return_value=struct.pack('3i',pid,uid,gid)
                with self.assertRaises(PermissionError):PeerPolicy(22,33,1).check(fake)
            fake.getsockopt.return_value=struct.pack('3i',1,22,33)
            self.assertEqual(PeerPolicy(22,33,1).check(fake),1)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hids-m2-unit-');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name).resolve()/'journal.sqlite'
        self.store=Store(self.path,max_records=100,max_pages=128);self.addCleanup(self.store.close)
        self.store.activate(BASE['source_id'],BASE['activation_id'],authorized=True)
        self.store.boundary(BASE['source_id'],BASE['activation_id'],'initial-boundary',NOW,NOW)

    def progress(self):return self.store.progress(BASE['source_id'],BASE['activation_id'])

    def test_roundtrip_duplicate_observation_and_stale_receipt(self):
        ack=self.store.put(BASE,NOW);self.assertEqual(ack['result'],'stored')
        other=copy.deepcopy(BASE);other['cursor']='second';other['event_id']=event_id(other['source_id'],other['cursor']);other['expected_revision']=1
        self.store.put(other,NOW)
        replay=copy.deepcopy(BASE);replay['observation']['observed_at']='2026-11-07T00:00:02.000000Z'
        self.assertEqual(self.store.put(replay,NOW)['checkpoint_revision'],1)
        self.assertEqual(self.progress()['revision'],2)
        self.assertEqual(get_event(self.path,BASE['event_id']),BASE)
        self.assertEqual(canonical(replay),canonical(BASE))

    def test_conflict_stale_and_invalid_version_preserve_progress(self):
        self.store.put(BASE,NOW)
        bad=copy.deepcopy(BASE);bad['fields']['MESSAGE']='different'
        with self.assertRaisesRegex(Invalid,'id_conflict'):self.store.put(bad,NOW)
        bad=copy.deepcopy(BASE);bad['cursor']='new';bad['event_id']=event_id(bad['source_id'],bad['cursor'])
        with self.assertRaisesRegex(Invalid,'stale_revision'):self.store.put(bad,NOW)
        bad=copy.deepcopy(BASE);bad['protocol_version']=1
        with self.assertRaisesRegex(Invalid,'unsupported_version'):self.store.put(bad,NOW)
        self.assertEqual(self.progress()['revision'],1)
        self.assertEqual(get_event(self.path,BASE['event_id']),BASE)

    def test_atomic_failures_and_uncertain_commit(self):
        for stage in ('before_insert','after_insert','after_checkpoint','before_commit','after_commit'):
            def fault(s):
                if s==stage:raise sqlite3.OperationalError('injected')
            self.store.fault=fault
            with self.subTest(stage=stage),self.assertRaises(sqlite3.OperationalError):self.store.put(BASE,NOW)
            self.assertEqual(self.progress()['revision'],1 if stage=='after_commit' else 0)
            self.assertEqual(get_event(self.path,BASE['event_id']) is not None,stage=='after_commit')
        self.store.fault=lambda _:None
        self.assertEqual(self.store.put(BASE,NOW)['result'],'duplicate')

    def test_durable_rejection_duplicate_and_conflict(self):
        e={k:v for k,v in BASE.items() if k not in ('journal','fields','activity_wall_time','activity_wall_time_reason')}
        e['message_type']='journal_rejection';e['reason']='binary_field'
        self.assertEqual(self.store.put(e,NOW)['result'],'rejected_record')
        self.assertEqual(self.store.put(e,NOW)['result'],'rejected_record')
        self.assertEqual(self.progress()['cursor'],e['cursor'])
        e['reason']='malformed_field'
        with self.assertRaisesRegex(Invalid,'id_conflict'):self.store.put(e,NOW)

    def test_activation_revoke_gap_and_no_event_activation(self):
        with self.assertRaises(PermissionError):self.store.activate(BASE['source_id'],BASE['activation_id'])
        self.store.gap(BASE['source_id'],BASE['activation_id'],'cursor_gap')
        with self.assertRaisesRegex(Invalid,'inactive_source'):self.store.put(BASE,NOW)
        self.assertEqual(self.progress()['revision'],0)
        self.store.revoke(BASE['source_id'],BASE['activation_id'])
        with self.assertRaisesRegex(Invalid,'inactive_source'):self.progress()

    def test_empty_boundary_and_new_activation_revision(self):
        self.store.revoke(BASE['source_id'],BASE['activation_id'])
        with self.assertRaises(Invalid):self.store.activate(BASE['source_id'],BASE['activation_id'],authorized=True)
        new='40000000-0000-4000-8000-000000000004'
        self.store.activate(BASE['source_id'],new,authorized=True)
        self.store.boundary(BASE['source_id'],new,None,NOW,NOW)
        self.assertEqual(self.store.progress(BASE['source_id'],new)['state'],'empty_unanchored')
        event=copy.deepcopy(BASE);event['activation_id']=new
        self.store.put(event,NOW)
        self.assertEqual(self.store.progress(BASE['source_id'],new)['state'],'anchored')

    def test_profiles_permissions_readonly_and_storage_budget(self):
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode),0o600)
        self.assertEqual(self.store.conn.execute('PRAGMA journal_mode').fetchone()[0],'wal')
        self.store.max_records=1;self.store.put(BASE,NOW)
        bad=copy.deepcopy(BASE);bad['cursor']='two';bad['event_id']=event_id(bad['source_id'],bad['cursor']);bad['expected_revision']=1
        with self.assertRaises(sqlite3.OperationalError):self.store.put(bad,NOW)
        self.assertEqual(self.progress()['revision'],1)
        self.store.conn.execute('PRAGMA user_version=99')
        with self.assertRaises(RetrievalFailure):get_event(self.path,BASE['event_id'])

    def test_busy_database_and_startup_failure(self):
        other=sqlite3.connect(self.path,isolation_level=None);self.addCleanup(other.close);other.execute('BEGIN IMMEDIATE')
        with self.assertRaises(sqlite3.OperationalError):self.store.put(BASE,NOW)
        other.execute('ROLLBACK');self.assertEqual(self.progress()['revision'],0)
        with self.assertRaises(sqlite3.OperationalError):Store(self.path,max_records=100,max_pages=128,fault=lambda _:(_ for _ in ()).throw(sqlite3.OperationalError('startup')))


class SocketTests(unittest.TestCase):
    setUp=StorageTests.setUp
    progress=StorageTests.progress
    def test_socket_owner_group_mode_and_failure(self):
        directory=self.path.parent/'ipc';directory.mkdir(mode=0o750)
        os.chmod(directory,0o750)  # Own fixture directory; independent of caller umask.
        path=directory/'journal.sock';uid,gid=os.getuid(),os.getgid()
        listener=Listener(path,uid,gid)
        self.addCleanup(listener.close)
        info=path.stat();self.assertEqual((info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)),(uid,gid,0o660))
        with self.assertRaises(PermissionError):Listener(path,uid,gid)
        listener.close()
        with patch('engine.ingestion.m2_receiver.os.chown',side_effect=PermissionError('injected')):
            with self.assertRaises(PermissionError):Listener(path,uid,gid)
        self.assertFalse(path.exists())
        with patch('engine.ingestion.m2_receiver.os.chmod'):
            with self.assertRaises(PermissionError):Listener(path,uid,gid)
        self.assertFalse(path.exists())

    def test_split_coalesced_frames_commit(self):
        peer=unittest.mock.Mock();receiver=Receiver(self.store,BASE['source_id'],BASE['activation_id'],peer)
        a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
        errors=[];responses=[]
        def client():
            try:
                wire=frame(BASE);a.sendall(wire[:13]);a.sendall(wire[13:]+wire)
                a.settimeout(3);data=b''
                while data.count(b'\n')<2:
                    chunk=a.recv(4096)
                    if not chunk:raise EOFError('missing_responses')
                    data+=chunk
                responses.extend(decode(x) for x in data.splitlines())
            except Exception as e:errors.append(e)
            finally:a.shutdown(socket.SHUT_WR)
        thread=threading.Thread(target=client);thread.start()
        receiver.serve(b);thread.join(3)
        self.assertFalse(thread.is_alive());self.assertFalse(errors)
        self.assertEqual([x['result'] for x in responses],['stored','duplicate'])
        self.assertEqual(self.progress()['revision'],1);peer.check.assert_called_once()

    def test_peer_denied_before_bytes_and_terminal_malformed(self):
        peer=unittest.mock.Mock();peer.check.side_effect=PermissionError('denied')
        receiver=Receiver(self.store,BASE['source_id'],BASE['activation_id'],peer)
        fake=unittest.mock.Mock()
        with self.assertRaises(PermissionError):receiver.serve(fake)
        fake.recv.assert_not_called()
        peer.check.side_effect=None
        a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
        a.sendall(b'{\n');a.shutdown(socket.SHUT_WR)
        with self.assertRaises(TerminalFailure):receiver.serve(b)
        self.assertTrue(receiver.failed);self.assertEqual(self.progress()['revision'],0)

    def test_lost_ack_reconcile_and_duplicate(self):
        receiver=Receiver(self.store,BASE['source_id'],BASE['activation_id'],unittest.mock.Mock())
        a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
        a.sendall(frame(BASE));a.shutdown(socket.SHUT_WR)
        def lost(_):raise BrokenPipeError('lost_ack')
        receiver.serve(b,response_hook=lost)
        self.assertFalse(receiver.failed)
        p=receiver.handle({'protocol_version':2,'message_type':'reconcile'})
        self.assertEqual(p['revision'],1)
        self.assertEqual(receiver.handle(BASE)['result'],'duplicate')

    def test_storage_error_is_unconfirmed_and_terminal(self):
        receiver=Receiver(self.store,BASE['source_id'],BASE['activation_id'],unittest.mock.Mock())
        a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
        a.sendall(frame(BASE));a.shutdown(socket.SHUT_WR)
        def fault(stage):
            if stage=='after_commit':raise sqlite3.OperationalError('uncertain')
        self.store.fault=fault
        with self.assertRaises(TerminalFailure):receiver.serve(b)
        raw=a.recv(2049);self.assertTrue(raw.endswith(b'\n'))
        response=decode(raw[:-1]);validate_response(response,BASE['event_id'])
        self.assertEqual(response['code'],'storage_error')
        self.assertTrue(receiver.failed)
        self.assertEqual(self.progress()['revision'],1)
        self.assertEqual(get_event(self.path,BASE['event_id']),BASE)
