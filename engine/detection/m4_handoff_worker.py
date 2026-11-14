"""Root-configured synthetic acceptance worker. No production/live mode."""
import argparse
import errno
import json
import os
from pathlib import Path
import pwd
import signal
import stat
import sqlite3
import sys
import time

from engine.detection.m4_handoff import Source, Store, Worker, Invalid
from engine.detection.m4_pilot import load_json


def config(path):
    account=pwd.getpwnam('hids-ingest')
    if (os.getuid(),os.geteuid(),os.getgid(),os.getegid()) != (account.pw_uid,account.pw_uid,account.pw_gid,account.pw_gid):
        raise Invalid('backend service identity required')
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise Invalid('canonical lab config required')
    parent=path.parent
    info=parent.lstat();file=path.lstat()
    if (parent.parent!=Path('/var/tmp') or not parent.name.startswith('hids-m4-handoff.') or
            not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o711 or
            not stat.S_ISREG(file.st_mode) or file.st_uid!=0 or file.st_gid!=account.pw_gid or
            file.st_nlink!=1 or stat.S_IMODE(file.st_mode)!=0o640):raise Invalid('root private lab selection required')
    value=load_json(path)
    if (type(value) is not dict or value.keys()!={'version','lab_only','source','activation','generation','max_pages','storage'} or
            type(value['version']) is not int or value['version']!=1 or value['lab_only'] is not True):
        raise Invalid('synthetic lab configuration only')
    return parent,value


def isolation_probe(source):
    path=source.directory/(source.scope['activation']+'.sqlite')
    try:
        fd=os.open(path,os.O_WRONLY|os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno!=errno.EROFS:raise Invalid('source readonly mount not proven') from None
    else:
        os.close(fd);raise Invalid('source mount permits writes')
    with source.reader(path) as (db,_):
        try:db.execute('UPDATE m3_cursor SET frontier=frontier')
        except sqlite3.OperationalError as exc:
            if getattr(exc,'sqlite_errorcode',0)&255 != sqlite3.SQLITE_READONLY:raise Invalid('source SQL readonly denial not proven') from None
        else:raise Invalid('source SQL permits writes')
    for target in ('/var/lib/hids/m3','/run/hids/m3'):
        try:
            fd=os.open(target,os.O_RDONLY|os.O_DIRECTORY)
        except PermissionError:pass
        else:
            os.close(fd);raise Invalid('production M3 path not hidden')
    return dict(source_mount_readonly=True,source_sql_readonly=True,production_state_hidden=True,production_sockets_hidden=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-config',required=True,type=Path)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    try:
        root,value=config(args.lab_config)
        source=Source(root/'source',value['source'],value['activation'],value['generation'])
        isolation=isolation_probe(source)  # Fail closed outside the real sandbox.
        path=root/'state'/'destination'
        create=not path.exists()
        with Store(path,create=create,max_pages=value['max_pages'],storage=value['storage'],lab_only=True) as store:
            # Demo rules remain disabled; synthetic alert tests exercise the explicit library API.
            worker=Worker(store,[source])
            stopping=False
            def stop(*_):
                nonlocal stopping
                stopping=True
            signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
            while not stopping:
                status=worker.step()
                print(json.dumps(dict(status,isolation=isolation),sort_keys=True),flush=True)
                if args.once:
                    return 1 if any(v not in ('idle','imported') for v in status['bindings'].values()) else 0
                time.sleep(1)
        return 0
    except Exception:
        print(json.dumps(dict(lab_only=True,error='handoff_worker_failed')),file=sys.stderr,flush=True)
        return 1


if __name__=='__main__':raise SystemExit(main())
