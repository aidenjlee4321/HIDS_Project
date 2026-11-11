"""Exercise real producer/receiver process boundaries with synthetic records only."""

import json
import multiprocessing
import os
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from engine.ingestion.m3_progress import Progress
from engine.ingestion.m3_protocol import REQUEST_LIMIT, dispatch
from engine.ingestion.m3_receiver import Receiver

SCOPE = {
    "activation": "fixture-activation",
    "generation": "fixture-generation",
    "lease": "fixture-lease",
}

def run(producer, path, cutoff):
    ledger = Progress(path, "fixture-activation", "fixture-generation", 0)
    last = None
    try:
        with subprocess.Popen([producer], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
            try:
                while raw := child.stdout.readline(REQUEST_LIMIT + 1):
                    if cutoff == "before-commit" and json.loads(raw)["op"] == "accept":
                        child.kill()
                        break
                    reply = dispatch(raw, ledger, SCOPE)
                    if reply == "accepted":
                        last = json.loads(raw)
                        if cutoff == "after-commit":
                            child.kill()
                            break
                    child.stdin.write(reply.encode("ascii") + b"\n")
                    child.stdin.flush()
                assert child.wait(timeout=5) == (0 if cutoff is None else -9)
            finally:
                if child.poll() is None:
                    child.kill()
    finally:
        ledger.close()

    ledger = Progress(path, "fixture-activation", "fixture-generation", 0)
    try:
        ledger.recover()
        scanned, frontier = ledger.positions()
        assert scanned > 0 and frontier == scanned
        stored = ledger.db.execute("SELECT first_offset, payload FROM m3_execution").fetchall()
        if cutoff == "before-commit":
            assert not stored
        else:
            assert last is not None and len(stored) == 1 and stored[0][0] == 0
            assert json.loads(stored[0][1]) == last["execution"]
            assert ledger.accept(last["identity"], last["execution"]) == "duplicate"
    finally:
        ledger.close()


class SocketPairPeer:
    def check(self, connection):
        # Only the parent and its child hold the connected endpoints.
        pass


def run_socket(producer, path):
    ledger = Progress(path, SCOPE["activation"], SCOPE["generation"], 0)
    server, client = socket.socketpair()
    try:
        client.setblocking(False)
        with subprocess.Popen([producer, str(client.fileno())], pass_fds=(client.fileno(),)) as child:
            client.close()
            Receiver(ledger, SCOPE, SocketPairPeer()).serve(server)
            assert child.wait(timeout=5) == 0
        scanned, frontier = ledger.positions()
        assert scanned == frontier and scanned > 0
        payload, = ledger.db.execute("SELECT payload FROM m3_execution").fetchone()
        assert json.loads(payload)["comm_base64"] == "c2xlZXA="
    finally:
        server.close()
        client.close()
        ledger.close()


def crash_backend(connection, path, cutoff):
    class CrashProgress(Progress):
        def accept(self, identity, execution):
            if cutoff == "after-commit":
                super().accept(identity, execution)
            os.kill(os.getpid(), signal.SIGKILL)

    ledger = CrashProgress(path, SCOPE["activation"], SCOPE["generation"], 0)
    Receiver(ledger, SCOPE, SocketPairPeer()).serve(connection)


def run_backend_crash(producer, path, cutoff):
    server, client = socket.socketpair()
    backend = multiprocessing.get_context("spawn").Process(
        target=crash_backend, args=(server, path, cutoff))
    try:
        backend.start()
        server.close()
        client.setblocking(False)
        with subprocess.Popen([producer, str(client.fileno())],
                              pass_fds=(client.fileno(),)) as child:
            client.close()
            assert child.wait(timeout=5) == 2
        backend.join(5)
        assert backend.exitcode == -signal.SIGKILL
        ledger = Progress(path, SCOPE["activation"], SCOPE["generation"], 0)
        try:
            ledger.recover()
            scanned, frontier = ledger.positions()
            assert scanned == frontier > 0
            stored = ledger.db.execute("SELECT identity,payload FROM m3_execution").fetchall()
            if cutoff == "before-commit":
                assert not stored
                assert ledger.register("1794096000.123:100", scanned, scanned + 1) == "suppressed"
            else:
                assert len(stored) == 1
                identity, payload = stored[0]
                assert ledger.accept(identity, json.loads(payload)) == "duplicate"
        finally:
            ledger.close()
    finally:
        client.close()
        server.close()
        if backend.is_alive():
            backend.kill()
        backend.join(5)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        for index, cutoff in enumerate((None, "before-commit", "after-commit")):
            run(sys.argv[1], Path(directory) / f"{index}.sqlite", cutoff)
        run_socket(sys.argv[1], Path(directory) / "socket.sqlite")
        for cutoff in ("before-commit", "after-commit"):
            run_backend_crash(sys.argv[1], Path(directory) / f"backend-{cutoff}.sqlite", cutoff)
    print("PASS: Unix socket fixture, producer and backend kill before and after commit, recovery and deduplication")
