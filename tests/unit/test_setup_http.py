import json
from pathlib import Path
import tempfile
import unittest
import test_dashboard_http as pilot_tests
from test_setup import fixture
from api.setup_app import make_app
from api.setup_sessions import SetupSessions
from api.pilot_sessions import Denied

class SetupHTTPTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);p=Path(self.t.name);(p/'assets').mkdir();(p/'setup.html').write_text('<html>locked</html>');(p/'assets/index-123.js').write_text('void 0')
  self.assets=p;self.scheme='https';self.clock=[0];self.state=SetupSessions(fixture(),clock=lambda:self.clock[0]);self.app,_=make_app('127.0.0.1:18765',p,self.state.view,self.state)
 def call(self,path='/v0/setup',method='GET',body=b'',extra=(),base=True,query=b''):
  if method=='POST' and base:base=False;extra=[(b'host',b'127.0.0.1:18765'),(b'sec-fetch-site',b'same-origin'),(b'origin',b'https://127.0.0.1:18765'),(b'content-type',b'application/json'),*extra]
  return pilot_tests.HTTPTest.call(self,path,method,body,extra,base,query)
 def token(self):return self.state.redeem(self.state.mint())
 def auth(self,t):return [(b'authorization',('Bearer '+t).encode())]
 def stage(self,t,selected=None):
  body=dict(assessment_id=self.state.view['assessment_id'],confirmed_revision=0,selected=[] if selected is None else selected)
  return self.call('/v0/setup/draft','POST',json.dumps(body).encode(),self.auth(t))
 def test_all_setup_data_denied_without_bearer(self):
  self.assertEqual(self.call()[0],403);self.assertEqual(self.call('/v0/setup/draft','POST',b'{}')[0],403)
 def test_snapshot_closed_no_store_and_no_secret_fingerprint(self):
  status,headers,body=self.call(extra=self.auth(self.token()));v=json.loads(body);self.assertEqual(status,200);self.assertTrue(v['snapshot_only']);self.assertNotIn('fingerprint',v);self.assertEqual(headers[b'cache-control'],b'no-store');self.assertNotIn(b'set-cookie',headers)
 def test_scope_is_explicit_and_not_selectable(self):
  grant=self.state.mint();status,_,body=self.call('/v0/auth/redeem','POST',json.dumps({'grant':grant}).encode());self.assertEqual(status,200);self.assertEqual(json.loads(body)['scope'],'setup:draft')
  with self.assertRaises(Denied):self.state.authorize(json.loads(body)['token'],'history:read')
 def test_empty_draft_requires_root_confirmation(self):
  status,_,body=self.stage(self.token());v=json.loads(body);self.assertEqual(status,200);self.assertTrue(v['requires_root_confirmation']);self.assertEqual(self.state.review(v['reference'])['selected'],[])
 def test_unapproved_source_and_stale_revision_refused(self):
  t=self.token()
  for values in (['proc_lifecycle'],['journal_auth'],['audit_exec']*2,['/bin/sh']):self.assertEqual(self.stage(t,values)[0],403)
  body=dict(assessment_id=self.state.view['assessment_id'],confirmed_revision=True,selected=[]);self.assertEqual(self.call('/v0/setup/draft','POST',json.dumps(body).encode(),self.auth(t))[0],403)
 def test_no_history_control_export_or_debug_route(self):
  t=self.token()
  for p in ('/v0/history','/v0/pilot','/v0/setup/start','/v0/setup/stop','/v0/setup/confirm','/v0/setup/export','/docs','/openapi.json'):
   self.assertEqual(self.call(p,extra=self.auth(t))[0],404);self.assertEqual(self.call(p,'POST',b'{}',self.auth(t))[0],404)
 def test_logout_discards_draft_and_reference_is_not_session(self):
  t=self.token();reference=json.loads(self.stage(t)[2])['reference'];self.assertEqual(self.call(extra=self.auth(reference))[0],403);self.assertEqual(self.call('/v0/auth/logout','POST',b'{}',self.auth(t))[0],200)
  with self.assertRaises(Denied):self.state.review(reference)
 def test_queries_duplicate_json_and_extra_control_fields_refused(self):
  t=self.token();self.assertEqual(self.call(extra=self.auth(t),query=b'cursor=x')[0],403)
  for body in (b'{}',b'{"selected":[],"selected":[]}',b'{"operation":"start"}'):
   self.assertEqual(self.call('/v0/setup/draft','POST',body,self.auth(t))[0],403)
 def test_wrong_host_origin_transport_proxy_and_fetch_site_refused(self):
  for extra in ([(b'host',b'evil')],[(b'origin',b'http://127.0.0.1:18765')],[(b'x-forwarded-proto',b'https')],[(b'sec-fetch-site',b'cross-site')]):self.assertEqual(self.call(extra=extra)[0],403)
  self.scheme='http';self.assertEqual(self.call('/')[0],403)
 def test_unavailable_static_ui_and_grant_refusal(self):
  s=SetupSessions(None);self.app,self.state=make_app('127.0.0.1:18765',self.assets,None,s);self.assertEqual(self.call('/')[0],200)
  with self.assertRaises(Denied):s.mint()
if __name__=='__main__':unittest.main()
