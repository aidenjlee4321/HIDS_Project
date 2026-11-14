"""Root-only terminal client. Install/run using isolated Python and trusted path."""
import json
import os
import pwd
from pathlib import Path
import socket
import stat
import struct
import sys
from api.dashboard_service import config, CONTROL
from api.pilot_service import trusted
from api.pilot_sessions import Denied, closed_json, digest


def request(operation):
    if os.getuid() != 0 or os.geteuid() != 0 or operation not in ('mint','revoke_all'):
        raise Denied()
    cfg = config()
    parent = Path(CONTROL).parent
    info = parent.lstat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700 or not stat.S_ISDIR(info.st_mode):
        raise Denied()
    info = Path(CONTROL).lstat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or not stat.S_ISSOCK(info.st_mode):
        raise Denied()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        sock.connect(CONTROL)
        _, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
        # systemd initially owns listen(); asyncio can call listen() again
        # under the designated backend UID. Both are trusted for this root-
        # protected pathname; no other user is an authorized server.
        if uid not in (0, pwd.getpwnam('hids-ingest').pw_uid):
            raise Denied()
        sock.sendall(json.dumps({'version':1,'operation':operation}).encode()+b'\n')
        sock.shutdown(socket.SHUT_WR)
        data = bytearray()
        while True:
            chunk = sock.recv(4097-len(data))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 4096:
                raise Denied()
    value = closed_json(data, {'version','url'} if operation == 'mint' else {'version','revoked'})
    if type(value['version']) is not int or value['version'] != 1:
        raise Denied()
    if operation == 'mint':
        prefix = 'https://127.0.0.1:'+str(cfg['port'])+'/#grant='
        url = value['url']
        if not isinstance(url,str) or not url.startswith(prefix):
            raise Denied()
        digest(url[len(prefix):])
        return url
    if value['revoked'] is not True:
        raise Denied()
    return 'All dashboard sessions revoked.'


def main():
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ('mint','revoke_all') or not sys.stdout.isatty():
            raise Denied()
        print(request(sys.argv[1]))
    except Exception:
        print('HIDS access request denied', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
