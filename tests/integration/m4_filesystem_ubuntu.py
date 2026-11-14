"""Fenced ext4 M4 capacity/race-full/readonly acceptance with synthetic data.

No production filesystem is filled/remounted. Image and reports are retained.
Normal approved M4 admission budgets remain unchanged.
"""
import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests/integration')]
import dev
from m3_filesystem_ubuntu import receive,send

MIB=1024**2
SIZE=1536*MIB


def command(*argv):return subprocess.check_output(argv,stderr=subprocess.PIPE,text=True,timeout=30).strip()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def available(path):
    s=os.statvfs(path);return s.f_bavail*s.f_frsize


def producer(directory,incoming,outgoing):
    from engine.ingestion.m3_runtime import Runtime
    from engine.ingestion.m3_event import ARCH,PROFILE
    from engine.ingestion import m3_storage
    from engine.detection.m4_pilot import load_json
    scope=dict(source=str(uuid.uuid4()),activation=str(uuid.uuid4()))
    runtime=Runtime(directory,scope['source'],max_activations=4,max_pages=512,position_limit=1024,storage=m3_storage.defaults(512,4))
    try:
        scope['generation']=runtime.activate(scope['activation'])['generation']
        event=load_json(ROOT/'tests/fixtures/m4/execution.json')['execution']
        event.update(euid=0,exe_base64='L3Vzci9iaW4vZGFzaA==')
        for n in range(1,4):
            identity='1.001:'+str(n);runtime.progress.register(identity,(n-1)*10,n*10,eoe=True)
            runtime.progress.accept(identity,event,observation=dict(version=1,arch=ARCH,profile=PROFILE,first_observed_unix_ns=123))
        send(outgoing,dict(stage='source_ready',scope=scope))
        assert receive(incoming)==dict(command='stop')
    finally:runtime.close()


