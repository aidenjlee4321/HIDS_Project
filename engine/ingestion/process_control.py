"""Root activation lease/supervision only. Never collects source events or writes SQLite."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import select
import signal
import socket
import stat
import subprocess
import sys
import time
from engine.ingestion import process_contract as c

CONFIG=Path('/etc/hids/process.json')
RUNTIME=Path('/run/hids/process')
GRANT=RUNTIME/'next-start.json'
STATUS=RUNTIME/'status.json'
UNIT='hids-process-runtime.service'

def trusted(path,limit=16384,mode=None):
    path=Path(path);c.require(path.is_absolute() and path.resolve()==path)
    for p in path.parents:
        s=p.lstat();c.require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(fd);c.require(s.st_uid==0 and stat.S_ISREG(s.st_mode) and s.st_nlink==1 and not s.st_mode&0o022 and 0<s.st_size<=limit)
        if mode is not None:c.require(stat.S_IMODE(s.st_mode)==mode)
        data=bytearray()
        while len(data)<=limit:
            chunk=os.read(fd,min(65536,limit+1-len(data)))
            if not chunk:break
            data.extend(chunk)
        c.require(len(data)==s.st_size)
        data=bytes(data)
        return data
    finally:os.close(fd)

def configuration():
    value=c.decode(trusted(CONFIG,mode=0o440));c.keys(value,'version source_id code binary binary_sha256 max_events max_bytes minimum_free')
    c.require(type(value['version']) is int and value['version']==1 and c.uuid_valid(value['source_id']))
    c.require(value['code']=='/opt/hids-process-pipeline/code' and value['binary']=='/opt/hids-process-pipeline/process-collector')
    c.require(type(value['binary_sha256']) is str and len(value['binary_sha256'])==64)
    c.require(hashlib.sha256(trusted(value['binary'],32*1024*1024)).hexdigest()==value['binary_sha256'])
    for k,lo,hi in [('max_events',1,10000),('max_bytes',40*1024*1024,64*1024*1024),('minimum_free',256*1024*1024,2**63-1)]:c.integer(value[k],lo,hi)
    return value

def write_new(path,value,mode=0o600,gid=0):
    raw=c.dump(value).encode('ascii');c.require(len(raw)<=16384)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        os.fchown(fd,0,gid);os.fchmod(fd,mode)
        offset=0
        while offset<len(raw):
            n=os.write(fd,raw[offset:]);c.require(n>0);offset+=n
        os.fsync(fd)
    finally:os.close(fd)

def publish(value):
    # Root control metadata only; event/IPC/storage contracts remain unchanged.
    value=dict(value,version=2,runtime_pid=os.getpid(),runtime_invocation=os.environ.get('INVOCATION_ID'))
    path=RUNTIME/('status-'+str(os.getpid())+'.tmp')
    write_new(path,value);os.replace(path,STATUS)
    fd=os.open(RUNTIME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def runtime_directory():
    c.require(RUNTIME.resolve()==RUNTIME)
    s=RUNTIME.lstat();c.require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o750 and s.st_gid==pwd.getpwnam('hids-process').pw_gid)
    for parent in RUNTIME.parents:
        s=parent.lstat();c.require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022)

def authorize(entry):
    c.require(os.getuid()==os.geteuid()==0)
    runtime_directory();cfg=configuration();c.require(entry['source']==cfg['source_id'])
    for name in ('activation','generation'):c.require(c.uuid_valid(entry[name]))
    write_new(GRANT,dict(version=1,source_id=entry['source'],activation_id=entry['activation'],generation=entry['generation'],expires=time.monotonic()+30))

def role_command(role,program,*args):
    return ['/usr/bin/setpriv','--reuid='+str(role.pw_uid),'--regid='+str(role.pw_gid),'--clear-groups','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','--no-new-privs','--',str(program),*map(str,args)]

PARTS=('hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket')
BACKEND_RUNTIME=Path('/run/hids/process-backend')

def system(*args):
    return subprocess.check_output(['/usr/bin/systemctl',*args],text=True,timeout=10).strip()
def unit_state(name):return system('show',name,'-p','ActiveState','--value')
def runtime_scope():
    value=dict(line.split('=',1) for line in system('show',UNIT,'--property=ActiveState,MainPID,InvocationID').splitlines() if '=' in line)
    c.require(set(value)=={'ActiveState','MainPID','InvocationID'} and value['MainPID'].isdigit())
    value['MainPID']=int(value['MainPID']);return value
def outcome(name):
    return int(system('show',name,'-p','ExecMainStatus','--value'))
def wait_inactive(name,seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if unit_state(name) in ('inactive','failed'):return False
        time.sleep(.05)
    system('stop',name)
    return True
def latest(path,value,gid):
    tmp=path.with_name(path.name+'.pending');write_new(tmp,value,0o440,gid);os.replace(tmp,path)

def run(cfg,grant,*,binary=None):
    # No setuid/setgid occurs in this coordinator. PID 1 starts the fixed-role
    # services, each with its own zero-capability and syscall restrictions.
    c.require(binary is None) # Acceptance uses a root-only collector unit drop-in.
    reader=pwd.getpwnam('hids-process');backend=pwd.getpwnam('hids-ingest')
    c.require(reader.pw_uid>0 and backend.pw_uid>0 and reader.pw_uid!=backend.pw_uid)
    stopped=[False]
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stopped.__setitem__(0,True))
    source=dict(adapter='linux.cn_proc',mode='live',source_id=grant['source_id'],activation_id=grant['activation_id'],boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),profile=c.PROFILE);c.scope(source,'live')
    state=dict(version=1,source=grant['source_id'],activation=grant['activation_id'],generation=grant['generation'],state='starting',backend_exit=None,collector_exit=None)
    publish(state);listener=None;lease=None;ready_fd=None;started=[];pidfds=[]
    try:
        c.require(all(unit_state(name)=='inactive' for name in PARTS))
        s=BACKEND_RUNTIME.lstat();c.require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o750 and s.st_gid==backend.pw_gid)
        collector_cfg=dict(source=source,socket=str(RUNTIME/'events.sock'),peer_uid=0,lease_socket=str(RUNTIME/'lease.sock'))
        latest(RUNTIME/'current.json',collector_cfg,reader.pw_gid)
        backend_cfg=dict(source=source,path='/var/lib/hids/process/store.sqlite',collector_uid=reader.pw_uid,**{k:cfg[k] for k in ('max_events','max_bytes','minimum_free')})
        latest(BACKEND_RUNTIME/'current.json',backend_cfg,backend.pw_gid)
        fifo=BACKEND_RUNTIME/'ready.pipe';c.require(not os.path.lexists(fifo));os.mkfifo(fifo,0o660);os.chown(fifo,0,backend.pw_gid);fifo.chmod(0o660)
        ready_fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC)
        lease_path=RUNTIME/'lease.sock';c.require(not os.path.lexists(lease_path))
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM|socket.SOCK_CLOEXEC);listener.bind(str(lease_path));os.chown(lease_path,0,reader.pw_gid);lease_path.chmod(0o660);listener.listen(1);listener.settimeout(5)
        system('start','hids-process-backend.socket');started.extend(('hids-process-backend.socket','hids-process-backend.service'))
        system('start','hids-process-collector.service');started.append('hids-process-collector.service')
        lease,_=listener.accept();lease.settimeout(2)
        import struct
        peer=struct.unpack('3i',lease.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        c.require(peer[1]==reader.pw_uid and peer[0]==int(system('show','hids-process-collector.service','-p','MainPID','--value')))
        lease.sendall(c.dump(dict(source_id=source['source_id'],activation_id=source['activation_id'])).encode('ascii')+b'\n')
        data=bytearray();deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if not select.select([ready_fd],[],[],.05)[0]:continue
            data.extend(os.read(ready_fd,32));c.require(len(data)<=32)
            if b'\n' in data:break
        c.require(data==b'READY\n')
        state['state']='initialized_delivery_unproven';publish(state)
        for name in ('hids-process-collector.service','hids-process-backend.service'):
            pid=int(system('show',name,'-p','MainPID','--value'))
            if pid>0:pidfds.append(os.pidfd_open(pid))
        while not stopped[0]:
            if not pidfds or select.select(pidfds,[],[],.1)[0]:break
    finally:
        if lease is not None:lease.close()
        forced=False
        for name in ('hids-process-collector.service','hids-process-backend.service'):
            if name in started:
                forced=wait_inactive(name,4) or forced
        for name in reversed(PARTS):
            if name in started:system('stop',name)
        if listener is not None:listener.close()
        if ready_fd is not None:os.close(ready_fd)
        for fd in pidfds:os.close(fd)
        state.update(backend_exit=outcome('hids-process-backend.service') if 'hids-process-backend.service' in started else None,collector_exit=outcome('hids-process-collector.service') if 'hids-process-collector.service' in started else None,forced=forced)
        state['state']='stopped' if not forced and state['collector_exit']==0 and state['backend_exit']==0 else 'failed';publish(state)
        # Only our own ephemeral IPC paths; no security evidence is removed.
        for path in (RUNTIME/'lease.sock',BACKEND_RUNTIME/'ready.pipe'):
            if path.exists():path.unlink()
    return 0 if state['state']=='stopped' else 1

def main():
    try:
        c.require(os.getuid()==os.geteuid()==0 and len(sys.argv)==1)
        cfg=configuration();runtime_directory()
        lock=os.open(RUNTIME/'owner.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        raw=trusted(GRANT,4096,0o600);grant=c.decode(raw);c.keys(grant,'version source_id activation_id generation expires')
        c.require(type(grant['version']) is int and grant['version']==1 and grant['source_id']==cfg['source_id'] and c.uuid_valid(grant['activation_id']) and c.uuid_valid(grant['generation']))
        c.require(type(grant['expires']) in (int,float) and 0<grant['expires']-time.monotonic()<=30)
        GRANT.unlink() # One-use authorization, not security history; restart cannot reuse it.
        return run(cfg,grant)
    except Exception:return 1
if __name__=='__main__':raise SystemExit(main())
