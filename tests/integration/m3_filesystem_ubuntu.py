"""Bounded private-mount ext4 capacity/SQLite failure test; no host data changes."""
import argparse
from contextlib import closing
import errno
import json
import os
from pathlib import Path
import pwd
import select
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid

MIB=1024*1024
SIZE=64*MIB


def command(*args):
    return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=30).decode().strip()


def send(stream,value):
    stream.write(json.dumps(value)+'\n');stream.flush()


def receive(stream):
    if not select.select([stream],[],[],20)[0]:raise TimeoutError('filesystem test peer stalled')
    line=stream.readline()
    if not line:raise RuntimeError('filesystem test peer exited')
    return json.loads(line)


def available(path):
    value=os.statvfs(path);return value.f_bavail*value.f_frsize


def fill(fd,mount,target,host_device):
    """Allocate only our own filler on a distinct, bounded test filesystem."""
    info=os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_dev!=mount.stat().st_dev
            or info.st_dev==host_device):raise ValueError('unsafe filler filesystem')
    while available(mount)>target:
        size=os.fstat(fd).st_size;remaining=available(mount)-target
        amount=min(MIB,remaining//4096*4096)
        if not amount:break
        if size+amount>SIZE:raise ValueError('filler exceeds image bound')
        try:os.posix_fallocate(fd,size,amount)
        except OSError as exc:
            if exc.errno!=errno.ENOSPC:raise
            break
    os.fsync(fd)
    return available(mount)


def writer(state,incoming,outgoing):
    # Installed files are matched by the outer workflow; no root source/log reads.
    sys.path.insert(0,'/usr/lib/hids')
    from engine.ingestion.m3_runtime import Runtime
    from engine.ingestion import m3_storage
    policy=m3_storage.defaults(64,4)
    policy.update(warning_free_bytes=4*MIB,critical_free_bytes=2*MIB,minimum_free_bytes=MIB)
    source=str(uuid.uuid4());activation=str(uuid.uuid4());runtime=None
    execution=dict(syscall=221,pid=42,ppid=1,uid=1000,euid=1000,suid=1000,fsuid=1000,
        auid=None,session=7,path_count=1,success=True,cwd_present=True,proctitle_present=True,
        result=0,exe_base64='L2Jpbi94',comm_base64='eA==')
    def open_runtime():return Runtime(state,source,max_activations=4,max_pages=64,position_limit=32,storage=policy)
    try:
        runtime=open_runtime();runtime.activate(activation);runtime.claim();progress=runtime.progress
        progress.start_stream();progress.register('1.001:1',0,10,eoe=True);progress.accept('1.001:1',execution)
        progress.register('1.001:2',10,20,eoe=True);position=progress.positions()
        rows=lambda:progress.db.execute('SELECT identity FROM m3_execution').fetchall()
        assert rows()==[('1.001:1',)]
        send(outgoing,dict(stage='initial',storage=runtime.storage.observe(force=True)))
        assert receive(incoming)['command']=='pressure'
        status=runtime.storage.observe(force=True);assert status['state']=='critical',status
        try:progress.accept('1.001:2',execution)
        except m3_storage.StoragePressure:pass
        else:raise AssertionError('real filesystem pressure admitted a transaction')
        assert rows()==[('1.001:1',)] and progress.positions()==position
        send(outgoing,dict(stage='blocked',storage=status,positions=position))
        assert receive(incoming)['command']=='race'
        assert runtime.storage.observe(force=True)['state']=='normal'
        # Release redundant WAL extents before testing a genuine new write.
        progress.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        original_before=runtime.storage.before;armed=[True]
        def before(path):
            original_before(path)
            if armed[0]:
                armed[0]=False
                send(outgoing,dict(stage='admitted_before_external_fill',storage=runtime.storage.observe(force=True)))
                assert receive(incoming)['command']=='filled'
        runtime.storage.before=before
        failure=None
        try:progress.accept('1.001:2',execution)
        except sqlite3.Error as exc:failure=exc.sqlite_errorcode
        finally:runtime.storage.before=original_before
        assert failure is not None and failure&255==sqlite3.SQLITE_FULL,('expected actual SQLITE_FULL',failure)
        assert not progress.db.in_transaction and rows()==[('1.001:1',)]
        assert progress._state('1.001:2')=='open' and progress.positions()==position
        send(outgoing,dict(stage='sqlite_full',sqlite_errorcode=failure,storage=runtime.storage.observe(force=True),positions=position))
        assert receive(incoming)['command']=='recover'
        runtime.close();runtime=open_runtime()
        old=runtime.current();assert old['state']=='interrupted' and old['code']=='backend_restart'
        history=runtime.open_progress(activation,old['generation'])
        try:
            assert history.db.execute('PRAGMA integrity_check').fetchone()==('ok',)
            assert history.db.execute('SELECT identity FROM m3_execution').fetchall()==[('1.001:1',)]
            assert history._state('1.001:2')=='interrupted' and history.positions()==(20,20)
            assert history.register('1.001:2',20,30,eoe=True)=='suppressed'
            assert not history.db.execute("SELECT 1 FROM m3_execution WHERE identity='1.001:2'").fetchone()
        finally:history.close()
        assert not runtime.status()['source_ready']
        send(outgoing,dict(stage='recovered',integrity='ok',accepted=1,interrupted=1,late_suppressed=True,
            source_ready=False,storage=runtime.storage.observe(force=True)))
        assert receive(incoming)['command']=='close_for_readonly'
        runtime.close();runtime=None
        send(outgoing,dict(stage='closed_for_readonly'))
        assert receive(incoming)['command']=='readonly'
        error=None
        try:runtime=open_runtime()
        except OSError as exc:
            assert exc.errno==errno.EROFS;error={'errno':exc.errno}
        except sqlite3.Error as exc:
            assert exc.sqlite_errorcode&255 in (sqlite3.SQLITE_READONLY,sqlite3.SQLITE_CANTOPEN)
            error={'sqlite_errorcode':exc.sqlite_errorcode}
        assert error is not None,'read-only filesystem unexpectedly admitted a writer'
        # Private, quiescent, kernel-read-only image: immutable avoids creating WAL
        # sidecars for this inspection. This is not a production recovery shortcut.
        with closing(sqlite3.connect((state/(activation+'.sqlite')).as_uri()+'?mode=ro&immutable=1',uri=True)) as history:
            assert history.execute('SELECT identity FROM m3_execution').fetchall()==[('1.001:1',)]
            assert history.execute("SELECT state FROM m3_disposition WHERE identity='1.001:2'").fetchone()==('interrupted',)
        send(outgoing,dict(stage='readonly_blocked',error=error,accepted=1,interrupted=1))
        assert receive(incoming)['command']=='restart_writable'
        runtime=open_runtime();assert not runtime.status()['source_ready']
        history=runtime.open_progress(activation,runtime.current()['generation'])
        try:assert history.db.execute('PRAGMA integrity_check').fetchone()==('ok',)
        finally:history.close()
        send(outgoing,dict(stage='readonly_recovered',integrity='ok',source_ready=False))
    finally:
        if runtime:runtime.close()


def namespace(workspace,mount,parent_namespace):
    assert os.getuid()==0 and os.readlink('/proc/self/ns/mnt')!=parent_namespace
    image=workspace/'filesystem.ext4';account=pwd.getpwnam('hids-ingest')
    command('mount','-o','loop,nodev,nosuid,noexec',str(image),str(mount))
    child=None;filler=None
    try:
        os.chown(mount,0,account.pw_gid);mount.chmod(0o710)
        state=mount/'state';state.mkdir(mode=0o700);os.chown(state,account.pw_uid,account.pw_gid)
        filler=os.open(mount/'filler',os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
        read_parent,write_child=os.pipe();read_child,write_parent=os.pipe()
        child=os.fork()
        if child==0:
            os.close(filler);os.close(read_parent);os.close(write_parent)
            os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
            try:
                with os.fdopen(read_child) as incoming,os.fdopen(write_child,'w') as outgoing:
                    writer(state,incoming,outgoing)
            except BaseException:
                import traceback;traceback.print_exc();os._exit(1)
            os._exit(0)
        os.close(read_child);os.close(write_child);evidence=[]
        with os.fdopen(read_parent) as incoming,os.fdopen(write_parent,'w') as outgoing:
            item=receive(incoming);assert item['stage']=='initial';evidence.append(item)
            free=fill(filler,mount,3*MIB//2,workspace.stat().st_dev)
            assert MIB<free<2*MIB
            send(outgoing,dict(command='pressure'))
            item=receive(incoming);assert item['stage']=='blocked';evidence.append(item)
            os.ftruncate(filler,0);os.fsync(filler);send(outgoing,dict(command='race'))
            item=receive(incoming);assert item['stage']=='admitted_before_external_fill';evidence.append(item)
            free=fill(filler,mount,0,workspace.stat().st_dev);assert free<4096
            send(outgoing,dict(command='filled'))
            item=receive(incoming);assert item['stage']=='sqlite_full';evidence.append(item)
            os.ftruncate(filler,0);os.fsync(filler);send(outgoing,dict(command='recover'))
            item=receive(incoming);assert item['stage']=='recovered';evidence.append(item)
            send(outgoing,dict(command='close_for_readonly'))
            item=receive(incoming);assert item['stage']=='closed_for_readonly';evidence.append(item)
            os.close(filler);filler=None  # no open writable inode during remount
            command('mount','-o','remount,ro',str(mount));send(outgoing,dict(command='readonly'))
            item=receive(incoming);assert item['stage']=='readonly_blocked';evidence.append(item)
            command('mount','-o','remount,rw',str(mount));send(outgoing,dict(command='restart_writable'))
            item=receive(incoming);assert item['stage']=='readonly_recovered';evidence.append(item)
        _,status=os.waitpid(child,0);child=None;assert status==0
        result={'result':'passed','scope':'private_ext4_capacity_sqlite_full_and_readonly','image_bytes':SIZE,
                'mount_namespace_private':True,'writer_uid':account.pw_uid,'stages':evidence}
        target=workspace/'report.json';target.write_text(json.dumps(result,sort_keys=True)+'\n');target.chmod(0o600)
        print('PASS: actual filesystem reserve blocks writes; real SQLITE_FULL rolls back atomically; committed B survives and interrupted A cannot resurrect; read-only startup fails closed and recovers without reauthorization',flush=True)
    finally:
        if filler is not None:os.close(filler)
        if child:
            try:os.kill(child,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(child,0)
        command('umount',str(mount))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace',nargs=3,metavar=('WORKSPACE','MOUNT','PARENT_NAMESPACE'))
    args=parser.parse_args();assert os.getuid()==0
    if args.namespace:
        namespace(Path(args.namespace[0]),Path(args.namespace[1]),args.namespace[2]);return
    workspace=Path(tempfile.mkdtemp(prefix='hids-m3-filesystem.',dir='/root'));workspace.chmod(0o700)
    mount=Path(tempfile.mkdtemp(prefix='hids-m3-filesystem.',dir='/run'))
    image=workspace/'filesystem.ext4'
    fd=os.open(image,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.ftruncate(fd,SIZE);os.close(fd)
    command('mkfs.ext4','-q','-F','-m','0','-E','lazy_itable_init=0,lazy_journal_init=0',str(image))
    original_namespace=os.readlink('/proc/self/ns/mnt')
    try:
        subprocess.run(['unshare','--mount','--propagation','private',sys.executable,'-B',str(Path(__file__).resolve()),
            '--namespace',str(workspace),str(mount),original_namespace],check=True,timeout=120)
    finally:
        assert os.readlink('/proc/self/ns/mnt')==original_namespace
        assert mount.stat().st_dev==mount.parent.stat().st_dev,'mount escaped private namespace'
        devices=command('losetup','--associated',str(image),'--noheadings','--output','NAME').splitlines()
        for device in devices:
            assert device.startswith('/dev/loop') and device[9:].isdigit()
            command('losetup','--detach',device)
        assert not command('losetup','--associated',str(image),'--noheadings','--output','NAME')
        mount.rmdir()
    report=json.loads((workspace/'report.json').read_text());report['cleanup']='verified'
    (workspace/'report.json').write_text(json.dumps(report,sort_keys=True)+'\n')
    print('Private mount/loop cleanup verified; retained image and report '+str(workspace/'report.json'),flush=True)


if __name__=='__main__':main()
