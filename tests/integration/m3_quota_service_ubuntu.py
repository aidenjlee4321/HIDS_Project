"""Private-image actual Service/peer IPC quota failure. Called by quota harness."""
import grp
import json
import os
from pathlib import Path
import pwd
import select
import signal
import socket
import sqlite3
import struct
import sys
import tempfile
import traceback
import uuid
from m3_filesystem_ubuntu import command,receive,send,control_request,MIB

EVENT=dict(syscall=221,pid=42,ppid=1,uid=1000,euid=1000,suid=1000,fsuid=1000,
    auid=None,session=7,path_count=1,success=True,cwd_present=True,proctitle_present=True,
    result=0,exe_base64='L2Jpbi94',comm_base64='eA==')


def backend(state,data,listener,incoming,outgoing):
    sys.path.insert(0,'/usr/lib/hids')
    from engine.ingestion.m3_runtime import Runtime
    from engine.ingestion.m3_service import Service,open_data_listener,PeerPolicy
    from engine.ingestion import m3_storage
    ingest=pwd.getpwnam('hids-ingest');reader=pwd.getpwnam('hids-audit');ipc=grp.getgrnam('hids-ipc').gr_gid
    policy=m3_storage.defaults(64,4);policy.update(warning_free_bytes=4*MIB,critical_free_bytes=2*MIB,minimum_free_bytes=MIB)
    source=str(uuid.uuid4());runtime=None;endpoint=None;service=None
    def open_runtime():return Runtime(state,source,max_activations=4,max_pages=64,position_limit=32,storage=policy)
    try:
        runtime=open_runtime();endpoint=open_data_listener(data,ingest.pw_uid,ipc)
        service=Service(runtime,endpoint.sock,listener,PeerPolicy(reader.pw_uid,reader.pw_gid))
        send(outgoing,dict(stage='service_ready',source=source))
        while True:
            if not select.select([incoming],[],[],0)[0]:service.run_once();continue
            request=receive(incoming)['command']
            if request=='checkpoint':
                runtime.progress.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                send(outgoing,dict(stage='checkpointed'))
            elif request=='restart':
                service.close();runtime.close();runtime=open_runtime()
                service=Service(runtime,endpoint.sock,listener,PeerPolicy(reader.pw_uid,reader.pw_gid))
                send(outgoing,dict(stage='service_restarted'))
            elif request=='stop':break
            else:raise ValueError('unknown test coordination')
    finally:
        if service:service.close()
        if runtime:runtime.close()
        if endpoint:endpoint.close()


def peer(data,scope,incoming,outgoing):
    reader=pwd.getpwnam('hids-audit');ingest=pwd.getpwnam('hids-ingest');ipc=grp.getgrnam('hids-ipc').gr_gid
    os.setgroups([ipc]);os.setgid(reader.pw_gid);os.setuid(reader.pw_uid)
    assert data.lstat().st_uid==ingest.pw_uid and data.lstat().st_gid==ipc
    with socket.socket(socket.AF_UNIX) as channel:
        channel.settimeout(5);channel.connect(str(data))
        pid,uid,gid=struct.unpack('3i',channel.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        assert pid>0 and (uid,gid)==(ingest.pw_uid,ingest.pw_gid)
        def exchange(**value):
            packet=dict(version=3,**scope,**value)
            channel.sendall(json.dumps(packet).encode()+b'\n');reply=b''
            while not reply.endswith(b'\n'):
                block=channel.recv(4096)
                if not block:return None
                reply+=block;assert len(reply)<=4096
            return json.loads(reply)
        assert exchange(op='boundary')==dict(version=3,status='boundary')
        assert exchange(op='register',identity='1.001:1',begin=0,end=10,eoe=True)==dict(version=3,status='admit')
        assert exchange(op='accept',identity='1.001:1',execution=EVENT)==dict(version=3,status='accepted')
        assert exchange(op='register',identity='1.001:2',begin=10,end=20,eoe=True)==dict(version=3,status='admit')
        send(outgoing,dict(stage='peer_prepared',reader_uid=os.getuid(),backend_uid=uid))
        assert receive(incoming)['command']=='write_under_quota'
        reply=exchange(op='accept',identity='1.001:2',execution=EVENT)
        assert reply is None,'quota write received a reply instead of closed/unconfirmed delivery'
        send(outgoing,dict(stage='no_success_ack',connection_closed=True))


def query(path,sql):
    account=pwd.getpwnam('hids-ingest');uid,gid=os.geteuid(),os.getegid()
    try:
        os.setegid(account.pw_gid);os.seteuid(account.pw_uid)
        connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)
        try:return connection.execute(sql).fetchall()
        finally:connection.close()
    finally:os.seteuid(uid);os.setegid(gid)


