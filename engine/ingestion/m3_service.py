"""Serialized M3 control and ingestion. Reads no native Audit source itself."""

import argparse
import errno
import grp
import os
from pathlib import Path
import pwd
import selectors
import signal
import socket
import sqlite3
import stat
import sys
import time

from engine.ingestion.m1_contract import Invalid, integer, keys, uuid_valid
from engine.ingestion.m2_contract import decode, frame
from engine.ingestion.m2_receiver import Listener, PeerPolicy, _directory
from engine.ingestion.m2_service import Client, RootPolicy, load_root_json, systemd_control_listener
from engine.ingestion.m3_progress import CapacityError, ProgressError
from engine.ingestion.m3_protocol import SCOPE_FIELDS, VERSION, dispatch_request, parse_request
from engine.ingestion.m3_runtime import SOURCE_GAPS, Runtime
from engine.ingestion import m3_health


def load_config(path):
    config = load_root_json(path)
    keys(config, 'source_id max_activations max_pages position_limit')
    if not uuid_valid(config['source_id']):
        raise ValueError('invalid_source')
    integer(config['max_activations'], 1, 65536)
    integer(config['max_pages'], 32, 2147483646)
    integer(config['position_limit'], 1, 65536)
    return config


def identities():
    reader = pwd.getpwnam('hids-audit')
    ingest = pwd.getpwnam('hids-ingest')
    ipc = grp.getgrnam('hids-ipc').gr_gid
    if (reader.pw_uid <= 0 or ingest.pw_uid <= 0 or reader.pw_uid == ingest.pw_uid or
            min(reader.pw_gid, ingest.pw_gid, ipc) <= 0 or
            reader.pw_gid == ingest.pw_gid or ipc in (reader.pw_gid, ingest.pw_gid)):
        raise PermissionError('distinct_service_identities_required')
    for name, entry in (('hids-audit', reader), ('hids-ingest', ingest)):
        if grp.getgrnam(name).gr_gid != entry.pw_gid:
            raise PermissionError('primary_group_policy')
    return reader, ingest, ipc


def open_data_listener(path, uid, ipc_gid):
    """The runtime writer lock must already be held before stale-socket recovery."""
    path = Path(path)
    _directory(path.parent, uid, ipc_gid, 0o750)
    if os.path.lexists(path):
        original = path.lstat()
        if not stat.S_ISSOCK(original.st_mode) or (
                original.st_uid, original.st_gid, stat.S_IMODE(original.st_mode)) != (uid, ipc_gid, 0o660):
            raise PermissionError('unexpected_data_endpoint')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(.25)
            try:
                probe.connect(str(path))
            except OSError as error:
                if error.errno != errno.ECONNREFUSED:
                    raise PermissionError('data_endpoint_state_unverified') from error
            else:
                raise PermissionError('data_endpoint_still_listening')
        current = path.lstat()
        if (current.st_dev, current.st_ino, current.st_uid, current.st_gid, current.st_mode) != (
                original.st_dev, original.st_ino, original.st_uid, original.st_gid, original.st_mode):
            raise PermissionError('data_endpoint_changed')
        path.unlink()
    return Listener(path, uid, ipc_gid)


