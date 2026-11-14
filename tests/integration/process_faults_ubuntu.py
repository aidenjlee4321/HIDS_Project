"""Real process death and private mount FULL/readonly; synthetic events only."""
import json
import os
from pathlib import Path
import pwd
import signal
import shutil
import subprocess
import sys
import tempfile
from engine.ingestion import process_contract as c
from engine.ingestion.process_control import role_command

ROOT=Path(__file__).resolve().parents[2]
CHILD=r'''import json,os,signal,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[1]+'/tests/unit')
from test_process_pipeline import fixture,SOURCE
from engine.database.process_store import Store
stage=sys.argv[3]
def fault(point):
 if point==stage:os.kill(os.getpid(),signal.SIGKILL)
s=Store(Path(sys.argv[2])/'store.sqlite',SOURCE,'synthetic',fault=fault)
s.put(fixture());raise AssertionError('kill point not hit')
'''
VFS=r'''import os,sys,subprocess,json,pwd
from pathlib import Path
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[1]+'/tests/unit')
from test_process_pipeline import fixture,SOURCE
from engine.ingestion.process_control import role_command
root=Path(sys.argv[2]);kind=sys.argv[3];role=pwd.getpwnam('hids-ingest')
subprocess.run(['/usr/bin/mount','-t','tmpfs','-o','size=32m,nr_inodes=256','tmpfs',str(root)],check=True)
d=root/'store';d.mkdir(mode=0o700);os.chown(d,role.pw_uid,role.pw_gid)
# Initialize as the actual writer, with only free-space simulation to admit this
# deliberately small lab mount; production entry never offers this hook.
init="import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[1]+'/tests/unit');from engine.database.process_store import Store;from test_process_pipeline import SOURCE;s=Store(Path(sys.argv[2])/'store.sqlite',SOURCE,'synthetic',minimum_free=0,space=lambda:2**40);print('ready',flush=True);sys.stdin.read(1);s.close()"
pin=subprocess.Popen(role_command(role,'/usr/bin/python3','-I','-B','-c',init,sys.argv[1],str(d)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
assert pin.stdout.readline().strip()=='ready'
if kind=='readonly':pin.communicate('x',timeout=5);assert pin.returncode==0
if kind=='readonly':
 subprocess.run(['/usr/bin/mount','-o','remount,ro',str(root)],check=True)
 assert os.statvfs(d).f_flag & os.ST_RDONLY
else:
 fd=os.open(root/'filler',os.O_WRONLY|os.O_CREAT,0o600)
 try:
  try:
   while True:os.write(fd,bytes(65536))
  except OSError as e:assert e.errno==28
 finally:os.close(fd)
probe="""import sys,sqlite3
from pathlib import Path
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[1]+'/tests/unit')
from engine.database.process_store import Store
from test_process_pipeline import SOURCE,fixture
kind=sys.argv[3]
# Genuine SQLite VFS errors beneath a test-only bypass of admission. This proves
# rollback/error behavior separately from the already tested admission guard.
original=Store.admit;Store.admit=lambda self:None
try:
 try:
  s=Store(Path(sys.argv[2])/'store.sqlite',SOURCE,'synthetic',minimum_free=0,space=lambda:2**40)
  try:s.put(fixture())
  finally:s.close()
 except sqlite3.Error as e:
  primary=e.sqlite_errorcode&255
  # WAL open may fail before a write if readonly storage cannot create SHM.
  assert primary in ((8,14) if kind=='readonly' else (13,)),(kind,primary)
  print('sqlite_vfs_'+kind+'_refused')
 else:raise AssertionError('VFS error missing')
finally:Store.admit=original
"""
p=subprocess.run(role_command(role,'/usr/bin/python3','-I','-B','-c',probe,sys.argv[1],str(d),kind),capture_output=True,text=True,timeout=10)
if kind=='full':pin.communicate('x',timeout=5);assert pin.returncode==0
assert p.returncode==0,(p.returncode,p.stderr[-1000:]);print(p.stdout.strip())
'''

def main():
    assert os.getuid()==0
    global ROOT
    role=pwd.getpwnam('hids-ingest');root=Path(tempfile.mkdtemp(prefix='hids-process-faults.',dir='/opt'));root.chmod(0o711);results={}
    source=ROOT;code=root/'code';code.mkdir(mode=0o755)
    for name in ('engine','tests/unit'):
        for p in (source/name).rglob('*.py'):
            target=code/p.relative_to(source);target.parent.mkdir(mode=0o755,parents=True,exist_ok=True);target.write_bytes(p.read_bytes());target.chmod(0o644)
    for directory in [code,*code.rglob('*')]:
        if directory.is_dir():directory.chmod(0o755)
    ROOT=code
    for stage in ('before_commit','after_commit'):
        d=root/stage;d.mkdir(mode=0o700);os.chown(d,role.pw_uid,role.pw_gid)
        p=subprocess.run(role_command(role,'/usr/bin/python3','-I','-B','-c',CHILD,str(ROOT),str(d),stage),capture_output=True,timeout=10);assert p.returncode==-signal.SIGKILL
        check="import sqlite3,sys;from pathlib import Path;p=Path(sys.argv[1])/'store.sqlite';db=sqlite3.connect(p);assert db.execute('PRAGMA integrity_check').fetchone()==('ok',);assert db.execute('SELECT count(*) FROM process_events').fetchone()[0]==int(sys.argv[2]);db.close()"
        p=subprocess.run(role_command(role,'/usr/bin/python3','-I','-B','-c',check,str(d),'0' if stage=='before_commit' else '1'),capture_output=True,timeout=5);assert p.returncode==0
        results['sigkill_'+stage]=True
    for kind in ('full','readonly'):
        d=root/kind;d.mkdir(mode=0o755)
        p=subprocess.run(['/usr/bin/unshare','--mount','--propagation','private','--','/usr/bin/python3','-I','-B','-c',VFS,str(ROOT),str(d),kind],capture_output=True,text=True,timeout=20)
        (root/(kind+'.stderr')).write_text(p.stderr);(root/(kind+'.stderr')).chmod(0o600)
        assert p.returncode==0,(kind,p.stderr[-1500:]);results['real_sqlite_'+kind]=True
    (root/'report.json').write_text(json.dumps(results));(root/'report.json').chmod(0o600)
    print(json.dumps({'report':str(root/'report.json'),'checks':results}))
if __name__=='__main__':main()
