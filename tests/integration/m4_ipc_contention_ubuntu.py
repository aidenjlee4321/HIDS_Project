"""Bounded synthetic M4 contention beside installed M3 Service/real peer IPC.

No native Audit collection or production configuration/state changes. Retains all
private evidence. Run only as root on the authorized Ubuntu VM, from a snapshot.
"""
import argparse
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import resource
import select
import shutil
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests/integration')]
import dev
from m3_filesystem_ubuntu import receive,send,control_request

EVENT=dict(syscall=221,pid=42,ppid=1,uid=1000,euid=0,suid=0,fsuid=0,
    auid=None,session=None,path_count=1,success=True,cwd_present=True,proctitle_present=True,
    result=0,exe_base64='L3Vzci9iaW4vZGFzaA==',comm_base64='ZGFzaA==')


def backend(state,data,listener,incoming,outgoing):
    sys.path.insert(0,'/usr/lib/hids')
    from engine.ingestion.m3_runtime import Runtime
    from engine.ingestion.m3_service import Service,open_data_listener,PeerPolicy
    from engine.ingestion import m3_storage,m3_service
    assert Path(m3_service.__file__).is_relative_to('/usr/lib/hids')
    ingest=pwd.getpwnam('hids-ingest');reader=pwd.getpwnam('hids-audit');ipc=grp.getgrnam('hids-ipc').gr_gid
    runtime=Runtime(state,str(uuid.uuid4()),max_activations=4,max_pages=512,position_limit=1024,storage=m3_storage.defaults(512,4))
    endpoint=open_data_listener(data,ingest.pw_uid,ipc)
    service=Service(runtime,endpoint.sock,listener,PeerPolicy(reader.pw_uid,reader.pw_gid))
    try:
        send(outgoing,dict(stage='ready',source=runtime.source))
        while True:
            if select.select([incoming],[],[],0)[0]:
                request=receive(incoming)
                if request==dict(command='stop'):break
                assert request.get('command')=='checkpoint' and request.get('mode') in ('PASSIVE','TRUNCATE')
                result=runtime.progress.db.execute('PRAGMA wal_checkpoint('+request['mode']+')').fetchone()
                send(outgoing,dict(stage='checkpoint',mode=request['mode'],result=result));continue
            service.run_once()
    finally:service.close();runtime.close();endpoint.close()


