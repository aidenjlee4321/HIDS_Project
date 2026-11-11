"""Serialized production M2 ingestion/control lifecycle; never reads journal data."""
import argparse
import errno
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import stat
import struct
import sys
import time

from engine.database.m2_store import Store
from engine.ingestion.m1_contract import Invalid, integer, keys, uuid_valid
from engine.ingestion.m2_contract import decode, event_id, frame, RESPONSE_LIMIT
from engine.ingestion.m2_receiver import Listener, Receiver, Framer, service_policy, _directory


class RootPolicy:
    def check(self, connection):
        if not hasattr(socket, 'SO_PEERCRED'):
            raise PermissionError('linux_credentials_required')
        pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if pid <= 0 or uid != 0:
            raise PermissionError('root_control_required')
        return pid


def load_root_json(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise PermissionError('config_path')
    for directory in path.parents:
        info = directory.stat()
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
            raise PermissionError('config_parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > 4096:
            raise PermissionError('config_policy')
        raw = os.read(fd, 4097)
        if len(raw) > 4096:
            raise ValueError('config_size')
    finally:
        os.close(fd)
    # Configuration may use pretty-printing; strict duplicate detection remains.
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('config_duplicate')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def load_config(path):
    config = load_root_json(path)
    keys(config, 'source_id max_records max_pages')
    if not uuid_valid(config['source_id']):
        raise ValueError('config_source')
    integer(config['max_records'], 1, 2**63-1)
    integer(config['max_pages'], 16, 2147483646)
    return config


def systemd_control_listener(endpoint_path='/run/hids/control.sock'):
    if sys.platform != 'linux' or os.environ.get('LISTEN_PID') != str(os.getpid()) or os.environ.get('LISTEN_FDS') != '1':
        raise PermissionError('systemd_control_fd_required')
    path = Path(endpoint_path)
    _directory(path.parent, 0, 0, 0o755)
    endpoint = path.lstat()
    if not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid != 0 or endpoint.st_gid != 0 or stat.S_IMODE(endpoint.st_mode) != 0o600:
        raise PermissionError('root_control_endpoint')
    listener = socket.socket(fileno=3)
    listener.set_inheritable(False)
    if listener.family != socket.AF_UNIX or listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM or not listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) or listener.getsockname() != str(path):
        listener.close()
        raise PermissionError('control_listener_policy')
    listener.setblocking(False)
    return listener


class Client:
    def __init__(self, sock, control, pid, now):
        self.sock, self.control, self.pid = sock, control, pid
        self.framer = Framer(2048 if control else 65536)
        self.frames = None
        self.output = b''
        self.deadline = now + 5
        self.close_after = False
        self.reconciled = False
        self.activation = None


class Service:
    """One SQLite owner/event loop. Policy injection is an internal fixture seam."""
    def __init__(self, store, source, data_listener, control_listener, peer,
                 control_peer=None, stopped=lambda: False, clock=time.monotonic,
                 response_hook=lambda response: response):
        self.store, self.source = store, source
        self.data_listener, self.control_listener = data_listener, control_listener
        self.peer = peer
        self.control_peer = RootPolicy() if control_peer is None else control_peer
        self.stopped, self.clock, self.response_hook = stopped, clock, response_hook
        self.selector = selectors.DefaultSelector()
        for listener, kind in ((data_listener, 'data'), (control_listener, 'control')):
            listener.setblocking(False)
            self.selector.register(listener, selectors.EVENT_READ, kind)
        self.clients = {}
        self.reader = None
        self.failure = None
        self.durable_failure = None
        self.closed = False

    def current(self):
        row = self.store.conn.execute('SELECT activation,authorized,state,revision FROM progress WHERE source=?', (self.source,)).fetchone()
        return row

    def note(self, client, code):
        if not client.reconciled or not client.activation:
            return
        try:
            p = self.store.progress(self.source, client.activation)
            if p['state'] == 'initializing':
                self.store.gap(self.source, client.activation, 'unanchored_restart_gap')
            elif p['state'] not in ('gap', 'revoked'):
                self.store.note_interruption(self.source, client.activation, code)
        except Invalid:
            pass  # Already revoked; never reactivate it.
        except Exception:
            self.failure = 'storage_outcome_unconfirmed'
            self.durable_failure = False

    def drop(self, client, reason=None):
        if client.sock not in self.clients:
            return
        if reason and not client.control:
            self.note(client, reason)
        try:
            self.selector.unregister(client.sock)
        except (KeyError, ValueError):
            pass
        self.clients.pop(client.sock, None)
        client.sock.close()
        if self.reader is client:
            self.reader = None

    def control(self, obj):
        integer(obj.get('protocol_version'), 2, 2)
        command = obj.get('command')
        if command == 'status':
            keys(obj, 'protocol_version command')
            row = self.current()
            return {'protocol_version': 2, 'result': 'status', 'source_id': self.source,
                    'activation_id': row[0] if row else None,
                    'state': row[2] if row else 'inactive', 'revision': row[3] if row else 0,
                    'failure': self.failure, 'durable_failure': self.durable_failure,
                    'reader_connected': self.reader is not None,
                    'reader_pid': self.reader.pid if self.reader else None}
        keys(obj, 'protocol_version command source_id activation_id')
        if obj['source_id'] != self.source or not uuid_valid(obj['activation_id']):
            raise Invalid('inactive_source')
        if command == 'activate':
            if self.failure:
                raise Invalid('inactive_source')
            self.store.activate(self.source, obj['activation_id'], authorized=True)
            return {'protocol_version': 2, 'result': 'activated', 'activation_id': obj['activation_id']}
        if command == 'deactivate':
            # The serial loop processes control readiness before event readiness.
            self.store.revoke(self.source, obj['activation_id'])
            if self.reader:
                self.drop(self.reader)  # No pending event ACK is manufactured.
            return {'protocol_version': 2, 'result': 'deactivated', 'activation_id': obj['activation_id']}
        raise Invalid('invalid_event')

    def queue(self, client, response):
        wire = self.response_hook(response)
        wire = wire if type(wire) is bytes else frame(wire, RESPONSE_LIMIT)
        if len(wire) > RESPONSE_LIMIT+1:
            raise ValueError('response_limit')
        client.output = wire
        client.deadline = self.clock()+5
        self.selector.modify(client.sock, selectors.EVENT_WRITE, client)

    def fatal(self, client, code, event=None, storage=False):
        self.failure = 'storage_outcome_unconfirmed' if storage else 'protocol_failure'
        self.durable_failure = False
        if not storage and client.activation:
            try:
                self.store.gap(self.source, client.activation, 'protocol_failure')
                self.durable_failure = True
            except Exception:
                pass
        client.close_after = True
        if storage and event is None:
            self.drop(client)  # No validated event exists for a storage_error response.
        else:
            self.queue(client, {'protocol_version': 2, 'message_type': 'error' if storage else 'reject',
                                'event_id': event, 'code': 'storage_error' if storage else code})

    def dispatch(self, client, payload):
        pending = None
        try:
            obj = decode(payload, 2048 if client.control else 65536)
            if client.control:
                response = self.control(obj)
                client.close_after = True
            else:
                if self.failure:
                    raise Invalid('inactive_source')
                row = self.current()
                if not row or not row[1] or row[2] in ('gap', 'revoked'):
                    raise Invalid('inactive_source')
                if client.activation and client.activation != row[0]:
                    raise Invalid('inactive_source')
                client.activation = row[0]
                try:
                    if obj.get('event_id') == event_id(obj.get('source_id'), obj.get('cursor')):
                        pending = obj['event_id']
                except Invalid:
                    pass
                # Rejects are not storage errors: validate before entering DB handling.
                if obj.get('message_type') in ('journal_event', 'journal_rejection'):
                    from engine.ingestion.m2_contract import validate_event
                    validate_event(obj)
                receiver = Receiver(self.store, self.source, row[0], self.peer)
                response = receiver.handle(obj)
                if obj.get('message_type') == 'reconcile':
                    client.reconciled = True
                if obj.get('message_type') == 'gap':
                    client.close_after = True
            # Any encoding failure here is post-commit: never send a rejection.
            try:
                self.queue(client, response)
            except OSError:
                self.drop(client, 'reader_disconnected')  # Lost ACK only.
            except Exception:
                self.failure = 'post_commit_response_failure'
                self.durable_failure = False
                self.drop(client)
        except Invalid as exc:
            if client.control:
                client.close_after = True
                self.queue(client, {'protocol_version': 2, 'result': 'rejected', 'code': exc.code})
            elif exc.code in ('inactive_source', 'reader_busy'):
                client.close_after = True
                self.queue(client, {'protocol_version': 2, 'message_type': 'reject', 'event_id': pending, 'code': exc.code})
            else:
                self.fatal(client, exc.code, pending)
        except Exception:
            if client.control:
                self.failure = 'storage_outcome_unconfirmed'
                self.durable_failure = False
                if self.reader:
                    self.drop(self.reader)
                client.close_after = True
                self.queue(client, {'protocol_version': 2, 'result': 'error', 'code': 'storage_outcome_unconfirmed'})
            else:
                self.fatal(client, 'storage_error', pending, storage=True)

    def accept(self, listener, control):
        try:
            sock, _ = listener.accept()
        except (BlockingIOError, InterruptedError):
            return
        sock.setblocking(False)
        sock.set_inheritable(False)
        try:
            pid = (self.control_peer if control else self.peer).check(sock)
            if len(self.clients) >= 4 or (not control and self.reader is not None):
                sock.close()  # Bounded peers; do not displace a living reader.
                return
            client = Client(sock, control, pid, self.clock())
            self.clients[sock] = client
            if not control:
                self.reader = client
            self.selector.register(sock, selectors.EVENT_READ, client)
        except Exception:
            sock.close()

    def advance_frame(self, client):
        if client.frames is None:
            return
        try:
            payload = next(client.frames)
            self.dispatch(client, payload)
        except StopIteration:
            client.frames = None
        except Invalid as exc:
            if client.control:
                client.close_after = True
                self.queue(client, {'protocol_version': 2, 'result': 'rejected', 'code': exc.code})
            else:
                self.fatal(client, exc.code)

    def run_once(self):
        if self.closed or self.stopped():
            return
        events = self.selector.select(.1)
        if self.stopped():
            return
        # Root requests already ready take precedence over event commits.
        events.sort(key=lambda event: 0 if event[0].data == 'control' or (isinstance(event[0].data, Client) and event[0].data.control) else 1)
        for key, mask in events:
            if self.stopped():
                break
            value = key.data
            if value in ('data', 'control'):
                self.accept(key.fileobj, value == 'control')
                continue
            client = value
            if client.sock not in self.clients:
                continue
            try:
                if mask & selectors.EVENT_WRITE:
                    try:
                        count = client.sock.send(client.output)
                    except (BlockingIOError, InterruptedError):
                        continue
                    if count <= 0:
                        self.drop(client, 'reader_disconnected')
                        continue
                    client.output = client.output[count:]
                    if not client.output:
                        if client.close_after:
                            self.drop(client)
                        else:
                            client.deadline = self.clock()+5
                            self.selector.modify(client.sock, selectors.EVENT_READ, client)
                            self.advance_frame(client)
                elif mask & selectors.EVENT_READ:
                    if client.frames is not None:
                        self.advance_frame(client)
                        if client.frames is not None or client.output or client.sock not in self.clients:
                            continue
                    try:
                        chunk = client.sock.recv(4096)
                    except (BlockingIOError, InterruptedError):
                        continue
                    if not chunk:
                        self.drop(client, 'reader_disconnected')
                        continue
                    client.frames = client.framer.feed(chunk)
                    self.advance_frame(client)
            except (OSError, TimeoutError):
                self.drop(client, 'reader_disconnected')
        now = self.clock()
        for client in list(self.clients.values()):
            if now >= client.deadline:
                self.drop(client, 'lease_expired')

    def run(self):
        try:
            while not self.stopped():
                self.run_once()
            return 1 if self.failure else 0
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        for client in list(self.clients.values()):
            self.drop(client, 'ingest_shutdown')
        self.selector.close()


def main():
    parser = argparse.ArgumentParser(description='HIDS M2 ingestion; requires root-controlled systemd socket and service identity')
    parser.add_argument('--config', default='/etc/hids/m2.json')
    args = parser.parse_args()
    store = endpoint = control = service = None
    stopped = False
    def stop(_sig, _frame):
        nonlocal stopped
        stopped = True
    try:
        if sys.platform != 'linux':
            raise PermissionError('linux_required')
        peer, ipc_gid = service_policy('ingest')
        config = load_config(args.config)
        _directory(Path('/run/hids'), 0, 0, 0o755)
        control = systemd_control_listener()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, stop)
        store = Store('/var/lib/hids/m2/journal.sqlite', max_records=config['max_records'], max_pages=config['max_pages'])
        endpoint = Listener('/run/hids/ingest/journal.sock', os.getuid(), ipc_gid)
        service = Service(store, config['source_id'], endpoint.sock, control, peer, stopped=lambda: stopped)
        return service.run()
    except Exception:
        print('m2_ingestion_startup_or_runtime_failure', file=sys.stderr)
        return 1
    finally:
        if service: service.close()
        if endpoint: endpoint.close()
        if control: control.close()
        if store: store.close()


if __name__ == '__main__':
    raise SystemExit(main())
