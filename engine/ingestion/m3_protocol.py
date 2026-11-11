"""Closed M3 request framing for an externally authenticated reader lease."""

import json

from engine.ingestion.m3_progress import ProgressError

REQUEST_LIMIT = 65536
VERSION = 3
SCOPE_FIELDS = {"activation", "generation", "lease"}


def _object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ProgressError("duplicate JSON key")
    return result


def parse_request(raw, scope):
    """Validate framing and scope after the caller authenticates the peer."""
    if scope.keys() != SCOPE_FIELDS or any(type(value) is not str or not value for value in scope.values()):
        raise ProgressError("invalid receiver scope")
    if not 0 < len(raw) <= REQUEST_LIMIT or not raw.endswith(b"\n"):
        raise ProgressError("invalid request framing")
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    except (ValueError, RecursionError):
        raise ProgressError("invalid JSON request") from None
    if type(request) is not dict or type(request.get("version")) is not int:
        raise ProgressError("invalid request")
    if request["version"] != VERSION or any(
        type(request.get(key)) is not str or request[key] != value
        for key, value in scope.items()
    ):
        raise ProgressError("invalid request scope")
    return request


def dispatch_request(request, ledger, *, require_boundary=False):
    op = request.get("op")
    if op == 'boundary' and request.keys() == SCOPE_FIELDS | {'version', 'op'}:
        return ledger.start_stream()
    if require_boundary and not ledger.stream_started():
        raise ProgressError('source boundary required')
    common = SCOPE_FIELDS | {"version", "op", "identity"}
    identity = request.get("identity")
    if type(identity) is not str:
        raise ProgressError("invalid request identity")
    if op == "register" and request.keys() == common | {"begin", "end", "eoe"}:
        return ledger.register(identity, request["begin"], request["end"], eoe=request["eoe"])
    if op == 'resource' and request.keys() == common | {'evidence'}:
        return ledger.resource(identity, request['evidence'])
    if op == "accept" and request.keys() == common | {"execution"}:
        return ledger.accept(identity, request["execution"])
    if op == "reject" and request.keys() == common:
        ledger.reject(identity)
        return "rejected"
    if op == 'timeout' and request.keys() == common | {'evidence'}:
        return ledger.timeout(identity, request['evidence'])
    raise ProgressError("unknown request")


def dispatch(raw, ledger, scope, *, require_boundary=False):
    return dispatch_request(parse_request(raw, scope), ledger, require_boundary=require_boundary)
