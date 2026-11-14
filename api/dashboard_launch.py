"""Root manual dashboard lifecycle. Never selects/starts a collection source."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from api.dashboard_service import CONFIG,INSTALL,TLS,config
from api.dashboard_tls import ensure_leaf
from api.dashboard_cli import request
from api.dashboard_browser import trusted_binary,reap
from api.pilot_service import trusted
from api.pilot_sessions import Denied,closed_json
from api.process_view import selection

UNITS=('hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket')
PREP=r'''import os,sqlite3,sys
from pathlib import Path
os.umask(0o077);dbs=[]
for value in sys.argv[1:]:
 try:
  path=Path(value);s=path.lstat();d=path.parent.lstat()
  assert path.resolve()==path and s.st_uid==os.getuid() and s.st_mode&0o777==0o600 and s.st_nlink==1 and d.st_uid==os.getuid() and d.st_mode&0o777==0o700
  assert path.is_file() and path.parent.is_dir()
  db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=.05);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA busy_timeout=50');db.execute('PRAGMA schema_version').fetchone();dbs.append(db)
 except Exception:pass
print('prepared',flush=True);sys.stdin.readline()
for db in dbs:db.close()
'''


def system(*args):return subprocess.run(['/usr/bin/systemctl',*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=15).stdout.strip()


def stop():
    system('stop',*UNITS)
    # Only the fixed viewer units; never a source or the caller's browser.
    subprocess.run(['/usr/bin/systemctl','reset-failed',*UNITS],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)


def sync_directory(path):
    fd=os.open(path,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def publish(value,gid,*,fault=lambda point:None):
    if os.getuid()!=0 or os.geteuid()!=0 or CONFIG.is_symlink() or CONFIG.resolve()!=CONFIG:raise Denied()
    trusted(CONFIG.parent,True)
    history=CONFIG.with_name('dashboard-config-history')
    if not history.exists():
        history.mkdir(mode=0o700);history.chmod(0o700);sync_directory(CONFIG.parent)
    trusted(history,True)
    s=history.lstat()
    if history.resolve()!=history or stat.S_IMODE(s.st_mode)!=0o700:raise Denied()
    pending=CONFIG.with_name('dashboard-'+str(uuid.uuid4())+'.pending')
    fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o440)
    try:
        os.fchown(fd,0,gid);os.fchmod(fd,0o440)
        with os.fdopen(fd,'w',closefd=False) as f:json.dump(value,f,separators=(',',':'));f.flush();os.fsync(fd)
    finally:os.close(fd)
    fault('after_pending_sync')
    if CONFIG.exists():
        trusted(CONFIG)
        if CONFIG.stat().st_nlink!=1 or CONFIG.stat().st_size>2048:raise Denied()
        raw=CONFIG.read_bytes();backup=history/(str(uuid.uuid4())+'.json')
        fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            os.fchown(fd,0,0);os.fchmod(fd,0o600);offset=0
            while offset<len(raw):offset+=os.write(fd,raw[offset:])
            os.fsync(fd)
        finally:os.close(fd)
        sync_directory(history)
    fault('after_archive_sync')
    # Never remove the active config before its replacement is fully prepared.
    fault('before_publish');os.replace(pending,CONFIG);fault('after_publish')
    fault('before_directory_sync');sync_directory(CONFIG.parent);fault('after_directory_sync')


def finish_preparation(prep):
    try:prep.stdin.close();prep.wait(timeout=3)
    except BaseException:
        try:reap(prep,timeout=1)
        finally:stop()
        raise


def prepare(selected,bindings):
    if os.getuid()!=os.geteuid() or os.getuid()!=0:raise Denied()
    if selected:selection(selected)
    if type(bindings) is not list or len(bindings)>2 or any(type(v) is not str or not re.fullmatch('[0-9a-f]{64}',v) for v in bindings) or len(set(bindings))!=len(bindings):raise Denied()
    backend=pwd.getpwnam('hids-ingest')
    if CONFIG.is_symlink():raise Denied()
    old=config() if CONFIG.exists() else None
    stop()
    leaf=ensure_leaf(backend.pw_gid,{k:old[k] for k in ('tls_generation','certificate_sha256')} if old else None)
    cfg=dict(version=1,mode='frozen-dashboard',port=18765,process=None,history=None,**leaf);paths=[]
    for family,path,field,values in [('process',Path('/var/lib/hids/process/store.sqlite'),'selected',selected),('history',Path('/var/lib/hids/m4/store/handoff.sqlite'),'bindings',bindings)]:
        if not values:continue
        # Missing/unsafe data does not prevent a working family or authorization.
        try:
            s=path.lstat();d=path.parent.lstat()
            if path.resolve()!=path or not stat.S_ISREG(s.st_mode) or s.st_uid!=backend.pw_uid or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or d.st_uid!=backend.pw_uid or stat.S_IMODE(d.st_mode)!=0o700:raise Denied()
            cfg[family]=dict(identity=[s.st_dev,s.st_ino],**{field:values});paths.append(str(path))
        except (OSError,Denied):continue
    prep=None
    try:
        if paths:
            from engine.ingestion.process_control import role_command
            prep=subprocess.Popen(role_command(backend,'/usr/bin/python3','-I','-B','-c',PREP,*paths),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            # A short preparation timeout must not become an unbounded root wait.
            import selectors
            with selectors.DefaultSelector() as poll:
                poll.register(prep.stdout,selectors.EVENT_READ)
                if not poll.select(3) or prep.stdout.readline()!='prepared\n':raise Denied()
        publish(cfg,backend.pw_gid)
        for prior in TLS.iterdir():
            if prior.name==leaf['tls_generation']:continue
            info=prior.lstat()
            if not re.fullmatch('[0-9a-f-]{36}',prior.name) or prior.resolve()!=prior or info.st_uid!=0 or not stat.S_ISDIR(info.st_mode) or info.st_mode&0o022:raise Denied()
            prior.chmod(0o700)
        system('start',*UNITS[1:],UNITS[0])
        cert=TLS/leaf['tls_generation']/'leaf.pem';ctx=ssl.create_default_context(cafile=str(cert))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            try:
                if system('show',UNITS[0],'-p','ActiveState','--value')!='active':raise Denied()
                with opener.open('https://127.0.0.1:18765/',timeout=.5) as result:
                    if result.status!=200:raise Denied()
                return cert
            except Denied:raise
            except OSError:time.sleep(.1)
        raise Denied()
    except BaseException:stop();raise
    finally:
        if prep:finish_preparation(prep)


def profile_present(name):
    return any(line.split(' ',1)[0]==name for line in Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())


def remove_policy(policy,name):
    try:
        subprocess.run(['/usr/sbin/apparmor_parser','--skip-cache','--remove',str(policy)],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
    except (OSError,subprocess.SubprocessError):pass
    # A timed-out load/remove may already have changed kernel state. Confirm
    # absence; retain the policy file for diagnosis if cleanup cannot be proved.
    if profile_present(name):raise Denied()


def browser(user,binary,certutil,cert,*,temporary_userns=False,headless_check=False):
    binary=trusted_binary(binary);certutil=trusted_binary(certutil)
    if user.pw_uid<=0:raise Denied()
    policy=None;work=None;attempted=False;profile=None
    try:
        if temporary_userns:
            # Root explicitly requests the same exact-binary userns allowance as
            # acceptance. No global kernel knob or browser sandbox bypass.
            if not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(binary)):raise Denied()
            work=Path(tempfile.mkdtemp(prefix='hids-browser-policy.',dir='/run'));work.chmod(0o700);policy=work/'profile'
            profile='hids-dashboard-'+uuid.uuid4().hex
            policy.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile '+profile+' '+str(binary)+' flags=(unconfined) {\n userns,\n}\n')
            attempted=True
            subprocess.run(['/usr/sbin/apparmor_parser','--skip-cache','--replace',str(policy)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
        command=dict(url=request('mint'),certificate=cert.read_text())
        script='import sys,json;sys.path.insert(0,"/opt/hids-dashboard/code");from api.dashboard_browser import run;run(sys.argv[1],sys.argv[2],json.loads(sys.stdin.readline()),headless_check='+str(headless_check)+')'
        env={k:v for k,v in os.environ.items() if k in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','LANG','LC_ALL')};env.update(XDG_RUNTIME_DIR='/run/user/'+str(user.pw_uid),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(user.pw_uid)+'/bus')
        child=subprocess.Popen(['/usr/bin/python3','-I','-B','-c',script,str(binary),str(certutil)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,user=user.pw_uid,group=user.pw_gid,extra_groups=[],text=True,env=env)
        try:
            child.stdin.write(json.dumps(command)+'\n');child.stdin.close();command.clear()
            if child.wait()!=0:raise Denied()
        except BaseException:
            reap(child,timeout=15)
            raise
    finally:
        if policy and attempted:remove_policy(policy,profile)
        if policy:
            policy.unlink();work.rmdir()


def recent(family):
    # Explicit root CLI metadata selection only. No HTTP-supplied path or SQL.
    if family not in ('process','history') or os.getuid()!=0:raise Denied()
    backend=pwd.getpwnam('hids-ingest')
    path='/var/lib/hids/process/store.sqlite' if family=='process' else '/var/lib/hids/m4/store/handoff.sqlite'
    try:
        location=Path(path);info=location.lstat();parent=location.parent.lstat()
        if location.resolve()!=location or not stat.S_ISREG(info.st_mode) or info.st_uid!=backend.pw_uid or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600 or parent.st_uid!=backend.pw_uid or stat.S_IMODE(parent.st_mode)!=0o700:return []
    except OSError:return []
    script=r'''import json,sqlite3,sys,time
from pathlib import Path
p=Path(sys.argv[1]);db=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=.05);db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,65536);db.execute("PRAGMA query_only=ON");db.execute("PRAGMA trusted_schema=OFF");deadline=time.monotonic()+2;db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
try:
 if sys.argv[2]=="process":
  values=db.execute("SELECT typeof(source_id),length(CAST(source_id AS BLOB)),substr(source_id,1,37),typeof(activation_id),length(CAST(activation_id AS BLOB)),substr(activation_id,1,37) FROM process_events GROUP BY source_id,activation_id ORDER BY max(ordinal) DESC LIMIT 2").fetchall()
  assert all(a==d=="text" and b==e==36 for a,b,c,d,e,f in values);out=[dict(source_id=c,activation_id=f) for a,b,c,d,e,f in values]
 else:
  values=db.execute("SELECT typeof(binding_key),length(CAST(binding_key AS BLOB)),substr(binding_key,1,65) FROM m4h_bindings ORDER BY binding_key LIMIT 3").fetchall();assert len(values)<=2 and all(a=="text" and b==64 for a,b,c in values);out=[c for a,b,c in values]
 print(json.dumps(out),flush=True)
finally:db.close()
'''
    from engine.ingestion.process_control import role_command
    try:
        result=subprocess.run(role_command(backend,'/usr/bin/python3','-I','-B','-c',script,path,family),capture_output=True,text=True,timeout=3,check=True)
        if len(result.stdout)>1024:raise Denied()
        value=json.loads(result.stdout)
        if family=='process':
            if value:selection(value)
        elif type(value) is not list or len(value)>2 or any(type(v) is not str or not re.fullmatch('[0-9a-f]{64}',v) for v in value):raise Denied()
        return value
    except (OSError,ValueError,subprocess.SubprocessError):return []


def main():
    p=argparse.ArgumentParser(description='Root-authorized frozen history. Never starts collection.')
    p.add_argument('operation',choices=('prepare','open','stop'));p.add_argument('--process',action='append',default=[],metavar='SOURCE_UUID:ACTIVATION_UUID');p.add_argument('--binding',action='append',default=[]);p.add_argument('--recent-process',action='store_true',help='Explicitly include the two most recent stored process activations');p.add_argument('--retained-audit',action='store_true',help='Explicitly include up to two retained M4 bindings');p.add_argument('--browser',default='/opt/hids-browser/chrome');p.add_argument('--certutil',default='/usr/bin/certutil');p.add_argument('--temporary-browser-userns',action='store_true')
    a=p.parse_args()
    try:
        if os.getuid()!=os.geteuid() or os.getuid()!=0 or not sys.stdin.isatty() or not sys.stdout.isatty():raise Denied()
        fd=os.open('/run/hids-dashboard-launch.lock',os.O_CREAT|os.O_NOFOLLOW|os.O_RDWR,0o600)
        s=os.fstat(fd)
        if s.st_uid!=0 or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=0o600:raise Denied()
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.operation=='stop':stop();print('Dashboard stopped.');return 0
        selected=[]
        for value in a.process:
            parts=value.split(':')
            if len(parts)!=2:raise Denied()
            selected.append(dict(source_id=parts[0],activation_id=parts[1]))
        if a.operation=='open':
            user=pwd.getpwuid(int(os.environ['SUDO_UID']));trusted_binary(a.browser);trusted_binary(a.certutil)
        if a.recent_process:
            if selected:raise Denied()
            selected=recent('process')
        bindings=a.binding
        if a.retained_audit:
            if bindings:raise Denied()
            bindings=recent('history')
        if a.operation=='prepare':
            prepare(selected,bindings);print('Frozen dashboard prepared. Collection unchanged.');return 0
        try:
            cert=prepare(selected,bindings)
            browser(user,a.browser,a.certutil,cert,temporary_userns=a.temporary_browser_userns)
        finally:stop()
        print('Dashboard closed and authorization revoked.');return 0
    except Exception:
        print('HIDS dashboard launch refused or stopped; check prerequisites and current service state.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