class Service:
    def __init__(self, runtime, data_listener, control_listener, peer, *,
                 control_peer=None, health_listener=None, health_peer=None,
                 stopped=lambda: False, clock=time.monotonic):
        self.runtime = runtime
        self.peer = peer
        self.control_peer = RootPolicy() if control_peer is None else control_peer
        self.health_peer = RootPolicy() if health_peer is None else health_peer
        self.health_failure = None
        self.stopped, self.clock = stopped, clock
        self.selector = selectors.DefaultSelector()
        for listener, kind in ((data_listener, 'data'), (control_listener, 'control')):
            listener.setblocking(False)
            self.selector.register(listener, selectors.EVENT_READ, kind)
        if health_listener is not None:
            health_listener.setblocking(False)
            self.selector.register(health_listener, selectors.EVENT_READ, 'health')
        self.clients = {}
        self.reader = None
        self.scope = None
        self.failure = None
        self.closed = False

    def drop(self, client, code='stream_disconnected'):
        if client.sock not in self.clients:
            return
        try:
            self.selector.unregister(client.sock)
        except KeyError:
            pass
        del self.clients[client.sock]
        client.sock.close()
        if self.reader is client:
            self.reader = None
            self.scope = None
            try:
                self.runtime.interrupt(code)
            except Exception:
                self.failure = 'storage_failure'

    def control(self, request):
        if type(request.get('version')) is not int or request['version'] != VERSION:
            raise ProgressError('unsupported control version')
        command = request.get('command')
        if command in ('status', 'lease'):
            keys(request, 'version command')
            if command == 'status':
                status = self.runtime.status()
                if self.health_failure:
                    status['upstream_loss'] = {'kernel': 'unknown', 'dispatcher': 'unknown'}
                    if status['upstream_health'] is not None:
                        status['upstream_health']['freshness'] = 'unavailable'
                        status['upstream_health']['kernel'] = status['upstream_health']['dispatcher'] = 'unknown'
                status['possible_gap'] |= self.failure is not None
                return dict(version=VERSION, result='status', failure=self.failure,
                            health_reporting_error=self.health_failure,
                            reader_connected=self.reader is not None, **status)
            current = self.runtime.current()
            if self.failure or not current or current['state'] != 'ready':
                raise ProgressError('reader lease unavailable')
            return {'version': VERSION, 'result': 'lease', 'source': self.runtime.source,
                    'scope': {key: current[key] for key in ('activation', 'generation', 'lease')}}
        keys(request, 'version command source activation')
        if request['source'] != self.runtime.source or not uuid_valid(request['activation']):
            raise ProgressError('invalid control scope')
        if command == 'activate':
            if self.failure:
                raise ProgressError('service requires explicit restart')
            current = self.runtime.activate(request['activation'])
            return {'version': VERSION, 'result': 'activated', 'activation': current['activation']}
        if command == 'deactivate':
            self.runtime.revoke(request['activation'])
            if self.reader is not None:
                self.drop(self.reader, 'revoked')
            return {'version': VERSION, 'result': 'deactivated', 'activation': request['activation']}
        raise ProgressError('unknown control command')

    def health(self, request):
        if type(request.get('version')) is not int or request['version'] != VERSION:
            raise ProgressError('unsupported health version')
        current = self.runtime.current()
        if request.get('command') == 'scope':
            keys(request, 'version command')
            if not current or current['state'] not in ('ready', 'streaming'):
                return {'version': VERSION, 'result': 'inactive'}
            return {'version': VERSION, 'result': 'scope', 'activation': current['activation'], 'generation': current['generation']}
        keys(request, 'version command activation generation observation')
        if request['command'] != 'sample' or not current or current['state'] not in ('ready', 'streaming') or any(
                request[key] != current[key] for key in ('activation', 'generation')):
            raise ProgressError('inactive health scope')
        result = m3_health.record(self.runtime.db, current['activation'], current['generation'], request['observation'])
        self.health_failure = None
        return {'version': VERSION, 'result': result}

    def accept(self, listener, control, health=False):
        try:
            connection, _ = listener.accept()
        except (BlockingIOError, InterruptedError):
            return
        connection.setblocking(False)
        connection.set_inheritable(False)
        try:
            pid = (self.health_peer if health else self.control_peer if control else self.peer).check(connection)
            if (len(self.clients) >= 4 or (not control and (self.reader is not None or self.failure)) or
                    (health and any(getattr(client, 'health', False) for client in self.clients.values()))):
                connection.close()
                return
            client = Client(connection, control, pid, self.clock())
            client.health = health
            if not control:
                self.scope = self.runtime.claim()
                self.reader = client
                client.deadline = None
            self.clients[connection] = client
            self.selector.register(connection, selectors.EVENT_READ, client)
        except Exception as error:
            if isinstance(error, sqlite3.Error):
                self.failure = 'storage_failure'
            if connection in self.clients:
                self.drop(self.clients[connection])
            elif self.reader is not None and self.reader.sock is connection:
                self.reader = None
                self.scope = None
                try:
                    self.runtime.interrupt('stream_disconnected')
                except Exception:
                    self.failure = 'storage_failure'
            connection.close()

    def queue(self, client, response):
        client.output = frame(response, 2048)
        client.deadline = self.clock() + 2
        self.selector.modify(client.sock, selectors.EVENT_WRITE, client)

    def advance(self, client):
        if client.frames is None:
            return
        try:
            raw = next(client.frames)
            if client.control:
                response = (self.health if client.health else self.control)(decode(raw, 2048))
                client.close_after = True
            else:
                current = self.runtime.current()
                if self.failure or not current or current['state'] != 'streaming':
                    raise ProgressError('inactive source')
                request = parse_request(raw + b'\n', self.scope)
                if request.get('op') == 'gap':
                    if (request.keys() != SCOPE_FIELDS | {'version', 'op', 'code'} or
                            type(request['code']) is not str or request['code'] not in SOURCE_GAPS):
                        raise ProgressError('invalid source gap')
                    self.runtime.interrupt(request['code'])
                    client.close_after = True
                    status = 'interrupted'
                else:
                    status = dispatch_request(request, self.runtime.progress, require_boundary=True)
                response = {'version': VERSION, 'status': status}
            self.queue(client, response)
        except StopIteration:
            client.frames = None
            if not client.control:
                if not client.framer.buffer:
                    client.deadline = None
                elif client.deadline is None:
                    client.deadline = self.clock() + 2
        except CapacityError:
            if client.control:
                client.close_after = True
                self.queue(client, {'version': VERSION, 'result': 'rejected', 'code': 'capacity_exhausted'})
            else:
                self.drop(client, 'progress_capacity')
        except (Invalid, ProgressError, ValueError, RecursionError):
            if client.control:
                client.close_after = True
                self.queue(client, {'version': VERSION, 'result': 'rejected', 'code': 'invalid_control'})
            else:
                self.drop(client, 'protocol_failure')
        except sqlite3.Error:
            if getattr(client, 'health', False):
                self.health_failure = 'health_storage_failure'
                client.close_after = True
                self.queue(client, {'version': VERSION, 'result': 'rejected', 'code': 'health_storage_failure'})
                return
            self.failure = 'storage_failure'
            if self.reader is not None:
                self.drop(self.reader, 'storage_failure')
            if client.sock in self.clients:
                self.drop(client, 'storage_failure')

    def run_once(self):
        events = self.selector.select(.1)
        events.sort(key=lambda item: 0 if item[0].data == 'control' or
                    (isinstance(item[0].data, Client) and item[0].data.control and not item[0].data.health)
                    else 2 if item[0].data == 'health' or
                    (isinstance(item[0].data, Client) and item[0].data.health) else 1)
        for key, mask in events:
            if self.stopped():
                break
            client = key.data
            if client in ('control', 'data', 'health'):
                self.accept(key.fileobj, client != 'data', client == 'health')
                continue
            if client.sock not in self.clients:
                continue
            try:
                if mask & selectors.EVENT_WRITE:
                    count = client.sock.send(client.output)
                    if count <= 0:
                        self.drop(client)
                        continue
                    client.output = client.output[count:]
                    if not client.output:
                        if client.close_after:
                            self.drop(client)
                        else:
                            client.deadline = None
                            self.selector.modify(client.sock, selectors.EVENT_READ, client)
                            self.advance(client)
                else:
                    chunk = client.sock.recv(4096)
                    if not chunk:
                        self.drop(client, 'partial_frame' if client.framer.buffer else 'stream_disconnected')
                        continue
                    client.frames = client.framer.feed(chunk)
                    self.advance(client)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                self.drop(client)
        now = self.clock()
        for client in list(self.clients.values()):
            if client.deadline is not None and now >= client.deadline:
                self.drop(client, 'deadline')

    def run(self):
        try:
            while not self.stopped():
                self.run_once()
        finally:
            self.close()
        return 1 if self.failure else 0

    def close(self):
        if self.closed:
            return
        self.closed = True
        for client in list(self.clients.values()):
            self.drop(client, 'service_shutdown')
        try:
            self.runtime.interrupt('service_shutdown')
        except Exception:
            self.failure = 'storage_failure'
        finally:
            self.selector.close()