def worker(scope,incoming,outgoing):
    from engine.detection.m4_live import LiveSource
    from engine.detection.m4_rule_store import RuleStore
    from engine.detection.m4_rules import load_rules,REFERENCE
    from engine.detection.m4_service import isolation_probe
    from engine.detection.m4_migrate import snapshot
    from engine.ingestion.m3_storage import StoragePressure
    account=pwd.getpwnam('hids-ingest')
    assert os.getresuid()==(account.pw_uid,)*3 and os.getgroups()==[]
    caps={line.split(':')[0]:int(line.split()[1],16) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('CapEff:','CapPrm:','CapInh:'))}
    assert not any(caps.values())
    source=LiveSource(Path('/var/lib/hids/m3'),**scope);rules=load_rules([REFERENCE])
    probe=isolation_probe(source);assert all(probe.values())
    assert Path('/var/lib/hids/m3').stat().st_dev!=Path('/var/lib/hids/m4').stat().st_dev
    store=None
    def saved():
        return dict(rows=snapshot(store.db),plans=store.db.execute('SELECT binding_key,rule_plan FROM m4h_bindings ORDER BY binding_key').fetchall())
    def check(count):
        value=store.summary();assert value['events']==value['alerts']==count and value['pending']==0
        assert store.db.execute('PRAGMA integrity_check').fetchone()==('ok',)
        assert store.db.execute('PRAGMA foreign_key_check').fetchall()==[]
        return value
    try:
        store=RuleStore(create=True);store.select_evaluations(source,rules)
        store.import_page(source,rules,limit=1);store.evaluate_pending();original=saved()
        send(outgoing,dict(stage='initial',summary=check(1),isolation=probe,capabilities=caps))
        assert receive(incoming)==dict(command='pressure')
        pressure=store.guard.observe(store.path,force=True);assert pressure['state']=='critical'
        try:store.import_page(source,rules,limit=1)
        except StoragePressure:pass
        else:raise AssertionError('critical real free space admitted M4 write')
        assert saved()==original
        send(outgoing,dict(stage='pressure_blocked',storage=pressure,summary=check(1)))
        assert receive(incoming)==dict(command='release')
        assert store.guard.observe(store.path,force=True)['state']=='normal'
        store.import_page(source,rules,limit=1);store.evaluate_pending();original=saved();assert check(2)['events']==2
        before=store.guard.before;armed=[True]
        def raced(path):
            before(path)
            if armed[0]:
                armed[0]=False;normal=store.guard.observe(store.path,force=True);assert normal['state']=='normal'
                send(outgoing,dict(stage='admitted_before_fill',storage=normal))
                assert receive(incoming)==dict(command='filled')
        store.guard.before=raced;failure=None
        try:store.import_page(source,rules,limit=1)
        except sqlite3.Error as exc:failure=dict(code=exc.sqlite_errorcode,name=exc.sqlite_errorname)
        finally:store.guard.before=before
        assert failure and failure['code'] in (sqlite3.SQLITE_FULL,sqlite3.SQLITE_IOERR_WRITE),failure
        assert not store.db.in_transaction and saved()==original
        assert len(source.read_page()[0])==3  # Source is independent and still committed.
        send(outgoing,dict(stage='sqlite_full',failure=failure,storage=store.guard.observe(store.path,force=True),summary=check(2)))
        assert receive(incoming)==dict(command='recover')
        store.close();store=RuleStore();store.select_evaluations(source,rules)
        store.import_page(source,rules,limit=1);original=saved()
        assert store.summary()['pending']==1 and store.summary()['events']==3 and store.summary()['alerts']==2
        before=store.guard.before;armed=[True]
        def evaluation_race(path):
            before(path)
            if armed[0]:
                armed[0]=False;normal=store.guard.observe(store.path,force=True);assert normal['state']=='normal'
                send(outgoing,dict(stage='evaluation_admitted_before_fill',storage=normal))
                assert receive(incoming)==dict(command='filled')
        store.guard.before=evaluation_race;failure=None
        try:store.evaluate_pending()
        except sqlite3.Error as exc:failure=dict(code=exc.sqlite_errorcode,name=exc.sqlite_errorname)
        finally:store.guard.before=before
        assert failure and failure['code'] in (sqlite3.SQLITE_FULL,sqlite3.SQLITE_IOERR_WRITE),failure
        assert not store.db.in_transaction and saved()==original
        summary=store.summary();assert summary['events']==3 and summary['pending']==1 and summary['alerts']==2
        send(outgoing,dict(stage='evaluation_sqlite_full',failure=failure,summary=summary))
        assert receive(incoming)==dict(command='recover')
        store.close();store=RuleStore();store.select_evaluations(source,rules)
        store.evaluate_pending();store.evaluate_pending();summary=check(3)
        store.import_page(source,rules,limit=1);store.evaluate_pending();summary=check(3)
        store.close();store=None
        path=Path('/var/lib/hids/m4/store/handoff.sqlite');before_bytes=sha(path)
        before_names=sorted(x.name for x in path.parent.iterdir())
        send(outgoing,dict(stage='closed_for_readonly',summary=summary))
        assert receive(incoming)==dict(command='readonly')
        assert os.statvfs(path.parent).f_flag & os.ST_RDONLY
        try:store=RuleStore()
        except OSError as exc:assert exc.errno==errno.EROFS;refusal=exc.errno
        else:raise AssertionError('read-only destination admitted writer startup')
        assert sha(path)==before_bytes and sorted(x.name for x in path.parent.iterdir())==before_names
        send(outgoing,dict(stage='readonly_refused',errno=refusal,main_bytes_unchanged=True,files_unchanged=True))
        assert receive(incoming)==dict(command='writable')
        store=RuleStore();store.select_evaluations(source,rules)
        store.import_page(source,rules,limit=1);store.evaluate_pending()
        send(outgoing,dict(stage='recovered',summary=check(3)))
    finally:
        if store:store.close()


