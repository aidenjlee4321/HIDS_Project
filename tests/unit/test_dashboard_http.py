import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from api.pilot_app import make_app, SYNTHETIC, DEFENSES
from api.pilot_sessions import Sessions

class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name);(p/'assets').mkdir();(p/'index.html').write_text('<html>locked</html>');(p/'assets/index-123.js').write_text('void 0')
        self.assets=p;self.scheme='http'
        self.clock=[0.0];self.state=Sessions(clock=lambda:self.clock[0]);self.app,_=make_app('127.0.0.1:18765',p,self.state)
    def call(self,path='/v0/pilot',method='GET',body=b'',extra=(),base=True,query=b''):
        headers=[(b'host',b'127.0.0.1:18765'),(b'sec-fetch-site',b'same-origin')]
        if method=='POST':headers += [(b'origin',b'http://127.0.0.1:18765'),(b'content-type',b'application/json')]
        if not base:headers=[]
        headers+=list(extra)
        out=[];delivered=False
        async def receive():
            nonlocal delivered
            if delivered:return {'type':'http.disconnect'}
            delivered=True;return {'type':'http.request','body':body,'more_body':False}
        async def send(msg):out.append(msg)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':self.scheme,'server':('127.0.0.1',18765),'client':('127.0.0.1',12345),'path':path,'raw_path':path.encode(),'root_path':'','query_string':query,'method':method,'headers':headers}
        asyncio.run(self.app(scope,receive,send));return out[0]['status'],dict(out[0]['headers']),b''.join(x.get('body',b'') for x in out[1:])
    def token(self):return self.state.redeem(self.state.mint())
    def test_root_selected_https_origin(self):
        self.app,_=make_app('127.0.0.1:18765',self.assets,self.state,scheme='https');self.scheme='https'
        grant=self.state.mint();body=json.dumps({'grant':grant}).encode()
        self.assertEqual(self.call('/v0/auth/redeem','POST',body)[0],403)
        headers=[(b'host',b'127.0.0.1:18765'),(b'sec-fetch-site',b'same-origin'),(b'origin',b'https://127.0.0.1:18765'),(b'content-type',b'application/json')]
        self.assertEqual(self.call('/v0/auth/redeem','POST',body,headers,base=False)[0],200)
    def test_physical_scheme_must_match_root_selection(self):
        self.app,_=make_app('127.0.0.1:18765',self.assets,self.state,scheme='https')
        self.assertEqual(self.call('/')[0],403)
    def test_unsupported_origin_scheme_refuses(self):
        with self.assertRaises(ValueError):make_app('127.0.0.1:18765',self.assets,scheme='ftp')
    def test_protected_no_bearer(self):self.assertEqual(self.call()[0],403)
    def test_success_synthetic_only(self):
        status,headers,body=self.call(extra=[(b'authorization',('Bearer '+self.token()).encode())]);self.assertEqual(status,200);self.assertEqual(json.loads(body),SYNTHETIC)
        for k,v in DEFENSES.items():self.assertEqual(headers[k.encode()],v.encode())
    def test_redeem_and_logout(self):
        g=self.state.mint();body=json.dumps({'grant':g}).encode();status,_,out=self.call('/v0/auth/redeem','POST',body);self.assertEqual(status,200)
        t=json.loads(out)['token'];self.assertNotEqual(g,t);self.assertEqual(self.call('/v0/auth/redeem','POST',body)[0],403)
        self.assertEqual(self.call('/v0/auth/logout','POST',b'{}',[(b'authorization',('Bearer '+t).encode())])[0],200)
        self.assertEqual(self.call(extra=[(b'authorization',('Bearer '+t).encode())])[0],403)
    def test_host_origin_and_metadata(self):
        for headers in ([(b'host',b'localhost:18765')],[(b'host',b'evil.example')],[(b'host',b'127.0.0.1:18765'),(b'origin',b'null')],[(b'host',b'127.0.0.1:18765'),(b'sec-fetch-site',b'cross-site')],[(b'host',b'127.0.0.1:18765')]):
            self.assertEqual(self.call(extra=headers,base=False)[0],403)
    def test_forged_request_does_not_consume_grant(self):
        g=self.state.mint();self.assertEqual(self.call('/v0/auth/redeem','POST',json.dumps({'grant':g}).encode(),[(b'origin',b'http://evil.example')])[0],403);self.state.redeem(g)
    def test_duplicate_headers(self):
        t=self.token()
        for extra in ([(b'host',b'127.0.0.1:18765')],[(b'authorization',('Bearer '+t).encode())]*2,[(b'origin',b'http://127.0.0.1:18765')]*2):
            self.assertEqual(self.call(extra=extra)[0],403)
    def test_no_cookie_authority_or_query_token(self):
        t=self.token();self.assertEqual(self.call(extra=[(b'cookie',('token='+t).encode())])[0],403)
        self.assertEqual(self.call(query=('token='+t).encode())[0],403)
    def test_closed_post_schema(self):
        for body in (b'{"grant":"x","grant":"x"}',b'{}',b'[]',b'{"grant":"x","next":"/"}',b'bad'):
            self.assertEqual(self.call('/v0/auth/redeem','POST',body)[0],403)
    def test_bounded_body(self):self.assertEqual(self.call('/v0/auth/redeem','POST',b'x'*1025)[0],403)
    def test_no_proxy_authority(self):
        for key in (b'forwarded',b'x-forwarded-host',b'x-forwarded-proto',b'x-forwarded-for'):
            self.assertEqual(self.call(extra=[(key,b'anything')])[0],403)
    def test_no_routes_for_data_collection_or_docs(self):
        for path in ('/docs','/openapi.json','/v0/events','/v0/sources','/v0/pilot/','/assets/../../etc/passwd'):
            self.assertEqual(self.call(path)[0],404)
    def test_unauthenticated_shell_contains_no_host_data(self):
        self.assertEqual(self.call('/')[2],b'<html>locked</html>');self.assertEqual(self.call('/assets/index-123.js')[0],200)
    def test_elapsed_idle_refuses_over_http(self):
        t=self.token();self.clock[0]=300;self.assertEqual(self.call(extra=[(b'authorization',('Bearer '+t).encode())])[0],403)

if __name__=='__main__':unittest.main()
