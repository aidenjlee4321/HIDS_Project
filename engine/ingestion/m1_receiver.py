"""Explicitly harness-launched Linux synthetic receiver; no service/HTTP interface."""
from __future__ import annotations

import os
from pathlib import Path
import select
import signal
import socket
import time

from engine.database.m1_store import Store
from engine.ingestion.m1_contract import Framer, Invalid, decode, frame, keys, utc_now, uuid_valid, validate_event
from engine.ingestion.m1_io import control_read, control_write, ready, write_all
from engine.ingestion.m1_security import peer_matches, private_directory, private_file


def receiver_main(directory, control_fd, report_fd, fault=lambda stage: None, response_hook=lambda response: response, case_deadline=None):
    """Fault callable is an in-process test seam; never supplied over event IPC."""
    os.umask(0o077)
    stopped = False
    listener = store = connection = None
    owned = None
    path = Path(directory) / "events.sock"
    case_deadline = time.monotonic() + 120 if case_deadline is None else case_deadline

    def stop(_sig, _frame):
        nonlocal stopped
        stopped = True

    def report(stage, **values):
        control_write(report_fd, {"stage": stage, **values})

    def terminal(kind, event_id, code, error=None):
        nonlocal listener
        if listener is not None:
            listener.close()
            listener = None
        try:
            write_all(connection.fileno(), frame({"protocol_version": 1, "message_type": kind,
                      "event_id": event_id, "code": code}), time.monotonic() + 5)
        except (OSError, TimeoutError):
            pass
        details = {}
        if error is not None:
            details["reason"] = type(error).__name__
            for attr in ("errno", "sqlite_errorcode"):
                value = getattr(error, attr, None)
                if type(value) is int:
                    details[attr] = value
        report("terminal_failure", code=code, **details)
        return 1

    try:
        os.set_blocking(control_fd, False)
        os.set_blocking(report_fd, False)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, stop)
        private_directory(directory, require_linux=True)
        store = Store(Path(directory) / "pilot.sqlite", fault=fault, cancelled=lambda: stopped)
        if os.path.lexists(path) or len(os.fsencode(path)) >= 108:
            raise PermissionError("socket_path_unavailable")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
        if listener.get_inheritable():
            raise PermissionError("cloexec_required")
        listener.bind(str(path))
        os.chmod(path, 0o600)
        info = private_file(path, socket_file=True)
        owned = (info.st_dev, info.st_ino)
        listener.listen(1)
        if time.monotonic() >= case_deadline:
            raise TimeoutError("case_deadline")
        report("startup_ready")
    except BaseException as exc:
        try:
            report("startup_failure", reason=type(exc).__name__)
        except (OSError, TimeoutError):
            pass
        if listener is not None:
            listener.close()
        if store is not None:
            store.close()
        if owned is not None and path.exists():
            info = path.lstat()
            if (info.st_dev, info.st_ino) == owned:
                path.unlink()
        return 1

    expected_pid = None
    try:
        while not stopped and time.monotonic() < case_deadline:
            readable, _, _ = select.select([control_fd, listener], [], [], .1)
            if control_fd in readable:
                try:
                    command = control_read(control_fd)
                except EOFError:
                    break
                if command.get("command") == "stop":
                    keys(command, "command")
                    break
                keys(command, "command pid")
                if command["command"] != "peer" or type(command["pid"]) is not int or not 1 <= command["pid"] <= 2147483647:
                    raise ValueError("bad_control_policy")
                expected_pid = command["pid"]
                report("peer_policy_ready")
            if listener not in readable:
                continue
            try:
                connection, _ = listener.accept()
            except (BlockingIOError, InterruptedError):
                continue
            connection.setblocking(False)
            if expected_pid is None or not peer_matches(connection, expected_pid):
                connection.close()
                connection = None
                report("peer_denied")
                continue
            framer = Framer()
            deadline = min(case_deadline, time.monotonic() + 5)
            event_id = None
            try:
                while not stopped:
                    ready(connection.fileno(), False, deadline, lambda: stopped)
                    try:
                        chunk = connection.recv(4096)
                    except (BlockingIOError, InterruptedError):
                        continue
                    if not chunk:
                        break  # Partial frame discarded, without DB work.
                    for payload in framer.feed(chunk):
                        event_id = None
                        obj = decode(payload)
                        if uuid_valid(obj.get("event_id")):
                            event_id = obj["event_id"]
                        validate_event(obj)
                        try:
                            received = utc_now()
                            result = store.put(obj, received)
                        except Invalid as exc:
                            if exc.code in ("id_conflict", "capacity_exceeded"):
                                return terminal("reject", event_id, exc.code)
                            return terminal("error", event_id, "storage_error", exc)
                        except Exception as exc:
                            return terminal("error", event_id, "storage_error", exc)
                        response = {"protocol_version": 1, "message_type": "ack", "event_id": event_id, "result": result}
                        try:
                            injected = response_hook(response)
                            wire = injected if type(injected) is bytes else frame(injected)
                            if len(wire) > 513:
                                raise ValueError("response_limit")
                        except OSError:
                            raise  # Internal test seam for a plain lost-ACK disconnect.
                        except Exception:
                            listener.close()
                            listener = None
                            report("terminal_failure", code="response_encoding_failed")
                            return 1  # Already committed: never send a rejection now.
                        write_all(connection.fileno(), wire, min(case_deadline, time.monotonic() + 5), lambda: stopped)
                        event_id = None
                        deadline = min(case_deadline, time.monotonic() + 5)
            except Invalid as exc:
                return terminal("reject", event_id, exc.code)
            except (OSError, EOFError, TimeoutError):
                pass  # Transport failure alone permits a bounded reconnect.
            finally:
                connection.close()
                connection = None
        if time.monotonic() >= case_deadline:
            report("terminal_failure", code="case_deadline")
            return 1
        report("stopped")
        return 0
    except Exception as exc:
        report("terminal_failure", code="control_or_receiver_failure", reason=type(exc).__name__)
        return 1
    finally:
        if connection is not None:
            connection.close()
        if listener is not None:
            listener.close()
        store.close()
        if owned is not None and path.exists():
            info = private_file(path, socket_file=True)
            if (info.st_dev, info.st_ino) == owned:
                path.unlink()
