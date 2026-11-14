import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import uuid
from api.process_view import ProcessView,ViewError,_load,ProcessRows
from engine.database.process_store import Store
from engine.ingestion import process_contract as c
from test_process_pipeline import fixture,status,STAMP,PRODUCER


def rows(count=25):
    events=[];s=None
    for i in range(count):
        e=fixture(('fork','exec','exit')[i%3]);e['source']['mode']='live';s=e['source'];raw=c.dump(e);n=e['native']
        events.append(dict(ordinal=i+1,event_id=e['event_id'],source_id=s['source_id'],activation_id=s['activation_id'],producer_id=PRODUCER,boot_id=s['boot_id'],kind=n['what'],pid=n['tgid'],tid=n['tid'],observed_at=STAMP,received_at='2025-01-01T00:00:00.000000Z',envelope=raw,digest=hashlib.sha256(raw.encode()).hexdigest()))
    s=s or dict(fixture()['source'],mode='live')
    interval=dict(activation_id=s['activation_id'],producer_id=PRODUCER,source_id=s['source_id'],boot_id=s['boot_id'],acknowledged=0,delivery=1,incomplete=1,stopped=1,reason='native_gap',diagnostics=c.dump([4294967295]*20))
    return dict(events=events,intervals=[interval]),[dict(source_id=s['source_id'],activation_id=s['activation_id'])]


class ProcessViewTests(unittest.TestCase):
    def test_projection_time_roles_raw_precision_and_historical_status(self):
        r,s=rows();v=ProcessView(r,s);page=v.page('process','session')
        self.assertEqual(len(page['items']),20);self.assertEqual(page['items'][0]['arrival_ordinal'],'25')
        d=v.detail('process',page['items'][0]['event_id']);self.assertIsNone(d['envelope']['timestamps']['activity_wall_time'])
        self.assertEqual(d['envelope']['native']['timestamp_ns'],str(2**64-1));self.assertEqual(d['received_at'][:4],'2025')
        self.assertFalse(d['historical_interval']['acknowledged']);self.assertTrue(d['historical_interval']['delivery'])
        d['envelope']['native']['tid']=1;self.assertEqual(v.detail('process',d['event_id'])['envelope']['native']['tid'],42)
        self.assertEqual(v.summary()['monitoring_status'],'not_assessed')
    def test_cursors_bind_session_view_and_family(self):
        r,s=rows();v=ProcessView(r,s);cursor=v.page('process','one')['next_cursor']
        self.assertEqual(len(v.page('process','one',cursor)['items']),5)
        for view,kind,session,cur in [(v,'process','two',cursor),(ProcessView(r,s),'process','one',cursor),(v,'events','one',cursor),(v,'process','one',cursor+'x'),(v,'process','one','%41')]:
            with self.assertRaises(ViewError):view.page(kind,session,cur)
    def test_forged_metadata_canonical_bytes_missing_status_and_other_scope(self):
        for mutate in (lambda r:r['events'][0].update(pid=999),lambda r:r['events'][0].update(pid=True),lambda r:r['events'][0].update(digest='0'*64),lambda r:r['events'][0].update(envelope=r['events'][0]['envelope']+' '),lambda r:r.update(intervals=[]),lambda r:r['intervals'][0].update(stopped=2),lambda r:r['intervals'][0].update(diagnostics='[0]'),lambda r:r['intervals'][0].update(boot_id=str(uuid.uuid4())),lambda r:r['events'][0].update(source_id=str(uuid.uuid4())),lambda r:r['events'][0].update(ordinal=0)):
            r,s=rows();mutate(r)
            with self.assertRaises(ViewError):ProcessView(r,s)
    def test_closed_selections_caps_and_no_synthetic_mode(self):
        r,s=rows()
        for bad in ([],s+s,[dict(s[0],extra=True)],[dict(s[0],activation_id='x')]):
            with self.assertRaises(ViewError):ProcessView(r,bad)
        r,s=rows(129)
        with self.assertRaises(ViewError):ProcessView(r,s)
        r,s=rows();e=c.decode(r['events'][0]['envelope'].encode());e['source']['mode']='synthetic';r['events'][0]['envelope']=c.dump(e)
        with self.assertRaises(ViewError):ProcessView(r,s)
    def store(self,count=3):
        tmp=tempfile.TemporaryDirectory(prefix='hids-process-view.');self.addCleanup(tmp.cleanup);p=Path(tmp.name).resolve();p.chmod(0o700)
        r,selected=rows(count);source=c.decode(r['events'][0]['envelope'].encode())['source'];store=Store(p/'store.sqlite',source)
        self.addCleanup(store.close)
        for row in r['events']:store.put(c.decode(row['envelope'].encode()),row['received_at'])
        st=status(delivery=True,stopped=True);st['source']=source;store.interval(st,PRODUCER)
        identity=[store.path.stat().st_dev,store.path.stat().st_ino]
        return store,selected,identity
    def test_readonly_wal_consistent_and_closed_before_serving(self):
        store,selected,identity=self.store();before=store.conn.total_changes
        view=_load(store.path,selected,identity);self.assertEqual(view.summary()['counts']['events'],3);self.assertEqual(store.conn.total_changes,before)
        store.close();self.assertEqual(len(view.page('process','s')['items']),3)
    def test_schema_identity_permissions_and_huge_values_refused_without_repair(self):
        for fault in ('schema','identity','permissions','oversize','forgery'):
            store,selected,identity=self.store()
            if fault=='schema':store.conn.execute('CREATE TABLE foreign_table(x)')
            elif fault=='identity':identity[1]+=1
            elif fault=='permissions':store.path.chmod(0o644)
            elif fault=='oversize':store.conn.execute("UPDATE process_events SET envelope=?",('x'*100000,))
            else:store.conn.execute("UPDATE process_events SET tid=123")
            changes=store.conn.total_changes
            with self.subTest(fault=fault),self.assertRaises(ViewError):_load(store.path,selected,identity)
            self.assertEqual(store.conn.total_changes,changes)
    def test_sql_truncation_explicit_and_newest_first(self):
        store,selected,identity=self.store(130);view=_load(store.path,selected,identity)
        self.assertTrue(view.truncated);self.assertEqual(view.summary()['counts']['events'],128)
        self.assertEqual(view.page('process','s')['items'][0]['arrival_ordinal'],'130')

if __name__=='__main__':unittest.main()