def fill(fd,mount,target,host_device):
    s=os.fstat(fd)
    assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_dev==mount.stat().st_dev!=host_device
    started=time.monotonic();chunk=MIB
    while available(mount)>target:
        assert time.monotonic()-started<30,'bounded filler deadline'
        amount=min(chunk,(available(mount)-target)//4096*4096)
        if not amount:break
        size=os.fstat(fd).st_size;assert size+amount<=SIZE
        try:os.posix_fallocate(fd,size,amount)
        except OSError as exc:
            if exc.errno!=errno.ENOSPC:raise
            if amount<=4096:break
            chunk=max(4096,amount//2//4096*4096)
    os.fsync(fd);return available(mount)


def namespace(workspace,mount,parent_namespace):
    current_namespace=os.readlink('/proc/self/ns/mnt')
    if current_namespace==parent_namespace or current_namespace==os.readlink('/proc/1/ns/mnt'):
        raise RuntimeError('private mount namespace required; no mount attempted')
    if (workspace.parent!=Path('/var/tmp') or not workspace.name.startswith('hids-m4-filesystem.') or
        workspace.resolve()!=workspace or workspace.stat().st_uid!=0 or mount!=workspace/'mount' or mount.resolve()!=mount):
        raise RuntimeError('private workspace fence refused')
    image=workspace/'filesystem.ext4';info=dev.regular(image)
    if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size!=SIZE:
        raise RuntimeError('private image fence refused')
    account=pwd.getpwnam('hids-ingest');children=[];streams=[];mounted=[];filler=None
    report=dict(result='running',scope='synthetic_m4_private_ext4',image_bytes=SIZE,stages=[])
    def save():
        p=workspace/'report.json';p.write_text(json.dumps(report,sort_keys=True)+'\n');p.chmod(0o600)
    def fork_child(function):
        rp,wc=os.pipe();rc,wp=os.pipe();parent_pid=os.getpid();child=os.fork()
        if child==0:
            os.close(rp);os.close(wp)
            if filler is not None:os.close(filler)
            for f in streams:f.close()
            os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
            # Credential changes clear this flag; arm it only after dropping UID.
            if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGKILL,0,0,0)!=0:os._exit(1)
            if os.getppid()!=parent_pid:os._exit(1)
            with os.fdopen(rc) as incoming,os.fdopen(wc,'w') as outgoing:
                try:function(incoming,outgoing)
                except BaseException:traceback.print_exc();sys.stderr.flush();os._exit(1)
            os._exit(0)
        children.append(child);os.close(rc);os.close(wc)
        incoming,outgoing=os.fdopen(rp),os.fdopen(wp,'w');streams.extend((incoming,outgoing));return child,incoming,outgoing
    def item(stream,stage):
        value=receive(stream);assert value['stage']==stage,value
        report['stages'].append(value);save();return value
    try:
        command('mount','-o','loop,nodev,nosuid,noexec',str(image),str(mount));mounted.append(mount)
        device=command('findmnt','-n','-o','SOURCE','--target',str(mount))
        assert device in command('losetup','--associated',str(image),'--noheadings','--output','NAME').splitlines()
        assert device.startswith('/dev/loop') and device[9:].isdigit()
        mount.chmod(0o711)
        state=mount/'state';state.mkdir(mode=0o700);os.chown(state,account.pw_uid,account.pw_gid)
        source=workspace/'source';source.mkdir(mode=0o700);os.chown(source,account.pw_uid,account.pw_gid)
        prod,prod_in,prod_out=fork_child(lambda i,o:producer(source,i,o));scope=item(prod_in,'source_ready')['scope']
        for origin,target in ((source,Path('/var/lib/hids/m3')),(state,Path('/var/lib/hids/m4'))):
            assert target.is_dir();command('mount','--bind',str(origin),str(target));mounted.append(target)
        command('mount','-o','remount,bind,ro','/var/lib/hids/m3')
        blocked=workspace/'blocked';blocked.mkdir(mode=0o000)
        assert Path('/run/hids/m3').is_dir();command('mount','--bind',str(blocked),'/run/hids/m3');mounted.append(Path('/run/hids/m3'))
        filler=os.open(mount/'filler',os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
        process,incoming,outgoing=fork_child(lambda i,o:worker(scope,i,o));item(incoming,'initial')
        free=fill(filler,mount,400*MIB,workspace.stat().st_dev);assert 399*MIB<=free<=401*MIB
        send(outgoing,dict(command='pressure'));item(incoming,'pressure_blocked')
        os.ftruncate(filler,0);os.fsync(filler);send(outgoing,dict(command='release'));item(incoming,'admitted_before_fill')
        free=fill(filler,mount,0,workspace.stat().st_dev);assert free<4096,free
        report['full_available_bytes']=free;save();send(outgoing,dict(command='filled'));item(incoming,'sqlite_full')
        os.ftruncate(filler,0);os.fsync(filler);send(outgoing,dict(command='recover'));item(incoming,'evaluation_admitted_before_fill')
        free=fill(filler,mount,0,workspace.stat().st_dev);assert free<4096,free
        report['evaluation_full_available_bytes']=free;save();send(outgoing,dict(command='filled'));item(incoming,'evaluation_sqlite_full')
        os.ftruncate(filler,0);os.fsync(filler);send(outgoing,dict(command='recover'));item(incoming,'closed_for_readonly')
        os.close(filler);filler=None
        command('mount','-o','remount,ro',str(mount));command('mount','-o','remount,bind,ro','/var/lib/hids/m4')
        send(outgoing,dict(command='readonly'));item(incoming,'readonly_refused')
        command('mount','-o','remount,rw',str(mount));command('mount','-o','remount,bind,rw','/var/lib/hids/m4')
        send(outgoing,dict(command='writable'));item(incoming,'recovered')
        _,status=os.waitpid(process,0);children.remove(process);assert status==0
        send(prod_out,dict(command='stop'));_,status=os.waitpid(prod,0);children.remove(prod);assert status==0
        report.update(result='passed',normal_m4_budgets=True,private_namespace=True,source_independent=True,final_events=3,final_findings=3)
    finally:
        if filler is not None:os.close(filler)
        for child in children:
            try:os.kill(child,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(child,0)
        for f in streams:f.close()
        for target in reversed(mounted):command('umount',str(target))
        report['mounts_released']=True;save()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expected-manifest',required=True);parser.add_argument('--expected-vm-uuid',required=True)
    parser.add_argument('--namespace',nargs=3);args=parser.parse_args()
    assert sys.platform=='linux' and os.getuid()==0
    expected=str(uuid.UUID(args.expected_vm_uuid))
    if Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()!=expected:raise RuntimeError('VM identity differs; no experiment started')
    dev.verify(ROOT,args.expected_manifest)
    if args.namespace:namespace(Path(args.namespace[0]),Path(args.namespace[1]),args.namespace[2]);return
    units=('hids-m3.service','hids-m3.socket','hids-m3-health.service','hids-m3-health.timer')
    assert all(command('systemctl','show',u,'-p','ActiveState','--value')=='inactive' for u in units)
    assert command('systemctl','is-active','auditd')=='active'
    lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def preserved():
        paths=[*Path('/var/lib/hids/m3').glob('*.sqlite'),*Path('/var/lib/hids/m4').rglob('*.sqlite'),Path('/etc/hids/m3.json'),Path('/etc/audit/auditd.conf'),*Path('/etc/audit/plugins.d').glob('*.conf')]
        return dict(files={str(p):sha(p) for p in paths},rules=command('auditctl','-l'))
    baseline=preserved();assert available(Path('/var/tmp'))>SIZE+2048*MIB,'insufficient host reserve for private image'
    workspace=Path(tempfile.mkdtemp(prefix='hids-m4-filesystem.',dir='/var/tmp'));workspace.chmod(0o711)
    code=workspace/ROOT.name;shutil.copytree(ROOT,code)
    for parent,dirs,files in os.walk(code):
        Path(parent).chmod(0o755)
        for name in files:(Path(parent)/name).chmod(0o644)
    dev.verify(code,args.expected_manifest)
    image=workspace/'filesystem.ext4';fd=os.open(image,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.ftruncate(fd,SIZE);os.close(fd)
    command('mkfs.ext4','-q','-F','-m','0','-E','lazy_itable_init=0,lazy_journal_init=0',str(image))
    mount=workspace/'mount';mount.mkdir(mode=0o700);parent_namespace=os.readlink('/proc/self/ns/mnt');result=None
    try:
        result=subprocess.run(['unshare','--mount','--propagation','private',sys.executable,'-B',str(code/'tests/integration/m4_filesystem_ubuntu.py'),
            '--expected-manifest',args.expected_manifest,'--expected-vm-uuid',expected,'--namespace',str(workspace),str(mount),parent_namespace],timeout=120)
    finally:
        assert os.readlink('/proc/self/ns/mnt')==parent_namespace and mount.stat().st_dev==workspace.stat().st_dev
        devices=command('losetup','--associated',str(image),'--noheadings','--output','NAME').splitlines()
        for device in devices:
            assert device.startswith('/dev/loop') and device[9:].isdigit();command('losetup','--detach',device)
        assert not command('losetup','--associated',str(image),'--noheadings','--output','NAME')
        report=json.loads((workspace/'report.json').read_text()) if (workspace/'report.json').exists() else dict(result='failed',stages=[])
        report.update(vm_uuid=expected,source_manifest=args.expected_manifest,cleanup='verified',production_preserved=preserved()==baseline,
            original_units_inactive=all(command('systemctl','show',u,'-p','ActiveState','--value')=='inactive' for u in units))
        if result is None or result.returncode!=0 or not report['production_preserved'] or not report['original_units_inactive']:report['result']='failed'
        p=workspace/'report.json';p.write_text(json.dumps(report,sort_keys=True)+'\n');p.chmod(0o600);os.close(lock)
        print(json.dumps(dict(result=report['result'],report=str(p),cleanup=report['cleanup'],production_preserved=report['production_preserved'])),flush=True)
    assert report['result']=='passed'


if __name__=='__main__':main()
