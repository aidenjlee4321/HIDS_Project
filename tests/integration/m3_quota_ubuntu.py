"""Actual UID hard-quota failure/recovery on a fenced private ext4 loop image."""
import argparse
import errno
import json
import os
from pathlib import Path
import pwd
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import traceback
import uuid
from m3_filesystem_ubuntu import command,receive,send,available,MIB,SIZE


def writer(state,filler,incoming,outgoing):
    sys.path.insert(0,'/usr/lib/hids')
    from engine.ingestion.m3_runtime import Runtime
    from engine.ingestion import m3_storage
    policy=m3_storage.defaults(64,4)
    policy.update(warning_free_bytes=4*MIB,critical_free_bytes=2*MIB,minimum_free_bytes=MIB)
    source=str(uuid.uuid4());activation=str(uuid.uuid4());runtime=None
    event=dict(syscall=221,pid=42,ppid=1,uid=1000,euid=1000,suid=1000,fsuid=1000,auid=None,
        session=7,path_count=1,success=True,cwd_present=True,proctitle_present=True,result=0,
        exe_base64='L2Jpbi94',comm_base64='eA==')
    def open_runtime():return Runtime(state,source,max_activations=4,max_pages=64,position_limit=32,storage=policy)
    try:
        runtime=open_runtime();runtime.activate(activation);runtime.claim();progress=runtime.progress
        progress.start_stream();progress.register('1.001:1',0,10,eoe=True);progress.accept('1.001:1',event)
        progress.register('1.001:2',10,20,eoe=True);positions=progress.positions()
        progress.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        original=runtime.storage.before;armed=[True];quota_errno=None
        def before(path):
            nonlocal quota_errno
            original(path)
            if armed[0]:
                armed[0]=False
                status=runtime.storage.observe(force=True);assert status['state']=='normal'
                send(outgoing,dict(stage='admitted',storage=status))
                assert receive(incoming)['command']=='quota_limited'
                try:os.posix_fallocate(filler,0,4096)
                except OSError as exc:quota_errno=exc.errno
                assert quota_errno==errno.EDQUOT,('not a real user quota failure',quota_errno)
        runtime.storage.before=before;failure=None
        try:progress.accept('1.001:2',event)
        except sqlite3.Error as exc:failure=exc.sqlite_errorcode
        finally:runtime.storage.before=original
        assert failure is not None and failure in (sqlite3.SQLITE_FULL,sqlite3.SQLITE_IOERR_WRITE)
        assert not progress.db.in_transaction and progress.positions()==positions
        assert progress.db.execute('SELECT identity FROM m3_execution').fetchall()==[('1.001:1',)]
        assert progress._state('1.001:2')=='open'
        status=runtime.storage.observe(force=True)
        assert status['state']=='normal' and status['available_bytes']>4*MIB
        send(outgoing,dict(stage='quota_failed',quota_errno=quota_errno,sqlite_errorcode=failure,
            storage=status,positions=positions,accepted=1))
        assert receive(incoming)['command']=='quota_released'
        runtime.close();runtime=open_runtime();current=runtime.current()
        assert current['state']=='interrupted' and current['code']=='backend_restart'
        history=runtime.open_progress(activation,current['generation'])
        try:
            assert history.db.execute('PRAGMA integrity_check').fetchone()==('ok',)
            assert history.db.execute('SELECT identity FROM m3_execution').fetchall()==[('1.001:1',)]
            assert history._state('1.001:2')=='interrupted'
            assert history.register('1.001:2',20,30,eoe=True)=='suppressed'
            assert not history.db.execute("SELECT 1 FROM m3_execution WHERE identity='1.001:2'").fetchone()
        finally:history.close()
        assert not runtime.status()['source_ready']
        send(outgoing,dict(stage='recovered',integrity='ok',accepted=1,interrupted=1,late_suppressed=True,source_ready=False))
    finally:
        if runtime:runtime.close()