def peer(data,scope,incoming,outgoing):
    sys.path.insert(0,'/usr/lib/hids')
    from engine.ingestion.m3_event import ARCH,PROFILE
    reader=pwd.getpwnam('hids-audit');ingest=pwd.getpwnam('hids-ingest');ipc=grp.getgrnam('hids-ipc').gr_gid
    os.setgroups([ipc]);os.setgid(reader.pw_gid);os.setuid(reader.pw_uid)
    with socket.socket(socket.AF_UNIX) as channel:
        channel.settimeout(5);channel.connect(str(data))
        _,uid,gid=struct.unpack('3i',channel.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        assert (uid,gid)==(ingest.pw_uid,ingest.pw_gid)
        def exchange(**value):
            channel.sendall(json.dumps(dict(version=3,**scope,**value)).encode()+b'\n');reply=b''
            while not reply.endswith(b'\n'):
                block=channel.recv(4096);assert block;reply+=block;assert len(reply)<=4096
            return json.loads(reply)
        assert exchange(op='boundary')['status']=='boundary'
        send(outgoing,dict(stage='connected'));number=0
        while True:
            request=receive(incoming)
            if request['command']=='stop':break
            assert request==dict(command='batch',count=4)
            latencies=[]
            for _ in range(4):
                number+=1;identity='1.001:'+str(number)
                assert exchange(op='register',identity=identity,begin=(number-1)*10,end=number*10,eoe=True)['status']=='admit'
                started=time.monotonic()
                assert exchange(op='accept',identity=identity,execution=EVENT,
                    observation=dict(version=1,arch=ARCH,profile=PROFILE,first_observed_unix_ns=123))['status']=='accepted'
                latencies.append((time.monotonic()-started)*1000)
            send(outgoing,dict(stage='accepted',total=number,accept_ack_ms=latencies,reader_uid=os.getuid()))


WORKER='''import sys,json,time,resource,os
from pathlib import Path
from engine.detection.m4_live import LiveSource
from engine.detection.m4_service import isolation_probe
from engine.detection.m4_rule_store import RuleStore
from engine.detection.m4_rules import REFERENCE,load_rules
from engine.detection.m4_handoff import Worker
scope=json.loads(sys.argv[1]);source=LiveSource(Path('/var/lib/hids/m3'),**scope)
probe=isolation_probe(source)
with RuleStore(create=not Path('/var/lib/hids/m4/store').exists()) as store:
 rules=load_rules([REFERENCE]);store.select_evaluations(source,rules)
 print(json.dumps(dict(stage='ready',isolation=probe,uid=os.getuid(),groups=os.getgroups())),flush=True)
 assert json.loads(input())==dict(command='step')
 if sys.argv[2]=='destination_locked':
  attempted=[False]
  def trace(sql):
   if sql.strip().upper()=='BEGIN IMMEDIATE' and not attempted[0]:
    attempted[0]=True;print(json.dumps(dict(stage='write_attempt')),flush=True)
  store.db.set_trace_callback(trace)
 before=resource.getrusage(resource.RUSAGE_SELF);started=time.monotonic()
 result=Worker(store,[source],rules).step()
 after=resource.getrusage(resource.RUSAGE_SELF)
 print(json.dumps(dict(stage='done',status=result,seconds=time.monotonic()-started,
 cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,max_rss_kib=after.ru_maxrss)),flush=True)
'''
CONTINUOUS='''import json,time,resource
from engine.detection.m4_service import run
before=resource.getrusage(resource.RUSAGE_SELF);started=time.monotonic()
status,code=run()
after=resource.getrusage(resource.RUSAGE_SELF)
print(json.dumps(dict(stage='done',status=status,seconds=time.monotonic()-started,
 cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,max_rss_kib=after.ru_maxrss)),flush=True)
raise SystemExit(code)
'''
HOLDER='''import sys,json,sqlite3
from pathlib import Path
mode=sys.argv[1];p=Path(sys.argv[2]);db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,isolation_level=None) if mode=='reader' else sqlite3.connect(p,isolation_level=None)
try:
 db.execute('BEGIN' if mode=='reader' else 'BEGIN IMMEDIATE')
 count=db.execute('SELECT count(*) FROM m3_execution').fetchone()[0] if mode=='reader' else None
 print(json.dumps(dict(stage='held',count=count)),flush=True)
 assert json.loads(input())==dict(command='release')
 if mode=='reader':assert db.execute('SELECT count(*) FROM m3_execution').fetchone()[0]==count
finally:db.close()
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expected-manifest',required=True)
    parser.add_argument('--expected-vm-uuid',required=True,help='Exact previously verified guest UUID; refuses any other VM before setup')
    parser.add_argument('--polling',action='store_true',help='Bounded continuous idle/burst scope: 16 synthetic IPC events and three ten-second windows')
    args=parser.parse_args()
    assert sys.platform=='linux' and os.getuid()==0
    expected=str(uuid.UUID(args.expected_vm_uuid))
    if Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()!=expected:
        raise RuntimeError('VM identity differs; no experiment started')
    dev.verify(ROOT,args.expected_manifest)
    units=('hids-m3.service','hids-m3.socket','hids-m3-health.service','hids-m3-health.timer')
    def output(*argv):return subprocess.check_output(argv,text=True,timeout=20)
    assert all(output('systemctl','show',u,'-p','ActiveState','--value').strip()=='inactive' for u in units)
    assert output('systemctl','is-active','auditd').strip()=='active'
    lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def preserved():
        paths=[*Path('/var/lib/hids/m3').glob('*.sqlite'),*Path('/var/lib/hids/m4').rglob('*.sqlite'),Path('/etc/hids/m3.json'),Path('/etc/audit/auditd.conf'),*Path('/etc/audit/plugins.d').glob('*.conf')]
        return dict(files={str(p):sha(p) for p in paths},rules=output('auditctl','-l'))
    baseline=preserved();account=pwd.getpwnam('hids-ingest');ipc=grp.getgrnam('hids-ipc').gr_gid
    root=Path(tempfile.mkdtemp(prefix='hids-m4-ipc.',dir='/var/tmp'));root.chmod(0o711)
    report=dict(result='running',lab_only=True,source_manifest=args.expected_manifest,vm_uuid=expected,phases=[],root=str(root))
    children=[];streams=[];logs=[];processes=[];unit=None
    def save():
        p=root/'report.json';p.write_text(json.dumps(report,sort_keys=True)+'\n');p.chmod(0o600)
    def interrupted(*_):raise InterruptedError('bounded IPC trial interrupted')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
    def fork_child(function,drop=False):
        rp,wc=os.pipe();rc,wp=os.pipe();child=os.fork()
        if child==0:
            os.close(rp);os.close(wp)
            for stream in streams:stream.close()
            if not drop:listener.close()
            if drop:os.setgroups([ipc]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
            with os.fdopen(rc) as incoming,os.fdopen(wc,'w') as outgoing:
                try:function(incoming,outgoing)
                except BaseException:traceback.print_exc();sys.stderr.flush();os._exit(1)
            os._exit(0)
        children.append(child);os.close(rc);os.close(wc)
        incoming,outgoing=os.fdopen(rp),os.fdopen(wp,'w');streams.extend((incoming,outgoing));return child,incoming,outgoing
    def query(path,sql):
        uid,gid=os.geteuid(),os.getegid()
        try:
            os.setegid(account.pw_gid);os.seteuid(account.pw_uid)
            db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            try:return db.execute(sql).fetchall()
            finally:db.close()
        finally:os.seteuid(uid);os.setegid(gid)
    def log(name):
        p=root/name;f=p.open('x');p.chmod(0o600);logs.append(f);return f
    def finish(p):
        p.wait(timeout=15);assert p.returncode==0;p.stdin.close();p.stdout.close();processes.remove(p)
    try:
        code=root/ROOT.name;shutil.copytree(ROOT,code)
        for parent,dirs,files in os.walk(code):
            Path(parent).chmod(0o755)
            for name in files:(Path(parent)/name).chmod(0o644)
        dev.verify(code,args.expected_manifest)
        for name in ('source','state'):
            p=root/name;p.mkdir(mode=0o700);os.chown(p,account.pw_uid,account.pw_gid)
        control=root/'control';control.mkdir(mode=0o700)
        data=root/'ipc';data.mkdir(mode=0o750);os.chown(data,account.pw_uid,ipc)
        listener=socket.socket(socket.AF_UNIX);listener.bind(str(control/'control.sock'));(control/'control.sock').chmod(0o600);listener.listen(4)
        server,server_in,server_out=fork_child(lambda i,o:backend(root/'source',data/'data.sock',listener,i,o),True)
        ready=receive(server_in);assert ready['stage']=='ready'
        source=ready['source'];activation=str(uuid.uuid4())
        def rpc(**value):return control_request(control/'control.sock',dict(version=3,**value))
        assert rpc(command='activate',source=source,activation=activation)['result']=='activated'
        lease=rpc(command='lease')['scope'];scope=dict(source=source,activation=lease['activation'],generation=lease['generation'])
        client,client_in,client_out=fork_child(lambda i,o:peer(data/'data.sock',lease,i,o));assert receive(client_in)['stage']=='connected'
        destination=root/'state'/'store'/'handoff.sqlite';ledger=root/'source'/(activation+'.sqlite')
        def holder(mode,path):
            p=subprocess.Popen([sys.executable,'-B','-c',HOLDER,mode,str(path)],user=account.pw_uid,group=account.pw_gid,extra_groups=[],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log(mode+'-'+uuid.uuid4().hex+'.stderr'),text=True)
            processes.append(p);ready=receive(p.stdout);assert ready['stage']=='held';return p,ready
        if args.polling:
            constants=json.loads(subprocess.check_output([sys.executable,'-B','-c',
                'import json;from engine.detection.m4_live import POLICY;from engine.detection.m4_rules import REFERENCE;print(json.dumps(dict(policy=POLICY,reference=REFERENCE)))'],
                cwd=code,env={**os.environ,'PYTHONPATH':str(code)},text=True,timeout=10))
            POLICY,REFERENCE=constants['policy'],constants['reference']
            selected=root/'selected-config';selected.mkdir(mode=0o750);os.chown(selected,0,account.pw_gid)
            config=selected/'m4.json'
            config.write_text(json.dumps(dict(version=2,enabled=True,**scope,max_pages=512,storage=POLICY,max_events=16,max_seconds=60,rules=[REFERENCE])))
            os.chown(config,0,account.pw_gid);config.chmod(0o640)
            samples=[];batches=[];held=None
            def start_continuous(label):
                nonlocal unit
                unit='hids-m4-ipc-'+uuid.uuid4().hex[:12]
                properties=dict(User='hids-ingest',Group='hids-ingest',SupplementaryGroups='',WorkingDirectory=str(code),UMask='0077',NoNewPrivileges='yes',
                    CapabilityBoundingSet='',AmbientCapabilities='',ProtectSystem='strict',ProtectHome='yes',PrivateDevices='yes',ProtectKernelTunables='yes',
                    ProtectKernelModules='yes',ProtectControlGroups='yes',RestrictSUIDSGID='yes',RestrictAddressFamilies='AF_UNIX',LimitCORE='0',
                    BindReadOnlyPaths=str(root/'source')+':/var/lib/hids/m3 '+str(selected)+':/etc/hids',BindPaths=str(root/'state')+':/var/lib/hids/m4',
                    ReadOnlyPaths='/var/lib/hids/m3',ReadWritePaths='/var/lib/hids/m4',InaccessiblePaths='/run/hids/m3',
                    CPUAccounting='yes',MemoryAccounting='yes',IOAccounting='yes',RuntimeMaxSec='70')
                argv=['systemd-run','--quiet','--wait','--collect','--pipe','--unit',unit]
                for k,v in properties.items():argv+=['-p',k+'='+v]
                argv+=[sys.executable,'-B','-c',CONTINUOUS]
                worker=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log('polling-'+label+'.stderr'),text=True)
                processes.append(worker);return worker
            def imported(count):
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    try:
                        if destination.exists() and query(destination,'SELECT count(*) FROM m4h_events')==[(count,)]:return
                    except sqlite3.OperationalError:pass  # Bounded startup/WAL initialization race.
                    if worker.poll() is not None:raise RuntimeError('continuous worker exited before expected count')
                    time.sleep(.1)
                raise TimeoutError('continuous worker did not import expected count')
            def sample(label):
                raw=output('systemctl','show',unit,'-p','CPUUsageNSec','-p','MemoryCurrent','-p','MemoryPeak','-p','IOReadBytes','-p','IOWriteBytes')
                values={}
                for line in raw.splitlines():
                    key,value=line.split('=',1);values[key]=int(value) if value.isdecimal() and int(value)<2**63 else None
                sizes={}
                for name,directory in (('source',root/'source'),('destination',root/'state')):
                    sizes[name]=sum(x.stat().st_size for x in directory.rglob('*') if x.is_file())
                values.update(stage=label,monotonic=time.monotonic(),state_bytes=sizes,source_wal_bytes=Path(str(ledger)+'-wal').stat().st_size)
                samples.append(values);report['polling_samples']=samples;save();return values
            def batch(expected):
                send(client_out,dict(command='batch',count=4));accepted=receive(client_in);assert accepted['total']==expected
                assert query(ledger,'SELECT count(*) FROM m3_execution')==[(expected,)]
                batches.append(accepted);report['polling_batches']=batches;save()
            worker=start_continuous('main');imported(0)
            sample('idle_start');time.sleep(10);sample('idle_end')
            batch(4);imported(4)
            held,held_info=holder('reader',ledger);assert held_info['count']==4
            batch(8);imported(8)
            sample('held_reader_start');time.sleep(10);sample('held_reader_middle')
            batch(12);imported(12)
            time.sleep(10);sample('held_reader_end')
            send(server_out,dict(command='checkpoint',mode='PASSIVE'));checkpoint=receive(server_in)
            assert checkpoint['stage']=='checkpoint' and checkpoint['result'][1]>checkpoint['result'][2]
            report['checkpoint_while_held']=checkpoint;save()
            send(held.stdin,dict(command='release'));finish(held)
            send(server_out,dict(command='checkpoint',mode='TRUNCATE'));checkpoint=receive(server_in)
            assert checkpoint==dict(stage='checkpoint',mode='TRUNCATE',result=[0,0,0])
            assert Path(str(ledger)+'-wal').stat().st_size==0
            report['checkpoint_after_release']=checkpoint;sample('reader_released')
            batch(16)
            result=receive(worker.stdout);assert result['stage']=='done' and result['status']['completed'] and result['status']['selected_events']==16
            assert result['status']['events']==result['status']['alerts']==16 and result['status']['pending']==0
            finish(worker);unit=None;report['continuous_result']=result;save()
            worker=start_continuous('restart');retry=receive(worker.stdout);finish(worker);unit=None
            assert retry['status']['events']==retry['status']['alerts']==16 and retry['status']['reason']=='event_limit'
            assert query(destination,'PRAGMA integrity_check')==[('ok',)] and query(destination,'PRAGMA foreign_key_check')==[]
            assert query(ledger,'PRAGMA integrity_check')==[('ok',)]
            health=rpc(command='status');assert health['failure'] is None and health['source_ready'] and health['reader_connected']
            report.update(polling=True,source_snapshot_count=4,synthetic_events=16,restart_idempotent=True,source_ready=True)
        else:
            for index,name in enumerate(('baseline','destination_locked','source_snapshot','recovered')):
                held=None;held_info=None
                if name=='source_snapshot':held,held_info=holder('reader',ledger)
                unit='hids-m4-ipc-'+uuid.uuid4().hex[:12]
                properties=dict(User='hids-ingest',Group='hids-ingest',SupplementaryGroups='',WorkingDirectory=str(code),UMask='0077',NoNewPrivileges='yes',
                    CapabilityBoundingSet='',AmbientCapabilities='',ProtectSystem='strict',ProtectHome='yes',PrivateDevices='yes',ProtectKernelTunables='yes',
                    ProtectKernelModules='yes',ProtectControlGroups='yes',RestrictSUIDSGID='yes',RestrictAddressFamilies='AF_UNIX',LimitCORE='0',
                    BindReadOnlyPaths=str(root/'source')+':/var/lib/hids/m3',BindPaths=str(root/'state')+':/var/lib/hids/m4',
                    ReadOnlyPaths='/var/lib/hids/m3',ReadWritePaths='/var/lib/hids/m4',InaccessiblePaths='/run/hids/m3')
                argv=['systemd-run','--quiet','--wait','--collect','--pipe','--unit',unit]
                for k,v in properties.items():argv+=['-p',k+'='+v]
                argv+=[sys.executable,'-B','-c',WORKER,json.dumps(scope),name]
                worker=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log('worker-'+name+'.stderr'),text=True)
                processes.append(worker);ready=receive(worker.stdout)
                report['last_worker_identity']=ready;save()
                assert ready['stage']=='ready' and ready['uid']==account.pw_uid and set(ready['groups'])<={account.pw_gid} and ipc not in ready['groups'] and all(ready['isolation'].values())
                if name=='destination_locked':held,held_info=holder('writer',destination)
                if name=='destination_locked':
                    send(worker.stdin,dict(command='step'));assert receive(worker.stdout)==dict(stage='write_attempt')
                wal=Path(str(ledger)+'-wal');wal_before=wal.stat().st_size
                send(client_out,dict(command='batch',count=4));accepted=receive(client_in);assert accepted['total']==4*(index+1)
                assert query(ledger,'SELECT count(*) FROM m3_execution')==[(accepted['total'],)]
                wal_after=wal.stat().st_size
                if name!='destination_locked':send(worker.stdin,dict(command='step'))
                result=receive(worker.stdout);assert result['stage']=='done';finish(worker);unit=None
                if held:send(held.stdin,dict(command='release'));finish(held)
                expected=4 if name=='destination_locked' else accepted['total']
                assert result['status']['events']==expected and result['status']['alerts']==expected
                if name=='destination_locked':assert set(result['status']['bindings'].values())=={'source_or_destination_unavailable'}
                else:assert set(result['status']['bindings'].values())=={'imported'}
                health=rpc(command='status');assert health['failure'] is None and health['source_ready'] and health['reader_connected']
                assert query(destination,'PRAGMA integrity_check')==[('ok',)] and query(destination,'PRAGMA foreign_key_check')==[]
                report['phases'].append(dict(name=name,accepted=accepted['total'],accept_ack_ms=accepted['accept_ack_ms'],m4=result,
                    source_wal_bytes_before=wal_before,source_wal_bytes_after=wal_after,pinned_reader=held_info,source_ready=True,m4_write_attempt_before_batch=name=='destination_locked'));save()
        send(client_out,dict(command='stop'));_,status=os.waitpid(client,0);children.remove(client);assert status==0
        send(server_out,dict(command='stop'));_,status=os.waitpid(server,0);children.remove(server);assert status==0
        dev.verify(code,args.expected_manifest);report.update(result='passed',accepted=16,findings=16,installed_m3=True,actual_peer_credentials=True)
    finally:
        for p in processes:
            if p.poll() is None:p.kill();p.wait(timeout=15)
            if p.stdin:p.stdin.close()
            if p.stdout:p.stdout.close()
        if unit:subprocess.run(['systemctl','stop',unit],capture_output=True,timeout=20)
        for child in children:
            try:os.kill(child,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(child,0)
        for stream in streams:stream.close()
        for f in logs:f.close()
        if 'listener' in locals():listener.close()
        report['production_preserved']=preserved()==baseline
        report['original_units_inactive']=all(output('systemctl','show',u,'-p','ActiveState','--value').strip()=='inactive' for u in units)
        if report['result']!='passed' or not report['production_preserved'] or not report['original_units_inactive']:report['result']='failed'
        save();os.close(lock)
        print(json.dumps(dict(result=report['result'],report=str(root/'report.json'),production_preserved=report['production_preserved']),sort_keys=True),flush=True)
    assert report['result']=='passed'


if __name__=='__main__':main()
