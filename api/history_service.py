"""Manual D-12c HTTPS service. Fixed store, root-selected identity and bindings.

The service requires the documented systemd read-only mount boundary. No installer,
collector, writer, renewal or default enablement is invoked here.
"""
import asyncio
import os
from pathlib import Path
import pwd
import re
import sys
from api.pilot_service import trusted, Control, listeners
from api.pilot_sessions import Sessions, Denied, closed_json
from api.tls_leaf import validated_context

CONFIG=Path('/etc/hids/dashboard-history.json')
INSTALL=Path('/opt/hids-dashboard-history')
CONTROL='/run/hids-dashboard-history/control.sock'
CERT=Path('/etc/hids/dashboard-history-tls/leaf.pem')
KEY=Path('/etc/hids/dashboard-history-tls/leaf.key')


def config():
    for p in ('/etc','/etc/hids'):trusted(p,True)
    trusted(CONFIG)
    if CONFIG.stat().st_size>2048:raise Denied()
    value=closed_json(CONFIG.read_bytes(),{'version','mode','port','identity','bindings','certificate_sha256'})
    if (type(value['version']) is not int or value['version']!=1 or value['mode']!='frozen-history'
        or type(value['port']) is not int or value['port']!=18765
        or type(value['identity']) is not list or len(value['identity'])!=2 or any(type(n) is not int or n<0 for n in value['identity'])
        or type(value['bindings']) is not list or not 1<=len(value['bindings'])<=2 or len(set(value['bindings']))!=len(value['bindings'])
        or any(type(b) is not str or not re.fullmatch('[0-9a-f]{64}',b) for b in value['bindings'])
        or type(value['certificate_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',value['certificate_sha256'])):raise Denied()
    return value


async def run():
    import uvicorn
    from api.history_view import load_view
    from api.history_app import make_app
    cfg=config();backend=pwd.getpwnam('hids-ingest')
    socks=listeners(cfg['port'],control_path=CONTROL)
    def tls():return validated_context(CERT,KEY,cfg['certificate_sha256'],backend.pw_gid)
    ctx=tls()
    # Refuse a writable production mapping. This also protects against a manual
    # invocation that bypasses the service's read-only bind mount.
    if not os.statvfs('/var/lib/hids/m4/store').f_flag&os.ST_RDONLY:raise Denied()
    try:view=load_view(cfg['bindings'],cfg['identity'])
    except Exception:view=None
    class HistorySessions(Sessions):
        def mint(self):
            if view is None:raise Denied()
            tls()  # Never mint into an expired/replaced/unsafe TLS configuration.
            return super().mint()
    state=HistorySessions(scope='history:read')
    app,state=make_app('127.0.0.1:18765',INSTALL/'assets',view,state)
    config_server=uvicorn.Config(app,access_log=False,log_config=None,log_level='critical',proxy_headers=False,server_header=False,date_header=False,workers=1,reload=False,timeout_keep_alive=2,timeout_graceful_shutdown=3,limit_concurrency=16,h11_max_incomplete_event_size=8192)
    config_server.load();config_server.ssl=ctx
    server=uvicorn.Server(config_server)
    task=asyncio.create_task(server.serve(sockets=[socks['http']]))
    unix=await asyncio.start_unix_server(Control(state,'https://127.0.0.1:18765',lambda:server.started and not server.should_exit).handle,sock=socks['control'],limit=4096,cleanup_socket=False)
    try:
        while not task.done():state.housekeeping();await asyncio.sleep(1)
        await task
    finally:
        state.revoke_all();unix.close();await unix.wait_closed();server.should_exit=True
        if not task.done():await task


def main():
    try:
        if len(sys.argv)!=1 or os.environ.get('WEB_CONCURRENCY','1')!='1' or 'UVICORN_RELOAD' in os.environ:raise Denied()
        asyncio.run(run())
    except Exception:
        print('HIDS history view refused or stopped',file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
