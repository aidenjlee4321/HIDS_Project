"""Controlled sanitized Service/Runtime benchmark in fresh, isolated VM state.

Does not open installed M3 databases or change Audit policy. Native reader and
backend use actual service identities; this is not systemd/live-source acceptance.
"""
import argparse
import contextlib
import cProfile
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import resource
import signal
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid


def worker(args):
    sys.path.insert(0,str(args.app))
    from engine.ingestion.m3_runtime import Runtime
    from engine.ingestion.m3_service import Service,open_data_listener,PeerPolicy
    ingest=pwd.getpwnam('hids-ingest');reader=pwd.getpwnam('hids-audit')
    assert os.getuid()==ingest.pw_uid and os.getgid()==ingest.pw_gid
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    os.umask(0o077)
    runtime=Runtime(args.state,args.source,max_activations=4,max_pages=8192,position_limit=65536)
    endpoint=open_data_listener(args.data,ingest.pw_uid,grp.getgrnam('hids-ipc').gr_gid)
    listener=socket.socket(fileno=args.control_fd)
    service=Service(runtime,endpoint.sock,listener,PeerPolicy(reader.pw_uid,reader.pw_gid),stopped=lambda:stopping)
    profile=cProfile.Profile() if args.profile else None
    try:
        if profile:profile.enable()
        return service.run()
    finally:
        if profile:profile.disable();profile.dump_stats(str(args.state/'backend.pstats'))
        service.close();runtime.close();endpoint.close();listener.close()


@contextlib.contextmanager
def owner():
    account=pwd.getpwnam('hids-ingest');uid,gid=os.geteuid(),os.getegid()
    try:
        os.setegid(account.pw_gid);os.seteuid(account.pw_uid);yield
    finally:os.seteuid(uid);os.setegid(gid)


def query(path,sql):
    with owner():
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
        try:return db.execute(sql).fetchall()
        finally:db.close()


def rpc(path,**request):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(3);client.connect(str(path))
        client.sendall(json.dumps(dict(version=3,**request)).encode()+b'\n')
        result=bytearray()
        while not result.endswith(b'\n') and len(result)<8192:
            chunk=client.recv(8192)
            if not chunk:raise EOFError('benchmark control disconnected')
            result.extend(chunk)
        result=json.loads(result)
        if result.get('result')=='rejected':raise RuntimeError('benchmark control rejected')
        return result


def until(predicate,children=(),timeout=30):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if any(child.poll() is not None for child in children):raise RuntimeError('benchmark child exited')
        if predicate():return
        time.sleep(.01)
    raise TimeoutError('benchmark progress timeout')


