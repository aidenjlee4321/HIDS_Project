"""Approved, closed synthetic M1 contract. No native source collection."""
from __future__ import annotations

import datetime as dt
import json
import math
import re

EVENT_LIMIT = 65536
RESPONSE_LIMIT = 512
CONTRACT = "m1.process-exec/0.1.0"
REJECTIONS = frozenset({"invalid_json", "invalid_event", "unsupported_version",
                        "frame_too_large", "id_conflict", "capacity_exceeded"})
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z")


class Invalid(ValueError):
    def __init__(self, code="invalid_event"):
        self.code = code
        super().__init__(code)


def uuid_valid(value):
    return type(value) is str and UUID.fullmatch(value) is not None


def timestamp(value):
    if type(value) is not str or not STAMP.fullmatch(value):
        raise Invalid()
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise Invalid() from exc


def utc_now():
    now = dt.datetime.now(dt.timezone.utc)
    value = (f"{now.year:04d}-{now.month:02d}-{now.day:02d}T{now.hour:02d}:"
             f"{now.minute:02d}:{now.second:02d}.{now.microsecond:06d}Z")
    timestamp(value)
    return value


def keys(obj, expected):
    if type(obj) is not dict or set(obj) != set(expected.split()):
        raise Invalid()


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Invalid()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid("invalid_json")
        result[key] = value
    return result


def _constant(_value):
    raise Invalid("invalid_json")


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise Invalid("invalid_json")
    return result


def _strings(value):
    if type(value) is str:
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise Invalid("invalid_json")
        if len(value) > 256 or not value.isascii():
            raise Invalid()
    elif type(value) is dict:
        for key, child in value.items():
            _strings(key)
            _strings(child)
    elif type(value) is list:
        for child in value:
            _strings(child)


def decode(payload, limit=EVENT_LIMIT):
    """Bound bytes/depth before stdlib parsing; never accept duplicate keys."""
    if len(payload) > limit:
        raise Invalid("frame_too_large")
    if not payload or any(c in payload for c in (b"\r", b"\n")) or payload.startswith(b"\xef\xbb\xbf"):
        raise Invalid("invalid_json")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise Invalid("invalid_json") from exc
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 8:
                raise Invalid("invalid_json")
        elif char in "]}":
            depth -= 1
    try:
        result = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, Invalid):
            raise
        raise Invalid("invalid_json") from exc
    _strings(result)
    if type(result) is not dict:
        raise Invalid()
    return result


def validate_native(obj):
    keys(obj, "what what_code pid tgid parent cpu connector_sequence timestamp_ns timestamp_unit timestamp_clock")
    for key, value in {"what": "PROC_EVENT_EXEC", "timestamp_unit": "ns",
                       "timestamp_clock": "linux.cn_proc.timestamp_ns"}.items():
        if obj[key] != value:
            raise Invalid()
    integer(obj["what_code"], 2, 2)
    integer(obj["pid"], 1, 2147483647)
    integer(obj["tgid"], 1, 2147483647)
    integer(obj["cpu"], 0, 4294967295)
    integer(obj["connector_sequence"], 0, 4294967295)
    if obj["parent"] is not None:
        raise Invalid()
    raw = obj["timestamp_ns"]
    if type(raw) is not str or not re.fullmatch(r"0|[1-9][0-9]{0,19}", raw) or int(raw) > 2**64 - 1:
        raise Invalid()


def validate_event(obj):
    _strings(obj)
    if type(obj) is not dict:
        raise Invalid()
    for field, kind, supported in (("protocol_version", int, 1),
                                   ("contract_version", str, CONTRACT),
                                   ("ecs_reference_version", str, "9.5.0")):
        if type(obj.get(field)) is not kind:
            raise Invalid()
        if obj[field] != supported:
            raise Invalid("unsupported_version")
    keys(obj, "protocol_version message_type contract_version ecs_reference_version event_id producer_instance_id source native timestamps")
    if obj["message_type"] != "event" or not all(uuid_valid(obj[k]) for k in ("event_id", "producer_instance_id")):
        raise Invalid()
    source = obj["source"]
    keys(source, "adapter mode fixture_id boot_id")
    if source != {"adapter": "linux.cn_proc", "mode": "sanitized_fixture",
                  "fixture_id": "synthetic-exec-001", "boot_id": None}:
        raise Invalid()
    validate_native(obj["native"])
    clocks = obj["timestamps"]
    keys(clocks, "activity_wall_time activity_wall_time_reason observed_at observation")
    if (clocks["activity_wall_time"] is not None or
        clocks["activity_wall_time_reason"] != "not_emitted_by_source" or
        clocks["observation"] != "fixture_decode"):
        raise Invalid()
    timestamp(clocks["observed_at"])
    return obj


def canonical(obj):
    validate_event(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def frame(obj, limit=RESPONSE_LIMIT):
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(data) > limit:
        raise Invalid("frame_too_large")
    return data + b"\n"


class Framer:
    """One capped payload accumulator; LF is consumed without appending."""
    def __init__(self, limit=EVENT_LIMIT):
        self.limit = limit
        self.buffer = bytearray()

    def feed(self, chunk):
        for byte in chunk:
            if byte == 10:
                result = bytes(self.buffer)
                self.buffer.clear()
                yield result
            else:
                if len(self.buffer) == self.limit:
                    raise Invalid("frame_too_large")
                self.buffer.append(byte)
