"""Source-free HTTPS session acceptance using private synthetic assets and keys.

Runs as an ordinary Linux user. Never reads HIDS config, stores or credentials.
The injected monotonic clock affects this test process only, not the host clock.
"""
import argparse
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]


def main():
 a=argparse.ArgumentParser();a.add_argument('--expected-manifest',required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
 assert sys.platform=='linux' and os.getuid()!=0
 sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
 import dev,uvicorn
 from api.dashboard_app import make_app
 from api.pilot_sessions import Sessions
 dev.verify(ROOT,args.expected_manifest)
 output=dev.private_dir(args.output.absolute());work=Path(tempfile.mkdtemp(prefix='session-https.',dir=output));work.chmod(0o700)
 assets=work/'assets';assets.mkdir();(assets/'assets').mkdir();(assets/'dashboard.html').write_text('<html>Synthetic locked shell</html>');(assets/'assets/test.js').write_text('void 0')
 key=work/'test.key';cert=work/'test.pem'
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-addext','basicConstraints=critical,CA:FALSE'],capture_output=True,check=True,timeout=15);key.chmod(0o600)
 listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
 origin='https://127.0.0.1:'+str(port);clock=[100.0];state=Sessions(clock=lambda:clock[0],scope='dashboard:read')
 app,_=make_app('127.0.0.1:'+str(port),assets,None,None,state)
 config=uvicorn.Config(app,access_log=False,log_config=None,log_level='critical',proxy_headers=False,server_header=False,date_header=False,workers=1,timeout_keep_alive=1,timeout_graceful_shutdown=2,ssl_certfile=str(cert),ssl_keyfile=str(key),limit_concurrency=16,h11_max_incomplete_event_size=8192)
 server=uvicorn.Server(config);thread=threading.Thread(target=lambda:server.run(sockets=[listener]),name='synthetic-https')
 checks={};report=dict(result='running',source_manifest=args.expected_manifest,checks=checks)
 ctx=ssl.create_default_context(cafile=str(cert));peer_digest=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
 def call(path='/v0/dashboard',method='GET',value=None,token=None,extra=()):
  body=b'' if value is None else json.dumps(value).encode();connection=http.client.HTTPSConnection('127.0.0.1',port,context=ctx,timeout=5)
  try:
   connection.connect();assert hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()==peer_digest
   connection.putrequest(method,path,skip_host=True,skip_accept_encoding=True)
   headers=[('Host','127.0.0.1:'+str(port)),('Sec-Fetch-Site','same-origin'),('Connection','close')]
   if method=='POST':headers += [('Origin',origin),('Content-Type','application/json'),('Content-Length',str(len(body)))]
   if token is not None:headers += [('Authorization','Bearer '+token)]
   for k,v in headers+list(extra):connection.putheader(k,v)
   connection.endheaders(body);response=connection.getresponse();raw=response.read(65537);assert len(raw)<=65536
   assert response.getheader('Cache-Control')=='no-store' and response.getheader('Referrer-Policy')=='no-referrer'
   return response.status,json.loads(raw)
  finally:connection.close()
 def redeem(grant):
  status,value=call('/v0/auth/redeem','POST',{'grant':grant});assert status==200 and value['scope']=='dashboard:read';return value['token']
 def session():return redeem(state.mint())
 try:
  thread.start();deadline=time.monotonic()+5
  while not server.started:
   assert thread.is_alive() and time.monotonic()<deadline;time.sleep(.01)
  checks['unauthenticated_https_denied']=call()[0]==403
  grant=state.mint();status,_=call('/v0/auth/redeem','POST',{'grant':grant},extra=[('Origin','https://invalid.example')]);token=redeem(grant)
  checks['forged_origin_does_not_consume_grant']=status==403 and call(token=token)[0]==200
  checks['duplicate_authorization_denied']=call(token=token,extra=[('Authorization','Bearer '+token)])[0]==403
  checks['grant_replay_denied']=call('/v0/auth/redeem','POST',{'grant':grant})[0]==403
  assert call('/v0/auth/logout','POST',{},token=token)[0]==200
  checks['logout_revokes_over_https']=call(token=token)[0]==403
  state.revoke_all();grant=state.mint()
  def attempt(_):return call('/v0/auth/redeem','POST',{'grant':grant})[0]
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:statuses=list(pool.map(attempt,range(20)))
  checks['concurrent_redeem_exactly_once']=statuses.count(200)==1 and statuses.count(403)==19
  state.revoke_all();token=session();grant=state.mint();state.revoke_all()
  checks['revoke_all_cancels_session_and_grant']=call(token=token)[0]==403 and call('/v0/auth/redeem','POST',{'grant':grant})[0]==403
  grant=state.mint();clock[0]+=60
  checks['grant_exact_expiry_denied']=call('/v0/auth/redeem','POST',{'grant':grant})[0]==403
  token=session();clock[0]+=300
  checks['idle_exact_expiry_denied']=call(token=token)[0]==403
  token=session();start=clock[0]
  for step in range(1,9):clock[0]=start+200*step;assert call(token=token)[0]==200
  clock[0]=start+1800
  checks['absolute_expiry_despite_idle_renewal']=call(token=token)[0]==403
  foreign=Sessions(scope='setup:draft');other=foreign.redeem(foreign.mint())
  checks['foreign_scope_token_denied']=call(token=other)[0]==403
  state.revoke_all();token=session();clock[0]-=1
  denied=call(token=token)[0];clock[0]+=2
  checks['clock_rollback_revokes_session']=denied==403 and call(token=token)[0]==403
  dev.verify(ROOT,args.expected_manifest)
 except BaseException as exc:
  import traceback
  report['error_type']=type(exc).__name__; (work/'failure.txt').write_text(traceback.format_exc())
 finally:
  state.revoke_all();server.should_exit=True
  if thread.ident is not None:
   thread.join(5)
   if thread.is_alive():server.force_exit=True;thread.join(3)
  listener.close();checks['test_listener_and_thread_closed']=not thread.is_alive() and listener.fileno()==-1
  report['result']='passed' if checks and all(checks.values()) and 'error_type' not in report else 'failed'
  (work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(work/'report.json'),checks=checks,error_type=report.get('error_type'))))
 return int(report['result']!='passed')

if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
