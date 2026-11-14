"""D-12b synthetic pilot: bounded volatile root grants and read-only sessions."""
import base64
import hashlib
import json
import math
import re
import secrets
import threading
import time

TOKEN = re.compile(r'[A-Za-z0-9_-]{43}\Z')


class Denied(Exception):
    """Deliberately carries no attacker-controlled or secret diagnostic."""


def digest(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise Denied()
    try:
        raw = base64.urlsafe_b64decode(value + '=')
    except Exception:
        raise Denied() from None
    if base64.urlsafe_b64encode(raw).decode().rstrip('=') != value:
        raise Denied()
    return hashlib.sha256(raw).digest()


def closed_json(data, keys):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Denied()
            out[k] = v
        return out
    try:
        result = json.loads(data, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(Denied()))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Denied() from None
    if not isinstance(result, dict) or set(result) != set(keys):
        raise Denied()
    return result


class Sessions:
    GRANT_SECONDS = 60
    IDLE_SECONDS = 300
    ABSOLUTE_SECONDS = 1800
    CAPACITY = 4

    def __init__(self, *, clock=time.monotonic, random=secrets.token_bytes, scope='pilot:read'):
        if scope not in ('pilot:read','history:read','setup:draft','dashboard:read'):raise Denied()
        self.scope=scope
        self._clock, self._random = clock, random
        self._lock = threading.Lock()
        self._grants, self._sessions = {}, {}
        self._last = -math.inf

    def _now(self):
        now = self._clock()
        if not isinstance(now, (int, float)) or not math.isfinite(now) or now < self._last:
            self._grants.clear()
            self._sessions.clear()
            raise Denied()
        self._last = now
        return now

    def _prune(self, now):
        self._grants = {k:v for k,v in self._grants.items() if now < v}
        self._sessions = {k:v for k,v in self._sessions.items()
                          if now < v[0] + self.ABSOLUTE_SECONDS and now < v[1] + self.IDLE_SECONDS}

    def _new(self):
        try:
            raw = self._random(32)
            if type(raw) is not bytes or len(raw) != 32:
                raise Denied()
            token = base64.urlsafe_b64encode(raw).decode().rstrip('=')
            key = digest(token)
            if key in self._grants or key in self._sessions:
                raise Denied()
            return token, key
        except Exception:
            raise Denied() from None

    def mint(self):
        with self._lock:
            now = self._now()
            self._prune(now)
            if len(self._grants) + len(self._sessions) >= self.CAPACITY:
                raise Denied()
            token, key = self._new()
            self._grants[key] = now + self.GRANT_SECONDS
            return token

    def redeem(self, grant):
        key = digest(grant)
        with self._lock:
            now = self._now()
            self._prune(now)
            if key not in self._grants:
                raise Denied()
            # Generate while the grant is still indexed: a broken RNG cannot
            # turn a bootstrap into the same session credential.
            try:
                token, session_key = self._new()
            finally:
                del self._grants[key]
            self._sessions[session_key] = (now, now, self.scope)
            return token

    def authorize(self, token, scope='pilot:read'):
        key = digest(token)
        with self._lock:
            now = self._now()
            self._prune(now)
            record = self._sessions.get(key)
            if record is None or record[2] != scope:
                raise Denied()
            self._sessions[key] = (record[0], now, record[2])

    def logout(self, token):
        key = digest(token)
        with self._lock:
            now = self._now()
            self._prune(now)
            if key not in self._sessions:
                raise Denied()
            del self._sessions[key]

    def revoke_all(self):
        with self._lock:
            self._grants.clear()
            self._sessions.clear()

    def housekeeping(self):
        with self._lock:
            self._prune(self._now())