def main():
    parser = argparse.ArgumentParser(description='HIDS M3 ingestion with root-controlled activation')
    parser.add_argument('--config', default='/etc/hids/m3.json')
    args = parser.parse_args()
    runtime = endpoint = control = service = health_endpoint = None
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    try:
        if sys.platform != 'linux':
            raise PermissionError('linux_required')
        reader, ingest, ipc = identities()
        if (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (ingest.pw_uid, ingest.pw_uid, ingest.pw_gid, ingest.pw_gid):
            raise PermissionError('ingestion_identity_required')
        if set(os.getgroups()) | {os.getgid()} != {ingest.pw_gid, ipc}:
            raise PermissionError('supplementary_groups')
        config = load_config(args.config)
        _directory(Path('/run/hids'), 0, 0, 0o755)
        control = systemd_control_listener('/run/hids/m3/control.sock')
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, stop)
        runtime = Runtime('/var/lib/hids/m3', config['source_id'],
                          max_activations=config['max_activations'], max_pages=config['max_pages'],
                          position_limit=config['position_limit'])
        endpoint = open_data_listener('/run/hids/m3/ingest/audit.sock', ingest.pw_uid, ipc)
        try:
            health_endpoint = open_data_listener('/run/hids/m3/health/metrics.sock', ingest.pw_uid, ipc)
        except (OSError, PermissionError):
            print('m3_health_endpoint_unavailable', file=sys.stderr)
        service = Service(runtime, endpoint.sock, control, PeerPolicy(reader.pw_uid, reader.pw_gid),
                          health_listener=health_endpoint.sock if health_endpoint else None,
                          stopped=lambda: stopping)
        if health_endpoint is None:
            service.health_failure = "health_endpoint_unavailable"
        return service.run()
    except Exception:
        print('m3_ingestion_startup_or_runtime_failure', file=sys.stderr)
        return 1
    finally:
        if service:
            service.close()
        if endpoint:
            endpoint.close()
        if health_endpoint:
            health_endpoint.close()
        if control:
            control.close()
        if runtime:
            runtime.close()


if __name__ == '__main__':
    raise SystemExit(main())
