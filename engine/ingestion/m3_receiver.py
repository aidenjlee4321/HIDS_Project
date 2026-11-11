"""Bounded socket handling for one authenticated M3 plugin connection."""

import json
import socket
import threading
import time

from engine.ingestion.m2_receiver import Listener
from engine.ingestion.m3_progress import ProgressError
from engine.ingestion.m3_protocol import REQUEST_LIMIT, VERSION, dispatch


class Receiver:
    def __init__(self, ledger, scope, peer, *, timeout=2):
        self.ledger = ledger
        self.scope = dict(scope)
        self.peer = peer
        self.timeout = timeout
        self._lock = threading.Lock()
        self._active = True
        self._connected = False
        self._connection = None

    def revoke(self):
        with self._lock:
            self._active = False
            if self._connection is not None:
                try:
                    self._connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def serve(self, connection):
        """Run on the SQLite owner's thread. A disconnect ends this stream."""
        with connection:
            self.peer.check(connection)
            with self._lock:
                if not self._active or self._connected:
                    raise ProgressError("reader lease unavailable")
                self._connected = True
                self._connection = connection
            try:
                buffer = bytearray()
                deadline = None
                while True:
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        raise TimeoutError("partial request deadline")
                    connection.settimeout(remaining)
                    try:
                        chunk = connection.recv(4096)
                    except socket.timeout as error:
                        raise TimeoutError("partial request deadline") from error
                    if not chunk:
                        break
                    received = time.monotonic()
                    buffer.extend(chunk)
                    while (delimiter := buffer.find(b"\n")) >= 0:
                        with self._lock:
                            if not self._active:
                                raise ProgressError("reader lease revoked")
                            response = dispatch(bytes(buffer[:delimiter + 1]), self.ledger, self.scope)
                        del buffer[:delimiter + 1]
                        reply = json.dumps({"version": VERSION, "status": response})
                        connection.settimeout(self.timeout)
                        connection.sendall(reply.encode("ascii") + b"\n")
                        deadline = None
                    if len(buffer) >= REQUEST_LIMIT:
                        raise ProgressError("request frame too large")
                    if buffer and deadline is None:
                        deadline = received + self.timeout
                if buffer:
                    raise ProgressError("partial request at disconnect")
            finally:
                with self._lock:
                    self._active = False
                    self._connection = None
                self.ledger.recover()

    def serve_named(self, path, uid, ipc_gid, *, connect_timeout):
        """Serve one connection on an already authorized private runtime directory."""
        listener = Listener(path, uid, ipc_gid)
        try:
            listener.sock.settimeout(connect_timeout)
            connection, _ = listener.sock.accept()
            self.serve(connection)
        finally:
            listener.close()
