"""Ordinary-user transient Chromium profile; bootstrap travels over private pipes."""
import fcntl
import json
import os
from pathlib import Path
import selectors
import signal
import shutil
import subprocess
import sys
import tempfile
import time


def trusted_binary(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('browser prerequisite unavailable')
    for p in (path,*path.parents):
        s=p.lstat()
        if s.st_uid!=0 or s.st_mode&0o022:raise ValueError('browser prerequisite unavailable')
    if not path.is_file() or not os.access(path,os.X_OK):raise ValueError('browser prerequisite unavailable')
    return path


def reap(child,*,timeout=8,group=False):
    """Stop only this launch's owned worker/session, then collect its status."""
    if group:
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    elif child.poll() is None:child.terminate()
    try:child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if group:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:child.kill()
        child.wait(timeout=3)
    finally:
        # Chromium may leave children after its leader exits. This process group
        # belongs to the fresh session created for this launch only.
        if group:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass


class Pipe:
    def __init__(self,read,write):self.read=read;self.write=write;self.buffer=b'';self.id=0
    def call(self,method,params=None):
        self.id+=1;identifier=self.id
        raw=json.dumps(dict(id=identifier,method=method,params=params or {}),separators=(',',':')).encode()+b'\0'
        while raw:
            n=os.write(self.write,raw);raw=raw[n:]
        deadline=time.monotonic()+15
        with selectors.DefaultSelector() as selector:
            selector.register(self.read,selectors.EVENT_READ)
            while time.monotonic()<deadline:
                while b'\0' in self.buffer:
                    packet,self.buffer=self.buffer.split(b'\0',1);value=json.loads(packet)
                    if value.get('id')==identifier:
                        if 'error' in value:raise ValueError('browser pipe refused')
                        return value.get('result',{})
                if len(self.buffer)>1024*1024:raise ValueError('browser pipe limit')
                if not selector.select(max(0,deadline-time.monotonic())):break
                chunk=os.read(self.read,65536)
                if not chunk:break
                self.buffer+=chunk
        raise ValueError('browser pipe unavailable')


def run(binary,certutil,command,*,headless_check=False):
    if os.getuid()==0 or os.getuid()!=os.geteuid():raise ValueError('ordinary browser required')
    binary=trusted_binary(binary);certutil=trusted_binary(certutil)
    from api.pilot_sessions import digest
    prefix='https://127.0.0.1:18765/#grant='
    if type(command) is not dict or set(command)!={'url','certificate'} or type(command['url']) is not str or not command['url'].startswith(prefix):raise ValueError('invalid launch')
    digest(command['url'][len(prefix):])
    if type(command['certificate']) is not str or len(command['certificate'])>32768:raise ValueError('invalid leaf')
    def terminate(signum,frame):
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        raise SystemExit(128+signum)
    previous=signal.signal(signal.SIGTERM,terminate)
    home=None;child=None;fds=[]
    try:
        home=Path(tempfile.mkdtemp(prefix='hids-dashboard-browser.'))
        nss=home/'.local/share/pki/nssdb';nss.mkdir(parents=True,mode=0o700);cert=home/'leaf.pem';cert.write_text(command['certificate']);cert.chmod(0o600)
        for args in (['-N','--empty-password'],['-A','-n','hids-localhost-leaf','-t','P,,','-i',str(cert)]):
            subprocess.run([str(certutil),*args,'-d','sql:'+str(nss)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5,check=True)
        incoming,send=os.pipe();receive,outgoing=os.pipe();fds=[incoming,send,receive,outgoing]
        env={k:v for k,v in os.environ.items() if k in ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','LANG','LC_ALL')}
        env.update(HOME=str(home),XDG_DATA_HOME=str(home/'.local/share'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),PATH='/usr/bin:/bin')
        args=[str(binary),'--remote-debugging-pipe','--enable-automation','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--disable-default-apps','--disable-domain-reliability','--metrics-recording-only','--no-pings','--user-data-dir='+str(home/'user-data'),'about:blank']
        if headless_check:args.insert(1,'--headless=new')
        # An ordinary helper maps inherited descriptors immediately before exec.
        # No URL, bootstrap or bearer ever appears in browser command arguments.
        child=subprocess.Popen(['/usr/bin/python3','-I','-B',str(Path(__file__)), '--exec',str(incoming),str(outgoing),*args],pass_fds=(incoming,outgoing),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,start_new_session=True)
        os.close(incoming);fds.remove(incoming);os.close(outgoing);fds.remove(outgoing)
        pipe=Pipe(receive,send);pipe.call('Browser.getVersion')
        args=pipe.call('Browser.getBrowserCommandLine')['arguments']
        if any(a.startswith(('--no-sandbox','--ignore-certificate-errors','--disable-setuid-sandbox','--allow-insecure-localhost','--remote-debugging-port')) for a in args):raise ValueError('browser isolation refused')
        pipe.call('Target.createTarget',dict(url=command['url']));command.clear()
        if headless_check:time.sleep(2);pipe.call('Browser.close')
        result=child.wait()
        if result!=0:raise ValueError('browser exited unsuccessfully')
    finally:
        command.clear()
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        try:
            try:
                if child:reap(child,group=True)
            finally:
                for fd in fds:os.close(fd)
                if home:shutil.rmtree(home)
        finally:signal.signal(signal.SIGTERM,previous)


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--exec':
        if os.getuid()==0:raise ValueError('ordinary browser required')
        read,write=map(int,sys.argv[2:4]);r=fcntl.fcntl(read,fcntl.F_DUPFD_CLOEXEC,10);w=fcntl.fcntl(write,fcntl.F_DUPFD_CLOEXEC,10)
        os.dup2(r,3,inheritable=True);os.dup2(w,4,inheritable=True)
        for fd in set((read,write,r,w))-{3,4}:os.close(fd)
        os.execv(sys.argv[4],sys.argv[4:])
    if len(sys.argv)!=3:raise ValueError('invalid launch')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from api.pilot_sessions import closed_json
    command=closed_json(sys.stdin.buffer.readline(32769),{'url','certificate'})
    run(sys.argv[1],sys.argv[2],command)
if __name__=='__main__':
    try:main()
    except Exception:print('HIDS browser prerequisite unavailable or launch stopped',file=sys.stderr);raise SystemExit(1)
