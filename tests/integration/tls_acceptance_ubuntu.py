"""Synthetic leaf verification only. No HIDS data read or history endpoint."""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import hashlib

SERVER='''import asyncio,json,ssl,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from api.tls_leaf import validated_context
root=Path(sys.argv[2]);gid=int(sys.argv[3]);fingerprint=sys.argv[4]
async def handle(reader,writer):
 try:
  await asyncio.wait_for(reader.readuntil(b"\\r\\n\\r\\n"),3)
  writer.write(b"HTTP/1.1 200 OK\\r\\nContent-Length: 18\\r\\nConnection: close\\r\\n\\r\\nTLS synthetic only");await writer.drain()
 except Exception:pass
 finally:
  writer.close()
  try:await writer.wait_closed()
  except Exception:pass
async def main():
 servers={}
 for name in ('valid','foreign','expired'):
  if name=='valid':ctx=validated_context(root/(name+'.pem'),root/(name+'.key'),fingerprint,gid)
  else:
   ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(root/(name+'.pem'),root/(name+'.key'))
  servers[name]=await asyncio.start_server(handle,'127.0.0.1',0,ssl=ctx,ssl_handshake_timeout=3,limit=8192)
 print(json.dumps({k:v.sockets[0].getsockname()[1] for k,v in servers.items()}),flush=True)
 await asyncio.to_thread(sys.stdin.readline)
 for server in servers.values():server.close();await server.wait_closed()
asyncio.run(main())
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--tools',type=Path,required=True);p.add_argument('--expected-manifest',required=True);args=p.parse_args()
 root_source=Path(__file__).resolve().parents[2]
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path.insert(0,str(root_source/'scripts'));import dev;dev.verify(root_source,args.expected_manifest)
 root=Path(tempfile.mkdtemp(prefix='hids-tls-synthetic.',dir='/opt'));a=pwd.getpwnam('hids-ingest');user=pwd.getpwnam('ivy');os.chown(root,0,a.pw_gid);root.chmod(0o750)
 report={'passed':False,'synthetic_only':True,'checks':{},'source_manifest':args.expected_manifest};server=None
 def check(name,ok):assert ok,name;report['checks'][name]=True
 def run(*argv):return subprocess.check_output(list(map(str,argv)),stderr=subprocess.DEVNULL,timeout=10)
 try:
  for name in ('valid','foreign'):
   run('/usr/bin/openssl','req','-new','-newkey','rsa:2048','-nodes','-x509','-days','7','-subj','/CN=HIDS synthetic TLS','-addext','basicConstraints=critical,CA:FALSE','-addext','extendedKeyUsage=serverAuth','-addext','subjectAltName=IP:127.0.0.1','-keyout',root/(name+'.key'),'-out',root/(name+'.pem'))
  # A deliberately expired self-signed leaf, using the valid key/subject.
  (root/'index').touch();(root/'serial').write_text('0A\n');(root/'newcerts').mkdir()
  conf='''[ca]
