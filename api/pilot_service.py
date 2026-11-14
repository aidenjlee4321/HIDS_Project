"""Manual synthetic pilot, named root-created listeners, no collection access."""
import asyncio
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import struct
import sys
from api.pilot_sessions import Denied, closed_json

CONFIG = Path('/etc/hids/dashboard-pilot.json')
CONTROL = '/run/hids-dashboard-pilot/control.sock'
INSTALL = Path('/opt/hids-dashboard-pilot')


def trusted(path, directory=False):
    info = Path(path).lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise Denied()


def config():
    for p in ('/etc', '/etc/hids'):
        trusted(p, True)
    trusted(CONFIG)
    if CONFIG.stat().st_size > 1024:
        raise Denied()
    value = closed_json(CONFIG.read_bytes(), {'version','synthetic_only','port'})
    if type(value['version']) is not int or value['version'] != 1 or value['synthetic_only'] is not True or type(value['port']) is not int or not 1024 <= value['port'] <= 65535:
        raise Denied()
    return value


def listeners(port, *, control_path=CONTROL):
    if os.getuid() != pwd.getpwnam('hids-ingest').pw_uid or os.geteuid() != os.getuid():
        raise Denied()
    if (os.environ.get('LISTEN_PID') != str(os.getpid()) or os.environ.get('LISTEN_FDS') != '2'):
        raise Denied()
    names = os.environ.get('LISTEN_FDNAMES', '').split(':')
    if sorted(names) != ['control','http']:
        raise Denied()
    result = {}
    for fd,name in enumerate(names, 3):
        sock = socket.socket(fileno=fd)
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM or not sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
            raise Denied()
        if name == 'http' and (sock.family != socket.AF_INET or sock.getsockname() != ('127.0.0.1',port)):
            raise Denied()
        if name == 'control' and (sock.family != socket.AF_UNIX or sock.getsockname() != control_path):
            raise Denied()
        sock.set_inheritable(False)
        result[name] = sock
    for key in ('LISTEN_PID','LISTEN_FDS','LISTEN_FDNAMES'):
        os.environ.pop(key, None)
    return result


class Control:
    def __init__(self, state, origin, ready):
        self.state, self.origin, self.ready = state, origin, ready
        self.active = 0

    async def handle(self, reader, writer):
        counted = False
        try:
            peer = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
            _, uid, _ = struct.unpack('3i', peer)
            if uid != 0 or self.active >= 4 or not self.ready():
                raise Denied()
            self.active += 1
            counted = True
            data = await asyncio.wait_for(reader.readuntil(b'\n'), 2)
            if len(data) > 4096 or await asyncio.wait_for(reader.read(1), 2):
                raise Denied()
            value = closed_json(data, {'version','operation'})
            if type(value['version']) is not int or value['version'] != 1:
                raise Denied()
            if value['operation'] == 'mint':
                token = self.state.mint()
                out = {'version':1,'url':self.origin+'/#grant='+token}
            elif value['operation'] == 'revoke_all':
                self.state.revoke_all()
                out = {'version':1,'revoked':True}
            else:
                raise Denied()
            writer.write(json.dumps(out, separators=(',',':')).encode()+b'\n')
            await asyncio.wait_for(writer.drain(), 2)
        except Exception:
            # Neither protocol values nor credentials enter logs/errors.
            try:
                writer.write(b'{"error":"request denied"}\n')
                await asyncio.wait_for(writer.drain(), 1)
            except Exception:
                pass
        finally:
            if counted:
                self.active -= 1
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except Exception:
                pass


async def run():
    import uvicorn
    from api.pilot_app import make_app
    cfg = config()
    socks = listeners(cfg['port'])
    app, state = make_app('127.0.0.1:'+str(cfg['port']), INSTALL/'assets')
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_config=None,
        log_level='critical', proxy_headers=False, server_header=False, date_header=False,
        workers=1, reload=False, timeout_keep_alive=2, timeout_graceful_shutdown=3,
        limit_concurrency=16, h11_max_incomplete_event_size=8192))
    server_task = asyncio.create_task(server.serve(sockets=[socks['http']]))
    control = Control(state, 'http://127.0.0.1:'+str(cfg['port']), lambda:server.started and not server.should_exit)
    # systemd owns the pathname. Python must neither stat it through the
    # root-only directory nor unlink it on shutdown. Accept only via the fd.
    unix = await asyncio.start_unix_server(control.handle, sock=socks['control'], limit=4096, cleanup_socket=False)
    try:
        while not server_task.done():
            state.housekeeping()
            await asyncio.sleep(1)
        await server_task
    finally:
        state.revoke_all()
        unix.close()
        await unix.wait_closed()
        server.should_exit = True
        if not server_task.done():
            await server_task


def main():
    try:
        if len(sys.argv) != 1 or os.environ.get('WEB_CONCURRENCY', '1') != '1' or 'UVICORN_RELOAD' in os.environ:
            raise Denied()
        asyncio.run(run())
    except Exception:
        print('HIDS synthetic pilot refused or stopped', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
