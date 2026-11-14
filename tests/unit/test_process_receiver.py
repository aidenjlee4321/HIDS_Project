import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from engine.ingestion import process_contract as c
from engine.ingestion.process_receiver import serve
from test_process_pipeline import SOURCE,PRODUCER,fixture,status

class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hids-process-ipc.',dir='/tmp');self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        (self.root/'db').mkdir(mode=0o700);self.path=self.root/'db/store.sqlite'
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.socket=self.root/'e.sock';self.listener.bind(str(self.socket));self.socket.chmod(0o600);self.listener.listen(1)
        self.stop=threading.Event();self.ready=threading.Event();self.errors=[];self.thread=None
    def tearDown(self):
        self.stop.set()
        if self.thread:self.thread.join(4);self.assertFalse(self.thread.is_alive())
        self.listener.close();self.tmp.cleanup()
    def start(self,**kw):
        def run():
            try:serve(self.listener,self.path,SOURCE,kw.pop('expected_uid',os.getuid()),mode='synthetic',stopped=self.stop.is_set,ready=self.ready.set,timeout=1,**kw)
            except Exception as exc:self.errors.append(exc)
        self.thread=threading.Thread(target=run);self.thread.start();self.assertTrue(self.ready.wait(3))
    def client(self):
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(3);s.connect(str(self.socket));return s
    def exchange(self,s,value):
        s.sendall(c.dump(value).encode()+b'\n');data=bytearray()
        while not data.endswith(b'\n'):data.extend(s.recv(1024))
        return c.decode(bytes(data[:-1]))
    def rows(self):
        db=sqlite3.connect(self.path)
        try:return db.execute('SELECT ordinal,envelope FROM process_events ORDER BY ordinal').fetchall()
        finally:db.close()
    def finish(self):
        self.thread.join(4);self.assertFalse(self.thread.is_alive())
    def test_cpp_native_packet_to_durable_store(self):
        tool=os.environ['HIDS_PROCESS_SENDER'];self.start()
        p=subprocess.run([tool,str(self.socket),str(os.getuid())],capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);self.finish();self.assertFalse(self.errors)
        rows=self.rows();self.assertEqual([r[0] for r in rows],[1,2,3]);events=[c.decode(r[1].encode()) for r in rows]
        self.assertEqual([e['native']['what'] for e in events],['PROC_EVENT_FORK','PROC_EVENT_EXEC','PROC_EVENT_EXIT'])
        self.assertTrue(all(e['native']['timestamp_ns']=='18446744073709551615' for e in events))
        db=sqlite3.connect(self.path);self.assertEqual(db.execute('SELECT acknowledged,delivery,incomplete,stopped FROM process_intervals').fetchone(),(0,1,0,1));db.close()
    def test_commit_ack_duplicate_and_conflicting_payload(self):
        self.start()
        with self.client() as s:
            self.assertEqual(self.exchange(s,status())['message_type'],'status_ack')
            e=fixture();self.assertEqual(self.exchange(s,e)['result'],'stored');self.assertEqual(self.exchange(s,e)['result'],'duplicate')
            e['native']['connector_sequence']=1;self.assertEqual(self.exchange(s,e)['code'],'id_conflict')
        self.finish();self.assertEqual(len(self.rows()),1)
    def test_after_commit_failure_resolves_before_ack_without_second_insert(self):
        calls=[]
        def fault(stage):
            calls.append(stage)
            if stage=='after_commit':raise OSError('synthetic uncertain commit')
        self.start(store_options={'fault':fault})
        with self.client() as sock:
            self.exchange(sock,status());self.assertEqual(self.exchange(sock,fixture())['result'],'duplicate')
            self.exchange(sock,status(stopped=True,reason='stopped'))
        self.finish();self.assertFalse(self.errors);self.assertEqual(len(self.rows()),1);self.assertEqual(calls.count('before_insert'),1)
    def test_uncommitted_failure_never_gets_success_ack(self):
        def fault(stage):
            if stage=='before_commit':raise OSError('synthetic precommit error')
        self.start(store_options={'fault':fault})
        with self.client() as sock:
            self.exchange(sock,status());self.assertEqual(self.exchange(sock,fixture())['code'],'storage_error')
        self.finish();self.assertEqual(self.rows(),[])
        db=sqlite3.connect(self.path)
        try:self.assertEqual(db.execute('SELECT incomplete,stopped,reason FROM process_intervals').fetchone(),(1,1,'storage_failed'))
        finally:db.close()
    def test_unenrolled_event_refused_before_storage(self):
        self.start()
        with self.client() as s:self.assertEqual(self.exchange(s,fixture())['message_type'],'error')
        self.finish();self.assertEqual(self.rows(),[])
    def test_foreign_scope_status_refused(self):
        self.start()
        with self.client() as s:
            value=status();value['source']['activation_id']='66000000-0000-4000-8000-000000000006';self.assertEqual(self.exchange(s,value)['message_type'],'error')
        self.finish();self.assertEqual(self.rows(),[])
    def test_peer_uid_denial(self):
        self.start(expected_uid=os.getuid()+10000)
        with self.client() as s:
            try:s.sendall(b'{}\n');self.assertEqual(s.recv(32),b'')
            except ConnectionResetError:pass
        self.finish();self.assertEqual(self.rows(),[])
    def test_capacity_error_preserves_first_commit(self):
        self.start(store_options={'max_events':1})
        with self.client() as s:
            self.exchange(s,status());self.assertEqual(self.exchange(s,fixture())['result'],'stored');self.assertEqual(self.exchange(s,fixture('exit'))['code'],'capacity_exceeded')
        self.finish();self.assertEqual(len(self.rows()),1)
    def test_partial_frame_eof_not_committed(self):
        self.start()
        with self.client() as s:s.sendall(b'{"protocol_version":1')
        self.finish();self.assertEqual(self.rows(),[])
    def test_oversize_frame_rejected(self):
        self.start()
        with self.client() as s:
            try:s.sendall(b'x'*16385+b'\n');s.recv(1024)
            except (BrokenPipeError,ConnectionResetError):pass
        self.finish();self.assertEqual(self.rows(),[])

if __name__=='__main__':unittest.main()
