"""One granted process connection; no native collection and no HTTP routes."""
import os
import select
import socket
import sqlite3
import struct
import time
from engine.ingestion import process_contract as c
from engine.database.process_store import Store


def peer_uid(connection):
    return struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]

def send(connection,value,stopped=lambda:False):
    data=c.frame(value);offset=0;deadline=time.monotonic()+2
    while offset<len(data):
        if stopped() or time.monotonic()>=deadline:raise TimeoutError('response_deadline')
        if not select.select([], [connection], [], .05)[1]:continue
        try:offset+=connection.send(data[offset:],socket.MSG_NOSIGNAL)
        except (BlockingIOError,InterruptedError):continue
        if offset==0:raise EOFError()


def serve(listener,path,source,expected_uid,*,mode='live',stopped=lambda:False,ready=lambda:None,timeout=60,store_options=None):
    """Listener is an inherited root-created endpoint in production. No bind here."""
    if os.getuid()==0:raise PermissionError('backend_must_be_unprivileged')
    if listener.family!=socket.AF_UNIX or listener.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_STREAM or not listener.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN):raise PermissionError('unix_listener_required')
    c.require(type(expected_uid) is int and expected_uid>0)
    store=Store(path,source,mode,**(store_options or {}));connection=None;producer=None;last=None;failure_reason='transport_failed'
    try:
        listener.setblocking(False);ready();deadline=time.monotonic()+timeout
        while not stopped() and time.monotonic()<deadline:
            if not select.select([listener],[],[],.05)[0]:continue
            try:connection,_=listener.accept()
            except (BlockingIOError,InterruptedError):continue
            connection.setblocking(False)
            if peer_uid(connection)!=expected_uid:connection.close();connection=None;continue
            break
        if connection is None:raise TimeoutError('collector_not_connected')
        framer=c.Framer(c.EVENT_LIMIT);idle=time.monotonic()+5
        while not stopped():
            if time.monotonic()>=idle:raise TimeoutError('collector_idle')
            if not select.select([connection],[],[],.05)[0]:continue
            try:data=connection.recv(4096)
            except (BlockingIOError,InterruptedError):continue
            if not data:
                if framer.buffer:raise c.Invalid('invalid_json')
                break
            for payload in framer.feed(data):
                idle=time.monotonic()+5;event_id=None
                try:
                    value=c.decode(payload)
                    if value.get('message_type')=='status':
                        claimed=value.get('producer_instance_id');c.require(c.uuid_valid(claimed))
                        c.status(value,source,claimed if producer is None else producer,mode)
                        if producer is None:producer=claimed
                        store.interval(value,producer);last=value
                        send(connection,dict(protocol_version=1,message_type='status_ack',producer_instance_id=producer),stopped)
                    else:
                        c.require(producer is not None)
                        if c.uuid_valid(value.get('event_id')):event_id=value['event_id']
                        c.validate(value,source,mode,producer)
                        try:result,_=store.put(value)
                        except (OSError,sqlite3.Error):
                            # A post-COMMIT failure is not proof of rollback. Resolve
                            # the same ID/payload on this usable connection, read-only.
                            if store.committed(value) is None:raise
                            result='duplicate'
                        send(connection,dict(protocol_version=1,message_type='ack',event_id=event_id,result=result),stopped)
                except Exception as exc:
                    code=exc.code if isinstance(exc,c.Invalid) and exc.code in ('invalid_event','invalid_json','unsupported_version','frame_too_large','id_conflict','capacity_exceeded') else 'storage_error'
                    failure_reason='capacity' if code=='capacity_exceeded' else 'storage_failed' if code=='storage_error' else 'source_failed'
                    try:send(connection,dict(protocol_version=1,message_type='error',event_id=event_id,code=code),stopped)
                    except (OSError,TimeoutError,EOFError):pass
                    raise
    finally:
        if producer is not None and (last is None or not last['stopped']):
            # Best effort only: capacity/FULL may prevent a durable final status.
            # Root supervision must also surface receiver failure independently.
            value=dict(protocol_version=1,message_type='status',contract_version=c.CONTRACT,source=source,producer_instance_id=producer,acknowledged=bool(last and last['acknowledged']),delivery=bool(last and last['delivery']),incomplete=True,stopped=True,reason=failure_reason,diagnostic_counts=last['diagnostic_counts'] if last else [0]*20)
            try:store.interval(value,producer)
            except Exception:pass
        if connection is not None:connection.close()
        store.close()
