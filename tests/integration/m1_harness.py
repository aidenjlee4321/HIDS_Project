"""Private same-user synthetic harness. No production service interface."""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from engine.database.m1_store import get_event
from engine.ingestion.m1_contract import EVENT_LIMIT, decode
from engine.ingestion.m1_io import control_read, control_write, read_line, write_all
from engine.ingestion.m1_receiver import receiver_main
from engine.ingestion.m1_security import ordinary_user, private_directory, private_file


def _receiver_child(directory, control, report, close_fds, fault, response_hook, case_deadline):
    for fd in close_fds:
        os.close(fd)
    code = receiver_main(directory, control, report, fault, response_hook, case_deadline)
    os.close(control)
    os.close(report)
    raise SystemExit(code)


def no_fault(_stage):
    pass


def identity_response(response):
    return response


class HarnessFailure(RuntimeError):
    pass


class M1Harness:
    def __init__(self, producer, fixture, fault=no_fault, directory=None, response_hook=identity_response):
        os.umask(0o077)
        ordinary_user()
        self.directory = Path(directory) if directory is not None else Path(tempfile.mkdtemp(prefix="hids-m1-", dir="/tmp"))
        private_directory(self.directory, require_linux=True)
        self.producer_binary = str(Path(producer).resolve())
        self.fixture = str(Path(fixture).resolve())
        self.receiver = self.producer = None
        self.control = self.reports = self.producer_control = self.producer_reports = None
        self.original = None
        self.operations = 0
        self.outcome = None
        self.socket_identity = None
        self.case_deadline = time.monotonic() + 120
        try:
            self.start_receiver(fault, response_hook)
        except BaseException:
            self.close()
            raise

    def start_receiver(self, fault=no_fault, response_hook=identity_response):
        if self.receiver is not None and self.receiver.is_alive():
            raise HarnessFailure("explicit_receiver_stop_required")
        if self.receiver is not None:
            self.receiver.join(5)
        for name in ("control", "reports"):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)
        socket_path = self.directory / "events.sock"
        if os.path.lexists(socket_path):
            info = private_file(socket_path, socket_file=True)
            if (info.st_dev, info.st_ino) != self.socket_identity:
                raise HarnessFailure("unexpected_stale_socket")
            socket_path.unlink()  # Exact previously recorded socket, after old child reaped.
        control_r, control_w = os.pipe()
        report_r, report_w = os.pipe()
        self.control, self.reports = control_w, report_r
        self.receiver = multiprocessing.get_context("fork").Process(
            target=_receiver_child,
            args=(str(self.directory), control_r, report_w, (control_w, report_r), fault, response_hook, self.case_deadline))
        self.receiver.start()
        os.close(control_r)
        os.close(report_w)
        os.set_blocking(control_w, False)
        os.set_blocking(report_r, False)
        response = control_read(report_r)
        if response.get("stage") != "startup_ready":
            self.receiver.join(5)
            raise HarnessFailure("startup_failure")
        info = private_file(socket_path, socket_file=True)
        self.socket_identity = (info.st_dev, info.st_ino)
        if self.producer is not None and self.producer.poll() is None:
            self.authorize(self.producer.pid)

    def authorize(self, pid):
        control_write(self.control, {"command": "peer", "pid": pid})
        if control_read(self.reports).get("stage") != "peer_policy_ready":
            raise HarnessFailure("peer_policy_failed")

    def start_producer(self, restore=False):
        if self.producer is not None and self.producer.poll() is None:
            raise HarnessFailure("producer_still_running")
        for name in ("producer_control", "producer_reports"):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)
        if restore and self.original is None:
            raise HarnessFailure("no_immutable_original")
        control_r, control_w = os.pipe()
        report_r, report_w = os.pipe()
        self.producer = subprocess.Popen(
            [self.producer_binary, self.fixture, str(self.directory / "events.sock"), str(control_r), str(report_w)],
            pass_fds=(control_r, report_w), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(control_r)
        os.close(report_w)
        self.producer_control, self.producer_reports = control_w, report_r
        os.set_blocking(control_w, False)
        os.set_blocking(report_r, False)
        control_write(control_w, {"command": "restore" if restore else "prepare"})
        if restore:
            write_all(control_w, self.original, time.monotonic() + 5)
        response = control_read(report_r)
        if response.get("stage") != "prepared":
            raise HarnessFailure("producer_local_failure")
        frozen = read_line(report_r, EVENT_LIMIT, time.monotonic() + 5) + b"\n"
        if restore and frozen != self.original:
            raise HarnessFailure("immutable_event_changed")
        self.original = frozen
        self.authorize(self.producer.pid)  # Held producer has not opened event socket yet.

    def send(self, explicit_retry=False):
        if self.original is None or self.producer is None or self.producer.poll() is not None:
            raise HarnessFailure("prepared_producer_required")
        if self.outcome == "acknowledged" or self.operations >= 2:
            raise HarnessFailure("retry_budget_or_pending_state")
        if bool(self.operations) != explicit_retry:
            raise HarnessFailure("explicit_retry_authorization_required")
        if time.monotonic() >= self.case_deadline:
            raise HarnessFailure("test_case_deadline")
        self.operations += 1
        control_write(self.producer_control, {"command": "send", "receiver_pid": self.receiver.pid})
        try:
            result = decode(read_line(self.producer_reports, 512, min(self.case_deadline, time.monotonic() + 35)), 512)
        except (OSError, EOFError, TimeoutError, ValueError):
            self.outcome = "unconfirmed"
            return {"outcome": "unconfirmed", "code": "producer_result_unavailable"}
        if result.get("outcome") not in {"acknowledged", "rejected", "unconfirmed", "local_failure"}:
            raise HarnessFailure("invalid_producer_result")
        if self.outcome == "unconfirmed" and result["outcome"] != "acknowledged":
            result["operation_outcome"] = result["outcome"]
            result["outcome"] = "unconfirmed"
        self.outcome = result["outcome"]
        return result

    def retrieve(self):
        obj = decode(self.original[:-1])
        result = get_event(self.directory / "pilot.sqlite", obj["event_id"])
        if result != obj:
            raise HarnessFailure("retrieval_failure")
        return result

    def stop_producer(self):
        if self.producer is not None and self.producer.poll() is None:
            try:
                control_write(self.producer_control, {"command": "stop"})
                self.producer.wait(timeout=5)
            except (OSError, TimeoutError, subprocess.TimeoutExpired):
                self.producer.terminate()
                try:
                    self.producer.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.producer.kill()
                    self.producer.wait(timeout=5)

    def stop_receiver(self):
        if self.receiver is not None:
            if self.receiver.is_alive():
                try:
                    control_write(self.control, {"command": "stop"})
                except (OSError, TimeoutError):
                    pass
                self.receiver.join(.5)
                if self.receiver.is_alive():
                    os.kill(self.receiver.pid, signal.SIGTERM)
                    self.receiver.join(5)
                if self.receiver.is_alive():
                    self.receiver.kill()
                    self.receiver.join(5)
                    raise HarnessFailure("receiver_cleanup_deadline_failed")
            self.receiver.join(5)

    def close(self):
        try:
            self.stop_producer()
        finally:
            try:
                self.stop_receiver()
            finally:
                for name in ("control", "reports", "producer_control", "producer_reports"):
                    fd = getattr(self, name)
                    if fd is not None:
                        os.close(fd)
                        setattr(self, name, None)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
