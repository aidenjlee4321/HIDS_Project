import json
from pathlib import Path
import tempfile
import unittest
import test_dashboard_http as pilot_tests
from test_history_view import fixture
from api.history_app import make_app
from api.history_view import FrozenView
from api.pilot_sessions import Sessions,Denied

class HistoryHTTPTest(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);p=Path(tmp.name);(p/'assets').mkdir();(p/'history.html').write_text('<html>locked</html>');(p/'assets/index-123.js').write_text('void 0')
  self.assets=p;self.scheme='https';self.clock=[0.0];self.state=Sessions(clock=lambda:self.clock[0],scope='history:read');self.view=FrozenView(fixture());self.app,_=make_app('127.0.0.1:18765',p,self.view,self.state)
 def call(self,path='/v0/history',method='GET',body=b'',extra=(),base=True,query=b''):
  if method=='POST' and base:
   base=False;extra=[(b'host',b'127.0.0.1:18765'),(b'sec-fetch-site',b'same-origin'),(b'origin',b'https://127.0.0.1:18765'),(b'content-type',b'application/json'),*extra]
  return pilot_tests.HTTPTest.call(self,path,method,body,extra,base,query)
 def token(self):return self.state.redeem(self.state.mint())
 def get(self,path='/v0/history',token=None,query=b''):return self.call(path,extra=[(b'authorization',('Bearer '+(token or self.token())).encode())],query=query)
 def test_every_endpoint_denies_before_projection(self):
  for path in ('/v0/history','/v0/history/events','/v0/history/findings','/v0/history/events/'+'a'*64,'/v0/history/findings/'+'a'*64):
   for query in (b'',b'cursor=forged'):
    status,headers,body=self.call(path,query=query);self.assertEqual(status,403);self.assertNotIn(b'view_id',body)
 def test_history_scope_only_and_explicit_issuance(self):
  g=self.state.mint();status,_,body=self.call('/v0/auth/redeem','POST',json.dumps({'grant':g}).encode());self.assertEqual(status,200);self.assertEqual(json.loads(body)['scope'],'history:read');t=json.loads(body)['token']
  with self.assertRaises(Denied):self.state.authorize(t)
  self.assertEqual(self.get(token=t)[0],200)
  pilot=Sessions();self.assertEqual(self.get(token=pilot.redeem(pilot.mint()))[0],403)
 def test_unavailable_static_and_no_data(self):
  self.app,_=make_app('127.0.0.1:18765',self.assets,None,self.state);self.assertEqual(self.call('/')[0],200);self.assertEqual(self.get()[0],404)
 def test_synthetic_and_write_export_debug_routes_absent(self):
  token=self.token()
  for path in ('/v0/pilot','/v0/sources','/v0/export','/docs','/openapi.json','/v0/history/','/v0/history/events/../../etc/passwd'):
   self.assertEqual(self.get(path,token)[0],404)
  self.assertEqual(self.call('/v0/history','POST',b'{}')[0],404)
 def test_closed_query_allowlist(self):
  t=self.token()
  for query in (b'limit=1',b'cursor=x&cursor=y',b'cursor=',b'cursor=%41',b'cursor='+(b'x'*513),b'token='+t.encode()):self.assertIn(self.get('/v0/history/events',t,query)[0],(403,404))
  self.assertEqual(self.get(token=t,query=b'cursor=x')[0],403)
 def test_fixed_pages_and_cursor_binding(self):
  t=self.token();status,_,body=self.get('/v0/history/events',t);self.assertEqual(status,200);v=json.loads(body);self.assertEqual(len(v['items']),20);q=b'cursor='+v['next_cursor'].encode();self.assertEqual(len(json.loads(self.get('/v0/history/events',t,q)[2])['items']),5)
  self.assertEqual(self.get('/v0/history/findings',t,q)[0],404);self.assertEqual(self.get('/v0/history/events',self.token(),q)[0],404)
 def test_details_linkage_and_lossless_values(self):
  t=self.token();f=json.loads(self.get('/v0/history/findings',t)[2])['items'][0];d=json.loads(self.get('/v0/history/findings/'+f['finding_id'],t)[2]);e=json.loads(self.get('/v0/history/events/'+d['event_id'],t)[2]);self.assertEqual(e['execution']['result'],'0');self.assertEqual(e['metadata']['first_observed_unix_ns'],str(2**63-1));self.assertEqual(e['evaluation_state'],'matched');self.assertEqual(d['rule']['id'],f['rule_id'])
 def test_logout_revocation_and_grant_replay(self):
  g=self.state.mint();t=self.state.redeem(g);self.assertEqual(self.get(token=t)[0],200)
  self.assertEqual(self.call('/v0/auth/logout','POST',b'{}',[(b'authorization',('Bearer '+t).encode())])[0],200);self.assertEqual(self.get(token=t)[0],403)
  with self.assertRaises(Denied):self.state.redeem(g)
 def test_idle_absolute_revoke_and_restart(self):
  t=self.token();self.clock[0]=300;self.assertEqual(self.get(token=t)[0],403);t=self.token()
  for n in range(1,6):self.clock[0]=300+n*299;self.assertEqual(self.get(token=t)[0],200)
  self.clock[0]=2100;self.assertEqual(self.get(token=t)[0],403);t=self.token();self.state.revoke_all();self.assertEqual(self.get(token=t)[0],403)
  t=self.token();self.state=Sessions(scope='history:read');self.app,_=make_app('127.0.0.1:18765',self.assets,self.view,self.state);self.assertEqual(self.get(token=t)[0],403)
 def test_host_origin_transport_and_defenses(self):
  t=self.token();status,headers,_=self.get(token=t);self.assertEqual(headers[b'cache-control'],b'no-store');self.assertNotIn(b'set-cookie',headers)
  for extra in ([(b'host',b'evil')],[(b'origin',b'http://127.0.0.1:18765')],[(b'x-forwarded-proto',b'https')]):self.assertEqual(self.call(extra=extra)[0],403)
  self.scheme='http';self.assertEqual(self.call('/')[0],403)
 def test_request_cannot_choose_scope(self):
  g=self.state.mint();self.assertEqual(self.call('/v0/auth/redeem','POST',json.dumps({'grant':g,'scope':'history:read'}).encode())[0],403)
 def test_invalid_scope_configuration_refuses(self):
  with self.assertRaises(Denied):Sessions(scope='admin')
  with self.assertRaises(ValueError):make_app('127.0.0.1:18765',self.assets,self.view,Sessions())
if __name__=='__main__':unittest.main()