def run_case(mount,image,device,helper):
    ingest=pwd.getpwnam('hids-ingest');reader=pwd.getpwnam('hids-audit');ipc=grp.getgrnam('hids-ipc').gr_gid
    state=mount/'service-state';state.mkdir(mode=0o700);os.chown(state,ingest.pw_uid,ingest.pw_gid)
    directory=Path(tempfile.mkdtemp(prefix='hids-m3-quota-ipc.',dir='/run'));directory.chmod(0o711)
    private=directory/'control';private.mkdir(mode=0o700)
    shared=directory/'data';shared.mkdir(mode=0o750);os.chown(shared,ingest.pw_uid,ipc);shared.chmod(0o750)
    listener=socket.socket(socket.AF_UNIX);listener.bind(str(private/'control.sock'))
    (private/'control.sock').chmod(0o600);listener.listen(4)
    children=[];streams=[]
    def quota(value):return json.loads(command(str(helper),str(image),str(mount),device,str(value)))
    def fork_child(function,*,drop=False):
        rp,wc=os.pipe();rc,wp=os.pipe();child=os.fork()
        if child==0:
            os.close(rp);os.close(wp)
            for inherited in streams:inherited.close()
            if not drop:listener.close()
            if drop:os.setgroups([ipc]);os.setgid(ingest.pw_gid);os.setuid(ingest.pw_uid)
            with os.fdopen(rc) as incoming,os.fdopen(wc,'w') as outgoing:
                try:function(incoming,outgoing)
                except BaseException:traceback.print_exc();sys.stderr.flush();os._exit(1)
            os._exit(0)
        children.append(child);os.close(rc);os.close(wc)
        incoming,outgoing=os.fdopen(rp),os.fdopen(wp,'w');streams.extend((incoming,outgoing))
        return child,incoming,outgoing
    def rpc(**value):return control_request(private/'control.sock',dict(version=3,**value))
    try:
        server,server_in,server_out=fork_child(lambda incoming,outgoing:backend(state,shared/'data.sock',listener,incoming,outgoing),drop=True)
        ready=receive(server_in);assert ready['stage']=='service_ready';source=ready['source'];activation=str(uuid.uuid4())
        assert rpc(command='activate',source=source,activation=activation)['result']=='activated'
        scope=rpc(command='lease')['scope']
        client,client_in,client_out=fork_child(lambda incoming,outgoing:peer(shared/'data.sock',scope,incoming,outgoing))
        prepared=receive(client_in);assert prepared['stage']=='peer_prepared'
        send(server_out,dict(command='checkpoint'));assert receive(server_in)['stage']=='checkpointed'
        limit=quota(1);assert limit['hard_blocks']==1
        send(client_out,dict(command='write_under_quota'));assert receive(client_in)['stage']=='no_success_ack'
        _,status=os.waitpid(client,0);children.remove(client);assert status==0
        failed=rpc(command='status')
        assert failed['failure']=='storage_failure' and not failed['reader_connected'] and not failed['source_ready']
        assert failed['possible_gap'] and failed['storage']['state']=='normal'
        path=state/(activation+'.sqlite')
        assert query(path,'SELECT identity FROM m3_execution')==[('1.001:1',)]
        assert query(path,"SELECT state FROM m3_disposition WHERE identity='1.001:2'")[0][0] in ('open','interrupted')
        assert rpc(command='lease')['result']=='rejected'
        assert rpc(command='activate',source=source,activation=str(uuid.uuid4()))['result']=='rejected'
        assert quota(0)['hard_blocks']==0
        restored=rpc(command='status')
        assert restored['failure']=='storage_failure' and not restored['source_ready']
        assert rpc(command='activate',source=source,activation=str(uuid.uuid4()))['result']=='rejected'
        send(server_out,dict(command='restart'));assert receive(server_in)['stage']=='service_restarted'
        restarted=rpc(command='status');assert restarted['failure'] is None and not restarted['source_ready']
        assert rpc(command='lease')['result']=='rejected'
        assert query(path,'PRAGMA integrity_check')==[('ok',)]
        assert query(path,'SELECT identity FROM m3_execution')==[('1.001:1',)]
        assert query(path,"SELECT state FROM m3_disposition WHERE identity='1.001:2'")==[('interrupted',)]
        send(server_out,dict(command='stop'));_,status=os.waitpid(server,0);children.remove(server);assert status==0
        return dict(result='passed',backend_uid=ingest.pw_uid,reader_uid=reader.pw_uid,
            no_success_ack=True,root_failure='storage_failure',sampled_storage=failed['storage'],
            failure_latched_after_quota_release=True,activation_and_leases_denied=True,
            restart_integrity='ok',accepted=1,interrupted=1,source_ready_after_restart=False)
    finally:
        for stream in streams:stream.close()
        for child in children:
            try:os.kill(child,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(child,0)
        listener.close()
        for endpoint in (private/'control.sock',shared/'data.sock'):
            if endpoint.exists():endpoint.unlink()
        private.rmdir();shared.rmdir();directory.rmdir()
