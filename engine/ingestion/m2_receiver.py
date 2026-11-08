"""M2 ingestion primitives. No journal reads, service startup or activation CLI."""
import grp
import os
from pathlib import Path
import pwd
import socket
import stat
import struct
import threading
import time
from engine.ingestion.m1_contract import Invalid, utc_now
from engine.ingestion.m1_io import ready, write_all
from engine.ingestion.m2_contract import decode, frame, validate_event, event_id, RESPONSE_LIMIT
from engine.ingestion.m1_security import private_file


class TerminalFailure(RuntimeError):pass


class PeerPolicy:
    def __init__(self,uid,gid,pid=None):
        if uid<=0 or gid<0 or (pid is not None and pid<=0):raise ValueError('peer_policy')
        self.uid,self.gid,self.pid=uid,gid,pid

    def check(self,sock):
        if not hasattr(socket,'SO_PEERCRED'):raise PermissionError('linux_credentials_required')
        raw=sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i'))
        pid,uid,gid=struct.unpack('3i',raw)
        if pid<=0 or (uid,gid)!=(self.uid,self.gid) or (self.pid is not None and pid!=self.pid):raise PermissionError('peer_denied')
        return pid


def service_policy(role):
    """Resolve trusted NSS identities, never infer GID from UID. No grants."""
    reader=pwd.getpwnam('hids-journal');ingest=pwd.getpwnam('hids-ingest')
    ipc=grp.getgrnam('hids-ipc').gr_gid;journal=grp.getgrnam('systemd-journal').gr_gid
    if reader.pw_uid!=997 or ingest.pw_uid in (0,997) or reader.pw_gid==0 or ingest.pw_gid==0:
        raise PermissionError('service_identity')
    if grp.getgrnam('hids-journal').gr_gid!=reader.pw_gid or grp.getgrnam('hids-ingest').gr_gid!=ingest.pw_gid:
        raise PermissionError('primary_group_policy')
    me=reader if role=='reader' else ingest if role=='ingest' else None
    if me is None or os.getuid()!=me.pw_uid or os.geteuid()!=me.pw_uid or os.getgid()!=me.pw_gid or os.getegid()!=me.pw_gid:raise PermissionError('service_identity')
    expected={me.pw_gid,ipc}|({journal} if role=='reader' else set())
    if set(os.getgroups())|{me.pw_gid}!=expected:raise PermissionError('supplementary_groups')
    other=ingest if role=='reader' else reader
    return PeerPolicy(other.pw_uid,other.pw_gid),ipc


def _directory(path,uid,gid,mode):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise PermissionError('unsafe_directory')
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(uid,gid,mode):raise PermissionError('directory_policy')


class Listener:
    def __init__(self,path,uid,gid):
        self.path=Path(path);self.sock=None;self.owned=None
        if os.getuid()==0 or os.getuid()!=uid or os.geteuid()!=uid:raise PermissionError('nonroot_ingestion_identity')
        _directory(self.path.parent,uid,gid,0o750)
        if os.path.lexists(self.path):raise PermissionError('existing_socket')
        if len(os.fsencode(self.path))>=108:raise ValueError('socket_path')
        try:
            self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.sock.set_inheritable(False);self.sock.setblocking(False)
            self.sock.bind(str(self.path));i=self.path.lstat();self.owned=(i.st_dev,i.st_ino)
            os.chown(self.path,uid,gid)  # Explicit hids-ingest:hids-ipc; never assumed from umask.
            os.chmod(self.path,0o660)
            i=self.path.lstat()
            if not stat.S_ISSOCK(i.st_mode) or (i.st_dev,i.st_ino)!=self.owned or (i.st_uid,i.st_gid,stat.S_IMODE(i.st_mode))!=(uid,gid,0o660):raise PermissionError('socket_initialization_verification')
            self.sock.listen(1)
        except BaseException:
            self.close();raise

    def close(self):
        if self.sock is not None:self.sock.close();self.sock=None
        if self.owned is not None:
            try:
                i=self.path.lstat()
                if (i.st_dev,i.st_ino)==self.owned:self.path.unlink()
            except FileNotFoundError:pass
            self.owned=None


class Framer:
    def __init__(self,limit=65536):self.limit=limit;self.buffer=bytearray()
    def feed(self,chunk):
        for byte in chunk:
            if byte==10:
                value=bytes(self.buffer);self.buffer.clear();yield value
            else:
                if len(self.buffer)>=self.limit:raise Invalid('frame_too_large')
                self.buffer.append(byte)