default_ca=local
[local]
database={r}/index
serial={r}/serial
new_certs_dir={r}/newcerts
certificate={r}/valid.pem
private_key={r}/valid.key
default_md=sha256
policy=names
x509_extensions=leaf
[names]
commonName=supplied
[leaf]
basicConstraints=critical,CA:FALSE
extendedKeyUsage=serverAuth
subjectAltName=IP:127.0.0.1
'''.format(r=root)
  (root/'ca.conf').write_text(conf)
  run('/usr/bin/openssl','req','-new','-key',root/'valid.key','-subj','/CN=HIDS synthetic TLS','-out',root/'expired.csr')
  run('/usr/bin/openssl','ca','-selfsign','-batch','-notext','-config',root/'ca.conf','-in',root/'expired.csr','-startdate','20260101000000Z','-enddate','20260102000000Z','-out',root/'expired.pem')
  shutil.copyfile(root/'valid.key',root/'expired.key')
  for name in ('valid','foreign','expired'):
   key=root/(name+'.key');os.chown(key,0,a.pw_gid);key.chmod(0o440);(root/(name+'.pem')).chmod(0o644)
  (root/'code/api').mkdir(parents=True);shutil.copyfile(root_source/'api/tls_leaf.py',root/'code/api/tls_leaf.py')
  for folder in (root/'code',root/'code/api'):folder.chmod(0o755)
  (root/'code/api/tls_leaf.py').chmod(0o644)
  sys.path.insert(0,str(root/'code'));from api.tls_leaf import validated_context,TLSError
  der=run('/usr/bin/openssl','x509','-in',root/'valid.pem','-outform','DER');fingerprint=hashlib.sha256(der).hexdigest()
  validated_context(root/'valid.pem',root/'valid.key',fingerprint,a.pw_gid);check('valid_context',True)
  for name,cert,key,fp in (('wrong_fingerprint',root/'valid.pem',root/'valid.key','0'*64),('key_mismatch',root/'valid.pem',root/'foreign.key',fingerprint),('expired_leaf',root/'expired.pem',root/'expired.key',hashlib.sha256(run('/usr/bin/openssl','x509','-in',root/'expired.pem','-outform','DER')).hexdigest())):
   try:validated_context(cert,key,fp,a.pw_gid)
   except TLSError:check(name+'_refused',True)
   else:raise AssertionError(name)
  key=root/'valid.key';key.chmod(0o444)
  try:validated_context(root/'valid.pem',key,fingerprint,a.pw_gid)
  except TLSError:check('unsafe_key_mode_refused',True)
  else:raise AssertionError('unsafe key mode')
  finally:key.chmod(0o440)
  denied=subprocess.run(['/usr/bin/python3','-B','-c','from pathlib import Path;Path('+repr(str(key))+').read_bytes()'],user=user.pw_uid,group=user.pw_gid,extra_groups=[],capture_output=True)
  check('ordinary_key_read_denied',denied.returncode!=0 and b'PermissionError' in denied.stderr)
  server=subprocess.Popen(['/usr/bin/python3','-B','-c',SERVER,str(root/'code'),str(root),str(a.pw_gid),fingerprint],user=a.pw_uid,group=a.pw_gid,extra_groups=[],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'server.stderr').open('x'),text=True)
  ports=json.loads(server.stdout.readline());report['ports']=ports
  context=ssl.create_default_context(cafile=str(root/'valid.pem'))
  def get(port,hostname='127.0.0.1'):
   with socket.create_connection(('127.0.0.1',port),timeout=4) as sock:
    with context.wrap_socket(sock,server_hostname=hostname) as secure:
     secure.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n');return secure.recv(4096)
  check('verified_python_tls',b'TLS synthetic only' in get(ports['valid']))
  for name,port,hostname in (('foreign_leaf',ports['foreign'],'127.0.0.1'),('wrong_name',ports['valid'],'localhost')):
   try:get(port,hostname)
   except ssl.SSLCertVerificationError:check('python_'+name+'_refused',True)
   else:raise AssertionError(name)
  with socket.create_connection(('127.0.0.1',ports['valid']),timeout=4) as sock:
   sock.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n')
   try:plain=sock.recv(4096)
   except ConnectionResetError:plain=b''
   check('plaintext_does_not_serve_data',b'TLS synthetic only' not in plain)
  profile=Path(tempfile.mkdtemp(prefix='tls-browser.',dir=args.build));os.chown(profile,user.pw_uid,user.pw_gid);profile.chmod(0o700)
  for name in ('valid','expired'):
   dst=profile/(name+'.pem');shutil.copyfile(root/(name+'.pem'),dst);os.chown(dst,user.pw_uid,user.pw_gid);dst.chmod(0o600)
  env=dict(os.environ,HOME=user.pw_dir,USER=user.pw_name,LOGNAME=user.pw_name,XDG_RUNTIME_DIR='/run/user/'+str(user.pw_uid),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(user.pw_uid)+'/bus')
  child=subprocess.run(['systemd-run','--user','--scope','--quiet','--collect',str(args.build/'venv/bin/python'),'-B',str(root_source/'tests/integration/tls_browser.py'),str(profile),str(args.tools),json.dumps(ports),str(args.build)],user=user.pw_uid,group=user.pw_gid,extra_groups=[],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=(root/'browser.stderr').open('x'),text=True,timeout=90)
  value=json.loads(child.stdout.strip().splitlines()[-1]);report['browser']=value;check('browser_tls_acceptance',child.returncode==0 and value['passed'])
  report['passed']=True
 except Exception as exc:
  report['error_type']=type(exc).__name__;report['error']=str(exc)[:160] if isinstance(exc,AssertionError) else 'private failure retained'
  import traceback;(root/'failure.txt').write_text(traceback.format_exc())
 finally:
  if server:
   try:server.stdin.write('stop\n');server.stdin.flush();server.wait(timeout=8)
   except Exception:server.kill();server.wait()
   report['server_stopped']=server.returncode==0
  p=root/'report.json';p.write_text(json.dumps(report,indent=2));p.chmod(0o600)
  print(json.dumps({'passed':report['passed'],'report':str(p),'error':report.get('error'),'checks':len(report['checks'])}),flush=True)
 return 0 if report['passed'] and report.get('server_stopped') else 1
if __name__=='__main__':raise SystemExit(main())