def namespace(workspace,mount,parent_namespace,helper):
    assert os.getuid()==0 and os.readlink('/proc/self/ns/mnt')!=parent_namespace
    image=workspace/'filesystem.ext4';account=pwd.getpwnam('hids-ingest')
    command('mount','-o','loop,nodev,nosuid,noexec,usrquota',str(image),str(mount))
    child=None;filler=None
    try:
        device=command('findmnt','-n','-o','SOURCE','--target',str(mount))
        def quota(value):return json.loads(command(str(helper),str(image),str(mount),device,str(value)))
        initial=quota('get');assert initial['hard_blocks']==0 and initial['quota_uid']==account.pw_uid
        refusals=[]
        def refuse(label,other_image=image,other_mount=mount,other_device=device,value='1'):
            result=subprocess.run([str(helper),str(other_image),str(other_mount),str(other_device),value],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            assert result.returncode==65,(label,'unsafe helper request was not refused')
            assert quota('get')==initial,'refused request changed quota'
            refusals.append(label)
        refuse('non_loop_device',other_device='/dev/null')
        refuse('non_private_mount',other_mount='/run')
        refuse('non_private_image',other_image='/etc/audit/auditd.conf')
        refuse('oversized_limit',value='65537')
        # A separate zero-filled fixture cannot impersonate the mounted image.
        with tempfile.TemporaryDirectory(prefix='hids-m3-quota.guard.',dir='/root') as wrong:
            wrong_image=Path(wrong)/'filesystem.ext4'
            fd=os.open(wrong_image,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.ftruncate(fd,SIZE);os.close(fd)
            refuse('wrong_backing_inode',other_image=wrong_image)
        os.chown(mount,0,account.pw_gid);mount.chmod(0o710)
        state=mount/'state';state.mkdir(mode=0o700);os.chown(state,account.pw_uid,account.pw_gid)
        filler=os.open(mount/'quota-probe',os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
        os.fchown(filler,account.pw_uid,account.pw_gid)
        read_parent,write_child=os.pipe();read_child,write_parent=os.pipe();child=os.fork()
        if child==0:
            os.close(read_parent);os.close(write_parent);os.close(filler)
            os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
            filler=os.open(mount/'quota-probe',os.O_RDWR|os.O_NOFOLLOW)
            with os.fdopen(read_child) as incoming,os.fdopen(write_child,'w') as outgoing:
                try:writer(state,filler,incoming,outgoing)
                except BaseException:traceback.print_exc();sys.stderr.flush();os._exit(1)
            os._exit(0)
        os.close(read_child);os.close(write_child);evidence=[]
        with os.fdopen(read_parent) as incoming,os.fdopen(write_parent,'w') as outgoing:
            stage=receive(incoming);assert stage['stage']=='admitted';evidence.append(stage)
            limited=quota(1);assert limited['hard_blocks']==1 and limited['space_bytes']>1024
            send(outgoing,dict(command='quota_limited'))
            stage=receive(incoming);assert stage['stage']=='quota_failed';evidence.append(stage)
            assert available(mount)>4*MIB
            released=quota(0);assert released['hard_blocks']==0
            send(outgoing,dict(command='quota_released'))
            stage=receive(incoming);assert stage['stage']=='recovered';evidence.append(stage)
        _,status=os.waitpid(child,0);child=None;assert status==0
        os.close(filler);filler=None
        from m3_quota_service_ubuntu import run_case
        service_result=run_case(mount,image,device,helper)
        result=dict(result='passed',scope='private_ext4_actual_user_quota',image_bytes=SIZE,
            service=service_result,writer_uid=account.pw_uid,helper_refusals=refusals,initial_quota=initial,limited_quota=limited,released_quota=released,stages=evidence)
        output=workspace/'report.json';output.write_text(json.dumps(result,sort_keys=True)+'\n');output.chmod(0o600)
        print('PASS: actual UID quota returns EDQUOT with free space; SQLite failure rolls back; B survives; A is interrupted/suppressed after explicit recovery',flush=True)
    finally:
        if child:
            try:os.kill(child,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(child,0)
        if filler is not None:os.close(filler)
        command('umount',str(mount))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper',type=Path,required=True)
    parser.add_argument('--namespace',nargs=3)
    args=parser.parse_args();assert os.getuid()==0
    helper=args.helper.resolve();info=helper.stat()
    assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o700
    if args.namespace:
        namespace(Path(args.namespace[0]),Path(args.namespace[1]),args.namespace[2],helper);return
    workspace=Path(tempfile.mkdtemp(prefix='hids-m3-quota.',dir='/root'));workspace.chmod(0o700)
    mount=Path(tempfile.mkdtemp(prefix='hids-m3-quota.',dir='/run'));image=workspace/'filesystem.ext4'
    fd=os.open(image,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.ftruncate(fd,SIZE);os.close(fd)
    command('mkfs.ext4','-q','-F','-m','0','-O','quota','-E','lazy_itable_init=0,lazy_journal_init=0',str(image))
    original_namespace=os.readlink('/proc/self/ns/mnt')
    try:
        subprocess.run(['unshare','--mount','--propagation','private',sys.executable,'-B',str(Path(__file__).resolve()),
            '--helper',str(helper),'--namespace',str(workspace),str(mount),original_namespace],check=True,timeout=120)
    finally:
        assert os.readlink('/proc/self/ns/mnt')==original_namespace
        assert mount.stat().st_dev==mount.parent.stat().st_dev
        devices=command('losetup','--associated',str(image),'--noheadings','--output','NAME').splitlines()
        for device in devices:
            assert device.startswith('/dev/loop') and device[9:].isdigit();command('losetup','--detach',device)
        assert not command('losetup','--associated',str(image),'--noheadings','--output','NAME')
        mount.rmdir()
    output=workspace/'report.json';report=json.loads(output.read_text());report['cleanup']='verified'
    output.write_text(json.dumps(report,sort_keys=True)+'\n')
    print('Private quota mount/loop cleanup verified; retained image/report '+str(output),flush=True)


if __name__=='__main__':main()