class Receiver:
    """A caller-owned serialized service loop; activate/revoke only via trusted control."""
    def __init__(self,store,source,activation,peer):
        self.store,self.source,self.activation,self.peer=store,source,activation,peer
        self.lease=threading.Lock();self.failed=False;self.reader_pid=None

    def handle(self,obj):
        from engine.ingestion.m1_contract import keys, integer
        if obj.get('message_type')=='reconcile':
            keys(obj,'protocol_version message_type');integer(obj['protocol_version'],2,2)
            p=self.store.progress(self.source,self.activation)
            if p['state'] in ('gap','revoked'):raise Invalid('inactive_source')
            return {'protocol_version':2,'message_type':'progress','source_id':self.source,
                    **{k:v for k,v in p.items() if k!='authorized'}}
        if obj.get('message_type')=='gap':
            keys(obj,'protocol_version message_type code');integer(obj['protocol_version'],2,2)
            self.store.gap(self.source,self.activation,obj['code'])
            return {'protocol_version':2,'message_type':'gap_ack','code':obj['code']}
        if obj.get('message_type')=='boundary':
            keys(obj,'protocol_version message_type cursor started_at ended_at');integer(obj['protocol_version'],2,2)
            self.store.boundary(self.source,self.activation,obj['cursor'],obj['started_at'],obj['ended_at'])
            return {'protocol_version':2,'message_type':'boundary_ack','cursor':obj['cursor']}
        validate_event(obj)
        if obj['source_id']!=self.source or obj['activation_id']!=self.activation:raise Invalid('inactive_source')
        return self.store.put(obj,utc_now())

    def serve(self,sock,*,stopped=lambda:False,response_hook=lambda x:x):
        # Authentication precedes any bytes, and PID lease lasts only this connection.
        pid=self.peer.check(sock)
        if self.failed:raise TerminalFailure('receiver_requires_explicit_restart')
        if not self.lease.acquire(False):raise Invalid('reader_busy')
        self.reader_pid=pid
        sock.setblocking(False);framer=Framer();pending=None
        try:
            deadline=time.monotonic()+5
            while not stopped():
                ready(sock.fileno(),False,deadline,stopped)
                try:chunk=sock.recv(4096)
                except (BlockingIOError,InterruptedError):continue
                if not chunk:return
                for line in framer.feed(chunk):
                    pending=None;obj=decode(line)
                    try:
                        if obj.get('event_id')==event_id(obj.get('source_id'),obj.get('cursor')):
                            pending=obj['event_id']
                    except Invalid:
                        pass  # Invalid/oversized identity must not inflate a reject frame.
                    # Only a validated pending event can receive storage_error.
                    is_event=obj.get('message_type') in ('journal_event','journal_rejection')
                    if is_event:validate_event(obj)
                    try:response=self.handle(obj)
                    except Invalid:raise
                    except Exception as exc:
                        self.failed=True
                        if is_event:
                            write_all(sock.fileno(),frame({'protocol_version':2,'message_type':'error','event_id':pending,'code':'storage_error'},RESPONSE_LIMIT),time.monotonic()+5,stopped)
                        raise TerminalFailure('storage_outcome_unconfirmed') from exc
                    # Post-commit response failure cannot become a rejection.
                    wire=response_hook(response)
                    wire=wire if type(wire) is bytes else frame(wire,RESPONSE_LIMIT)
                    if len(wire)>RESPONSE_LIMIT+1:raise TerminalFailure('response_encoding')
                    write_all(sock.fileno(),wire,time.monotonic()+5,stopped)
                    pending=None;deadline=time.monotonic()+5
        except Invalid as exc:
            self.failed=True
            try:write_all(sock.fileno(),frame({'protocol_version':2,'message_type':'reject','event_id':pending,'code':exc.code},RESPONSE_LIMIT),time.monotonic()+5,stopped)
            except OSError:pass
            raise TerminalFailure('protocol_failure') from exc
        except TerminalFailure:
            self.failed=True;raise
        except (OSError,EOFError,TimeoutError):
            return  # Disconnect alone: persisted progress reconciled after reconnect.
        except Exception as exc:
            self.failed=True;raise TerminalFailure('post_commit_or_protocol_failure') from exc
        finally:self.reader_pid=None;self.lease.release()
