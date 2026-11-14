"""Pinned Linux 2 TLS faults using private synthetic keys; no listeners or trust."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import ssl
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);a=p.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests/integration')]
 import dev;dev.verify(ROOT,a.expected_manifest)
 import dashboard_pilot_ubuntu as lab
 from api import dashboard_tls as d
 from api.tls_leaf import TLSError,validated_context
 baseline=lab.preserved();u=pwd.getpwnam('hids-ingest')
 work=Path(tempfile.mkdtemp(prefix='hids-tls-faults.',dir='/opt'));work.chmod(0o755)
 root=work/'tls';current=d.ensure_leaf(u.pw_gid,root=root);old=root/current['tls_generation']
 before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
 end=d._openssl('x509','-in',old/'leaf.pem','-noout','-enddate').decode().strip().split('=',1)[1];near=ssl.cert_time_to_seconds(end)-1200
 actual_run=subprocess.run;actual_validate=d.validated_context;actual_chown=os.chown;actual_chmod=Path.chmod;actual_fsync=os.fsync
 def readable(path):
  r=actual_run(['/usr/bin/python3','-I','-B','-c','import os,sys;print(os.access(sys.argv[1],os.R_OK))',str(path)],capture_output=True,text=True,check=True,user=u.pw_uid,group=u.pw_gid,extra_groups=[])
  return r.stdout.strip()=='True'
 assert readable(old/'leaf.key')
 cases=[];report=dict(result='running',source_manifest=a.expected_manifest,cases=cases)
 try:
  for kind in ('openssl_before','openssl_after','validation','handoff','sync','sync_after_handoff','directory_mode','interrupt','kill_after_openssl','kill_during_validation'):
   existing=set(root.iterdir());kills=kind.startswith('kill_')
   def run(args,*pos,**kw):
    generation=args[:2]==['/usr/bin/openssl','req']
    if generation and kind=='openssl_before':raise OSError('injected')
    result=actual_run(args,*pos,**kw)
    if generation and kind=='openssl_after':raise subprocess.TimeoutExpired('injected',15)
    if generation and kind=='kill_after_openssl':os.kill(os.getpid(),signal.SIGKILL)
    return result
   def validate(*pos,**kw):
    if kw.get('_private'):
     if kind=='validation':raise TLSError('injected')
     if kind=='interrupt':raise KeyboardInterrupt()
     if kind=='kill_during_validation':
      actual_validate(*pos,**kw);os.kill(os.getpid(),signal.SIGKILL)
    return actual_validate(*pos,**kw)
   def chown(path,uid,gid,*pos,**kw):
    if kind=='handoff' and Path(path).name=='leaf.key' and gid==u.pw_gid:raise OSError('injected')
    return actual_chown(path,uid,gid,*pos,**kw)
   def chmod(path,mode,*pos,**kw):
    if kind=='directory_mode' and path.parent==root and mode==0o750:raise OSError('injected')
    return actual_chmod(path,mode,*pos,**kw)
   def attempt():
    with ExitStack() as stack:
     stack.enter_context(patch('time.time',return_value=near));stack.enter_context(patch.object(d.subprocess,'run',side_effect=run));stack.enter_context(patch.object(d,'validated_context',side_effect=validate));stack.enter_context(patch.object(d.os,'chown',side_effect=chown));stack.enter_context(patch.object(Path,'chmod',chmod))
     if kind=='sync':stack.enter_context(patch.object(d.os,'fsync',side_effect=OSError('injected')))
     if kind=='sync_after_handoff':
      calls=[]
      def fsync(fd):
       calls.append(fd)
       if len(calls)==4:raise OSError('injected after directory handoff')
       return actual_fsync(fd)
      stack.enter_context(patch.object(d.os,'fsync',side_effect=fsync))
     return d.ensure_leaf(u.pw_gid,current,root=root)
   if kills:
    pid=os.fork()
    if pid==0:
     try:attempt()
     except BaseException:os._exit(2)
     os._exit(3)
    _,status=os.waitpid(pid,0);assert os.waitstatus_to_exitcode(status)==-signal.SIGKILL
   else:
    try:attempt()
    except (OSError,subprocess.SubprocessError,TLSError,KeyboardInterrupt):pass
    else:raise AssertionError('fault did not fire')
   failed=set(root.iterdir())-existing;assert len(failed)==1;failed=failed.pop()
   assert failed.stat().st_mode&0o777==0o700 and not readable(failed/'leaf.key')
   assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
   with patch('time.time',return_value=near):ready=d.ensure_leaf(u.pw_gid,current,root=root)
   directory=root/ready['tls_generation'];validated_context(directory/'leaf.pem',directory/'leaf.key',ready['certificate_sha256'],u.pw_gid)
   assert readable(directory/'leaf.key');directory.chmod(0o700)
   cases.append(dict(fault=kind,failed_generation_private=True,old_material_preserved=True,retry_valid=True,actual_sigkill=kills))
  report['result']='passed';dev.verify(ROOT,a.expected_manifest)
 except BaseException as e:
  report.update(result='failed',error_type=type(e).__name__)
  import traceback;(work/'failure.txt').write_text(traceback.format_exc())
 finally:
  report['production_preserved']=lab.preserved()==baseline
  if not report['production_preserved']:report['result']='failed'
  work.chmod(0o700);(work/'report.json').write_text(json.dumps(report,indent=2))
  print(json.dumps(dict(result=report['result'],report=str(work/'report.json'),cases=len(cases),actual_sigkill=sum(c['actual_sigkill'] for c in cases),production_preserved=report['production_preserved'],error_type=report.get('error_type'))))
 return int(report['result']!='passed')

if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
