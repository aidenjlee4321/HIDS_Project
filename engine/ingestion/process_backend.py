"""Fixed private backend entry point; no source subscription or human API."""
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import stat
import sys
from engine.ingestion.process_receiver import serve
from engine.ingestion import process_contract as c


def credentials(name):
    role=pwd.getpwnam(name)
    c.require(role.pw_uid>0 and os.getuid()==os.geteuid()==role.pw_uid and os.getgid()==os.getegid()==role.pw_gid and len(os.getgroups())<=1 and set(os.getgroups())<={role.pw_gid})
    values={}
    for line in Path('/proc/self/status').read_text().splitlines():
        if ':' in line:
            k,v=line.split(':',1);values[k]=v.strip()
    c.require(values.get('NoNewPrivs')=='1')
    c.require(all(int(values[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')))


def main():
    listener=None
    try:
        credentials('hids-ingest');c.require(len(sys.argv)==2)
        # PID 1 performs the UID/GID transition before applying the same
        # RestrictSUIDSGID filter; this process never changes identity itself.
        from engine.ingestion.process_control import trusted
        c.require(sys.argv[1]=='/run/hids/process-backend/current.json')
        c.require(os.environ.get('LISTEN_PID')==str(os.getpid()) and os.environ.get('LISTEN_FDS')=='1')
        listener_fd=3;raw=trusted(sys.argv[1],mode=0o440)
        cfg=c.decode(raw);c.keys(cfg,'source path collector_uid max_events max_bytes minimum_free')
        c.scope(cfg['source'],'live');c.require(cfg['collector_uid']==pwd.getpwnam('hids-process').pw_uid>0)
        stopped=[False]
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stopped.__setitem__(0,True))
        listener=socket.socket(fileno=listener_fd)
        def ready():
            ready_fd=os.open('/run/hids/process-backend/ready.pipe',os.O_WRONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:os.write(ready_fd,b'READY\n')
            finally:os.close(ready_fd)
        serve(listener,Path(cfg['path']),cfg['source'],cfg['collector_uid'],ready=ready,stopped=lambda:stopped[0],timeout=10,
              store_options={k:cfg[k] for k in ('max_events','max_bytes','minimum_free')})
        return 0
    except Exception:return 1
    finally:
        if listener is not None:listener.close()
if __name__=='__main__':raise SystemExit(main())
