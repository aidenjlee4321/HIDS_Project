"""Explicit-root dashboard HTTPS service. Fixed stores, independently frozen families.

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

CONFIG=Path('/etc/hids/dashboard.json')
INSTALL=Path('/opt/hids-dashboard')
CONTROL='/run/hids-dashboard/control.sock'
TLS=Path('/etc/hids/dashboard-tls')


def config():
    for p in ('/etc','/etc/hids'):trusted(p,True)
    trusted(CONFIG)
    if CONFIG.stat().st_size>2048:raise Denied()
    value=closed_json(CONFIG.read_bytes(),{'version','mode','port','process','history','tls_generation','certificate_sha256'})
    if type(value['version']) is not int or value['version']!=1 or value['mode']!='frozen-dashboard' or type(value['port']) is not int or value['port']!=18765:raise Denied()
    from engine.ingestion.m1_contract import uuid_valid
    from api.process_view import selection
    if not uuid_valid(value['tls_generation']) or type(value['certificate_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',value['certificate_sha256']):raise Denied()
    for family,field in [('process','selected'),('history','bindings')]:
        part=value[family]
        if part is None:continue
        if type(part) is not dict or set(part)!={'identity',field}:raise Denied()
        identity=part['identity']
        if type(identity) is not list or len(identity)!=2 or any(type(n) is not int or n<0 for n in identity):raise Denied()
        if family=='process':selection(part['selected'])
        elif type(part['bindings']) is not list or not 1<=len(part['bindings'])<=2 or any(type(k) is not str or not re.fullmatch('[0-9a-f]{64}',k) for k in part['bindings']) or len(set(part['bindings']))!=len(part['bindings']):raise Denied()
    return value



async def run():
    import uvicorn
    from api.history_view import load_view as history_load
    from api.process_view import load_view as process_load
    from api.dashboard_app import make_app
    cfg=config();backend=pwd.getpwnam('hids-ingest')
    socks=listeners(cfg['port'],control_path=CONTROL)
    certdir=TLS/cfg['tls_generation']
    def tls():return validated_context(certdir/'leaf.pem',certdir/'leaf.key',cfg['certificate_sha256'],backend.pw_gid)
    ctx=tls()
    def family(name,path,loader,field):
        part=cfg[name]
        if part is None:return None
        try:
            if not os.statvfs(path).f_flag&os.ST_RDONLY:raise Denied()
            return loader(part[field],part['identity'])
        except Exception:return None
    process=family('process','/var/lib/hids/process',process_load,'selected')
    history=family('history','/var/lib/hids/m4/store',history_load,'bindings')
    class DashboardSessions(Sessions):
        def mint(self):
            tls()  # Never mint into an expired/replaced/unsafe TLS configuration.
            return super().mint()
    state=DashboardSessions(scope='dashboard:read')
    app,state=make_app('127.0.0.1:18765',INSTALL/'assets',process,history,state)
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
        print('HIDS dashboard refused or stopped',file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
