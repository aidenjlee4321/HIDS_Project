"""Root-selected bounded real-data import trial. Explicit opt-in rule plans; no OS setup."""
import argparse
import errno
import grp
import json
import os
from pathlib import Path
import pwd
import signal
import stat
import sys
import time

from engine.detection.m4_handoff import Source, Store, Worker, Invalid, private, scope_uuid
from engine.detection.m4_pilot import load_json
from engine.ingestion import m3_storage
from engine.detection.m4_rules import validate_references,load_rules

CONFIG = Path('/etc/hids/m4.json')
from engine.detection.m4_live import SOURCE_DIRECTORY,STATE_DIRECTORY,PAGES,POLICY,LiveSource,LiveStore


def validate_config(value):
    fields = {'version','enabled','source','activation','generation','max_pages','storage','max_events','max_seconds'}
    if type(value) is not dict or type(value.get('version')) is not int:
        raise Invalid('closed root selection required')
    if value['version']==2:fields=fields|{'rules'}
    if value.keys()!=fields:raise Invalid('closed root selection required')
    if value['version'] not in (1,2) or type(value['enabled']) is not bool:
        raise Invalid('invalid configuration version/enable')
    for field in ('source','activation','generation'): scope_uuid(value[field])
    if type(value['max_pages']) is not int or value['max_pages'] != PAGES:
        raise Invalid('approved page budget required')
    m3_storage.validate(value['storage'], PAGES, 1)
    if value['storage'] != POLICY:
        raise Invalid('approved real-data admission policy required')
    for field, bound in (('max_events',16),('max_seconds',120)):
        if type(value[field]) is not int or not 1 <= value[field] <= bound:
            raise Invalid('bounded trial scope required')
    if value['version']==2:validate_references(value['rules'])
    return value


def config():
    account = pwd.getpwnam('hids-ingest')
    if (os.getuid(),os.geteuid(),os.getgid(),os.getegid()) != (account.pw_uid,account.pw_uid,account.pw_gid,account.pw_gid):
        raise Invalid('backend identity required')
    if CONFIG != Path('/etc/hids/m4.json') or CONFIG.resolve() != CONFIG:
        raise Invalid('fixed configuration required')
    parent, file = CONFIG.parent.lstat(), CONFIG.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022 or
            not stat.S_ISREG(file.st_mode) or file.st_uid != 0 or file.st_gid != account.pw_gid or
            stat.S_IMODE(file.st_mode) != 0o640 or file.st_nlink != 1):
        raise Invalid('root private configuration required')
    ipc = grp.getgrnam('hids-ipc').gr_gid
    if ipc in os.getgroups(): raise Invalid('no reader IPC group required')
    return validate_config(load_json(CONFIG))


def isolation_probe(source,*,require_binding=True):
    if not os.statvfs(SOURCE_DIRECTORY).f_flag & os.ST_RDONLY:
        raise Invalid('source read-only namespace required')
    path = SOURCE_DIRECTORY / (source.scope['activation'] + '.sqlite')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno != errno.EROFS and (require_binding or exc.errno not in (errno.ENOENT,errno.EACCES)):
            raise Invalid('source mount denial not proven') from None
    else:
        os.close(fd); raise Invalid('source writes permitted')
    try:
        fd = os.open('/run/hids/m3', os.O_RDONLY | os.O_DIRECTORY)
    except PermissionError:
        pass
    else:
        os.close(fd); raise Invalid('M3 sockets must be hidden')
    if require_binding:source.read_page(limit=1)  # New imports always validate the full source binding.
    return dict(source_readonly=True, m3_sockets_hidden=True)


def run(once=False):
    value = config()
    if not value['enabled']:
        return dict(mode='disabled',lab_only=False), 0
    source = LiveSource(SOURCE_DIRECTORY,value['source'],value['activation'],value['generation'])
    isolation = isolation_probe(source,require_binding=value['version']==1 or not STATE_DIRECTORY.exists())
    private(STATE_DIRECTORY.parent,directory=True)
    if value['version']==2:
        from engine.detection.m4_rule_store import RuleStore
        store_type=RuleStore;rules=load_rules(value['rules'])
    else:store_type=LiveStore;rules=[]
    with store_type(create=not STATE_DIRECTORY.exists()) as store:
        bindings = {row[0] for row in store.db.execute('SELECT binding_key FROM m4h_bindings')}
        if value['version']==1 and bindings - {source.key}:raise Invalid('trial destination belongs to another selection')
        if value['version']==2:store.select_evaluations(source,rules)
        worker = Worker(store,[source],rules)
        def selected_count():
            return store.db.execute('SELECT count(*) FROM m4h_events WHERE binding_key=?',(source.key,)).fetchone()[0]
        deadline = time.monotonic() + value['max_seconds']
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        status = dict(store.summary(),mode='bounded_trial',isolation=isolation)
        while not stopping and time.monotonic() < deadline:
            remaining = value['max_events'] - selected_count()
            if remaining <= 0:
                if value['version']==2:store.evaluate_pending()
                status=dict(store.summary(),mode='bounded_trial',isolation=isolation,selected_events=selected_count())
                pending=store.binding_pending(source.key) if value['version']==2 else 0
                return dict(status,reason='event_limit' if not pending else 'pending',completed=not pending),0 if not pending else 2
            worker.page_limit = min(64,remaining)
            status = dict(worker.step(),mode='bounded_trial',isolation=isolation,selected_events=selected_count())
            if any(v not in ('idle','imported') for v in status['bindings'].values()):
                return dict(status,reason='blocked'),1
            if once: return dict(status,reason='single_round',completed=selected_count()>=value['max_events']),0
            if selected_count() >= value['max_events']: return dict(status,reason='event_limit',completed=True),0
            time.sleep(min(1,max(0,deadline-time.monotonic())))
        return dict(status,reason='stopped' if stopping else 'time_limit',completed=False),2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    try: status,code=run(args.once)
    except Exception: status,code=dict(lab_only=False,error='real_data_trial_failed'),1
    print(json.dumps(status,sort_keys=True),flush=True)
    return code


if __name__ == '__main__': raise SystemExit(main())