def resources(pid):
    info=dict(line.split(':',1) for line in Path(f'/proc/{pid}/status').read_text().splitlines())
    fields=Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()
    return dict(rss_kib=int(info['VmRSS'].split()[0]),high_water_kib=int(info['VmHWM'].split()[0]),
        cpu_seconds=(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'))


def copy_app(source,binary,target):
    target.mkdir(mode=0o755);target.chmod(0o755)
    for path in sorted((source/'engine').rglob('*.py')):
        destination=target/path.relative_to(source);destination.parent.mkdir(parents=True,exist_ok=True)
        for parent in destination.parents:
            if parent==target:break
            parent.chmod(0o755)
        destination.write_bytes(path.read_bytes());destination.chmod(0o644)
    (target/'plugin').write_bytes(binary.read_bytes());(target/'plugin').chmod(0o755)


def trial(app,helper,directory,fixture,events,*,warmup=512,profile=False,history_files=0):
    ingest=pwd.getpwnam('hids-ingest');reader=pwd.getpwnam('hids-audit');ipc=grp.getgrnam('hids-ipc').gr_gid
    directory.mkdir(mode=0o755);directory.chmod(0o755)
    state=directory/'state';state.mkdir(mode=0o700);os.chown(state,ingest.pw_uid,ingest.pw_gid)
    data_dir=directory/'data';data_dir.mkdir(mode=0o750);data_dir.chmod(0o750);os.chown(data_dir,ingest.pw_uid,ipc)
    for index in range(history_files):
        path=state/f'synthetic-history-{index}.fixture';path.write_bytes(b'X'*4096);path.chmod(0o600)
        os.chown(path,ingest.pw_uid,ingest.pw_gid)
    control=directory/'control.sock';data=data_dir/'audit.sock';source=str(uuid.uuid4());activation=str(uuid.uuid4())
    backend=plugin=None;out=None
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(str(control));control.chmod(0o600);listener.listen(16)
        out=(directory/'children.stderr').open('xb');os.chmod(directory/'children.stderr',0o600)
        command=[sys.executable,'-B',str(helper),'--worker','--app',str(app),'--state',str(state),
                 '--data',str(data),'--source',source,'--control-fd',str(listener.fileno())]
        if profile:command.append('--profile')
        try:
            backend=subprocess.Popen(['/usr/bin/setpriv','--no-new-privs','--bounding-set=-all','--inh-caps=-all',
                '--ambient-caps=-all','--reuid',str(ingest.pw_uid),'--regid',str(ingest.pw_gid),'--groups',str(ipc),*command],
                pass_fds=(listener.fileno(),),stdout=subprocess.DEVNULL,stderr=out,env={'PATH':'/usr/bin:/bin','LANG':'C'})
            until(lambda:data.exists(),[backend])
            rpc(control,command='activate',source=source,activation=activation)
            scope=rpc(control,command='lease')['scope']
            plugin=subprocess.Popen(['/usr/bin/setpriv','--no-new-privs','--bounding-set=-all','--inh-caps=-all',
                '--ambient-caps=-all','--reuid',str(reader.pw_uid),'--regid',str(reader.pw_gid),'--groups',str(ipc),
                str(app/'plugin'),str(data),scope['activation'],scope['generation'],scope['lease'],
                str(reader.pw_uid),str(reader.pw_gid),str(ingest.pw_uid),str(ingest.pw_gid),str(ipc),'--current-tail'],
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=out)
            until(lambda:rpc(control,command='status')['source_ready'],[backend,plugin])
            database=state/(activation+'.sqlite')
            def send(first,last):
                plugin.stdin.write(b''.join(fixture.replace(b':100)',f':{10000+i})'.encode()) for i in range(first,last)))
                plugin.stdin.flush()
                until(lambda:query(database,'SELECT COUNT(*) FROM m3_execution')==[(last,)],[backend,plugin])
            for first in range(0,warmup,64):send(first,min(warmup,first+64))
            cpu_before={name:resources(child.pid) for name,child in (('backend',backend),('collector',plugin))}
            started=time.monotonic();samples=[]
            for first in range(warmup,warmup+events,64):
                send(first,min(warmup+events,first+64))
                if (first-warmup)%512==0:
                    samples.append(dict(events=min(events,first-warmup+64),backend=resources(backend.pid),collector=resources(plugin.pid)))
            elapsed=time.monotonic()-started
            cpu_after={name:resources(child.pid) for name,child in (('backend',backend),('collector',plugin))}
            rows=query(database,'SELECT identity,payload FROM m3_execution ORDER BY first_offset')
            assert [identity for identity,_ in rows]==[f'1794096000.123:{10000+i}' for i in range(warmup+events)]
            assert query(database,'SELECT scanned=frontier FROM m3_cursor')==[(1,)]
            assert query(database,'SELECT COUNT(*) FROM m3_positions')==[(6*(warmup+events),)]
            health=rpc(control,command='status')['event_health']
            assert not any(health.get(key) for key in ('timeouts','late_records','resource_incidents','discarding','rejected_groups'))
            if 'observed_executions' in health:assert health['observed_executions']==warmup+events
            result=dict(events=events,warmup=warmup,seconds=round(elapsed,6),events_per_second=round(events/elapsed,3),
                backend_cpu_seconds=round(cpu_after['backend']['cpu_seconds']-cpu_before['backend']['cpu_seconds'],3),
                collector_cpu_seconds=round(cpu_after['collector']['cpu_seconds']-cpu_before['collector']['cpu_seconds'],3),
                samples=samples,database_pages=query(database,'PRAGMA page_count')[0][0],
                active_state_bytes=sum(p.stat().st_blocks*512 for p in state.iterdir() if p.is_file()),
                payload_sha256=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest(),
                history_files=history_files,state=str(state),activation=activation)
            rpc(control,command='deactivate',source=source,activation=activation)
            return result
        finally:
            for child in (plugin,backend):
                if child:
                    if child.poll() is None:child.terminate()
                    try:child.wait(timeout=8)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
            if plugin and plugin.stdin:plugin.stdin.close()
            if out:out.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--profile',action='store_true')
    parser.add_argument('--app',type=Path);parser.add_argument('--state',type=Path);parser.add_argument('--data',type=Path)
    parser.add_argument('--source');parser.add_argument('--control-fd',type=int)
    parser.add_argument('--before',type=Path);parser.add_argument('--before-plugin',type=Path)
    parser.add_argument('--after',type=Path);parser.add_argument('--after-plugin',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--events',type=int,default=4096)
    parser.add_argument('--history-files',type=int,default=0)
    args=parser.parse_args()
    if args.worker:return worker(args)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    assert os.getuid()==0 and 512<=args.events<=8000 and 0<=args.history_files<=256
    code=Path(tempfile.mkdtemp(prefix='hids-m3-perf-code.',dir='/usr/lib'));code.chmod(0o755)
    copy_app(args.before,args.before_plugin,code/'before');copy_app(args.after,args.after_plugin,code/'after')
    helper=code/'worker.py';helper.write_bytes(Path(__file__).read_bytes());helper.chmod(0o644)
    directory=Path(tempfile.mkdtemp(prefix='hids-m3-perf.',dir='/var/lib/hids'));directory.chmod(0o755)
    lines=(args.after/'tests/fixtures/audit/structural-exec.log').read_bytes().splitlines();lines[-1]+=b' '
    fixture=b'\n'.join(lines)+b'\n';rows=[]
    for index,label in enumerate(('before','after','after','before','before','after')):
        value=trial(code/label,helper,directory/str(index),fixture,args.events,history_files=args.history_files)
        value.update(variant=label,trial=index);rows.append(value)
        print(json.dumps({k:value[k] for k in ('variant','trial','seconds','events_per_second','backend_cpu_seconds')},sort_keys=True),flush=True)
    assert len({r['payload_sha256'] for r in rows})==1,'normalized payload differs between variants'
    profile=trial(code/'after',helper,directory/'profile',fixture,512,warmup=64,profile=True,history_files=args.history_files)
    import pstats
    stats=pstats.Stats(str(Path(profile['state'])/'backend.pstats'))
    top=sorted(stats.stats.items(),key=lambda item:item[1][3],reverse=True)[:20]
    summary=dict(format=1,scope='isolated_service_runtime_synthetic',trials=rows,
        medians={label:statistics.median(r['events_per_second'] for r in rows if r['variant']==label) for label in ('before','after')},
        profile=[dict(file=Path(key[0]).name,line=key[1],function=key[2],calls=value[1],own_seconds=value[2],cumulative_seconds=value[3]) for key,value in top],
        evidence=str(directory),code=str(code))
    args.output.write_text(json.dumps(summary,sort_keys=True)+'\n');args.output.chmod(0o600)
    print(json.dumps(dict(medians=summary['medians'],report=str(args.output),evidence=str(directory)),sort_keys=True),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
