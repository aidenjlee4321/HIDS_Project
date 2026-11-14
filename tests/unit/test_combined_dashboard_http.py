import json
from pathlib import Path
import tempfile
import unittest
from api.dashboard_app import make_app
from api.process_view import ProcessView
from api.history_view import FrozenView
from api.pilot_sessions import Sessions,Denied
from test_process_view import rows
from test_history_view import fixture
import test_history_http as history_tests

class CombinedHTTPTests(unittest.TestCase):
    call=history_tests.HistoryHTTPTest.call
    get=history_tests.HistoryHTTPTest.get
    token=history_tests.HistoryHTTPTest.token
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.assets=Path(tmp.name)
        (self.assets/'assets').mkdir();(self.assets/'dashboard.html').write_text('<html>locked</html>')
        self.scheme='https';self.clock=[0.0];self.state=Sessions(clock=lambda:self.clock[0],scope='dashboard:read')
        r,s=rows();self.process=ProcessView(r,s);self.history=FrozenView(fixture())
        self.app,_=make_app('127.0.0.1:18765',self.assets,self.process,self.history,self.state)
    def test_every_route_independently_requires_dashboard_authority(self):
        for path in ('/v0/dashboard','/v0/process/events','/v0/process/events/x','/v0/history','/v0/history/events','/v0/history/findings','/v0/history/events/x','/v0/history/findings/x'):
            self.assertEqual(self.call(path)[0],403)
            for scope in ('history:read','pilot:read','setup:draft'):
                other=Sessions(scope=scope);t=other.redeem(other.mint());self.assertEqual(self.get(path,t)[0],403)
    def test_explicit_scope_and_legacy_app_refuses_it(self):
        grant=self.state.mint();status,_,raw=self.call('/v0/auth/redeem','POST',json.dumps(dict(grant=grant)).encode());self.assertEqual(status,200)
        token=json.loads(raw)['token'];self.assertEqual(json.loads(raw)['scope'],'dashboard:read')
        with self.assertRaises(Denied):self.state.authorize(token,'history:read')
        self.assertEqual(self.get('/v0/dashboard',token)[0],200)
    def test_combined_summary_process_details_and_findings(self):
        t=self.token();s=json.loads(self.get('/v0/dashboard',t)[2]);self.assertTrue(s['history_only']);self.assertTrue(s['process']['available'])
        p=json.loads(self.get('/v0/process/events',t)[2]);d=json.loads(self.get('/v0/process/events/'+p['items'][0]['event_id'],t)[2])
        self.assertIsNone(d['envelope']['timestamps']['activity_wall_time']);self.assertTrue(d['historical_interval']['incomplete'])
        f=json.loads(self.get('/v0/history/findings',t)[2])['items'][0];self.assertEqual(self.get('/v0/history/events/'+f['event_id'],t)[0],200)
    def test_failed_family_does_not_block_other_family_or_auth(self):
        for process,history,good,bad in [(None,self.history,'/v0/history/events','/v0/process/events'),(self.process,None,'/v0/process/events','/v0/history/events'),(None,None,None,None)]:
            self.app,_=make_app('127.0.0.1:18765',self.assets,process,history,self.state);t=self.token()
            self.assertEqual(self.get('/v0/dashboard',t)[0],200)
            if good:self.assertEqual(self.get(good,t)[0],200);self.assertEqual(self.get(bad,t)[0],404)
            self.assertEqual(self.call('/v0/auth/logout','POST',b'{}',[(b'authorization',('Bearer '+t).encode())])[0],200)
            self.assertEqual(self.get('/v0/dashboard',t)[0],403)
    def test_process_cursor_cannot_cross_session_or_family(self):
        t=self.token();p=json.loads(self.get('/v0/process/events',t)[2]);q=b'cursor='+p['next_cursor'].encode()
        self.assertEqual(len(json.loads(self.get('/v0/process/events',t,q)[2])['items']),5)
        self.assertEqual(self.get('/v0/process/events',self.token(),q)[0],404)
        self.assertEqual(self.get('/v0/history/events',t,q)[0],404)
    def test_queries_paths_and_mutation_are_closed(self):
        t=self.token()
        for q in (b'limit=1',b'cursor=x&cursor=y',b'cursor=%41',b'cursor=',b'token='+t.encode()):self.assertIn(self.get('/v0/process/events',t,q)[0],(403,404))
        for path in ('/v0/pilot','/v0/setup','/v0/export','/v0/process/events/../../etc/passwd','/docs','/openapi.json'):
            self.assertEqual(self.get(path,t)[0],404)
        self.assertEqual(self.call('/v0/process/events','POST',b'{}')[0],404)
    def test_expiry_host_scheme_and_headers(self):
        t=self.token();_,headers,_=self.get('/v0/dashboard',t)
        for name in (b'cache-control',b'content-security-policy',b'referrer-policy'):self.assertIn(name,headers)
        self.clock[0]=300;self.assertEqual(self.get('/v0/process/events',t)[0],403)
        self.scheme='http';self.assertEqual(self.call('/')[0],403)
    def test_static_shell_is_data_free_and_scope_config_closed(self):
        self.assertEqual(self.call('/')[2],b'<html>locked</html>')
        with self.assertRaises(ValueError):make_app('127.0.0.1:18765',self.assets,self.process,self.history,Sessions(scope='history:read'))

if __name__=='__main__':unittest.main()
