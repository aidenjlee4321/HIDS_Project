"""Bounded private test-control pipes and nonblocking socket writes."""
import errno
import os
import select
import time

from engine.ingestion.m1_contract import Invalid, decode, frame


def ready(fd, writing, deadline, stopped=lambda: False):
    while not stopped():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("io_deadline")
        try:
            read, write, _ = select.select([] if writing else [fd], [fd] if writing else [], [], min(remaining, .1))
            if read or write:
                return
        except InterruptedError:
            continue
    raise InterruptedError("shutdown_requested")


def write_all(fd, data, deadline, stopped=lambda: False):
    offset = 0
    while offset < len(data):
        ready(fd, True, deadline, stopped)
        try:
            count = os.write(fd, data[offset:])
        except OSError as exc:
            if exc.errno in (errno.EINTR, errno.EAGAIN, errno.EWOULDBLOCK):
                continue
            raise
        if count <= 0:
            raise BrokenPipeError("zero_write")
        offset += count


def read_line(fd, limit, deadline, stopped=lambda: False):
    """Control pipes only: single-byte reads cannot consume the next control line."""
    data = bytearray()
    while True:
        ready(fd, False, deadline, stopped)
        try:
            byte = os.read(fd, 1)
        except BlockingIOError:
            continue
        except InterruptedError:
            continue
        if not byte:
            raise EOFError("control_closed")
        if byte == b"\n":
            return bytes(data)
        if len(data) == limit:
            raise Invalid("frame_too_large")
        data.extend(byte)


def control_read(fd, timeout=5):
    return decode(read_line(fd, 512, time.monotonic() + timeout), 512)


def control_write(fd, obj):
    write_all(fd, frame(obj), time.monotonic() + 5)
