"""Explicit backed-up schema upgrade. CLI requires root, then drops to data owner."""
import argparse
import json
import os
from pathlib import Path
import pwd
import sqlite3
import stat
import sys
import uuid

from engine.detection.m4_handoff import Store,private
from engine.detection.m4_live import LiveStore,PAGES,POLICY,STATE_DIRECTORY
from engine.detection.m4_rule_store import RuleStore
from engine.detection.m4_schema import MIGRATION
from engine.detection.m4_storage import aggregate
from engine.detection.m4_pilot import Invalid,canonical,digest
from engine.ingestion import m3_storage


def snapshot(db):
    values={}
    for table,order in (('m4h_events','event_key'),('m4h_rules','rule_id,revision'),('m4h_evaluations','event_key,rule_id,revision'),('m4h_alerts','alert_id')):
        values[table]=db.execute('SELECT * FROM '+table+' ORDER BY '+order).fetchall()
    values['m4h_bindings']=db.execute('SELECT binding_key,scope,directory,state FROM m4h_bindings ORDER BY binding_key').fetchall()
    return values


def migrate_store(directory,*,fault=lambda stage:None):
    """Generic private-path core for tests; CLI below fixes the production path."""
    directory=Path(directory);private(directory.parent,directory=True)
    old=LiveStore.__new__(LiveStore)
    Store.__init__(old,directory,max_pages=PAGES,storage=dict(POLICY),lab_only=False)
    backup=None
    try:
        if old.db.execute('PRAGMA integrity_check').fetchone()!=('ok',) or old.db.execute('PRAGMA foreign_key_check').fetchall():
            raise Invalid('source integrity failure')
        before=snapshot(old.db)
        pages=old.db.execute('PRAGMA page_count').fetchone()[0]
        if not 1<=pages<=PAGES:raise Invalid('source exceeds page budget')
        reserve=pages*4096+65536
        status=old.guard.observe(old.path,force=True);total=aggregate(directory.parent)
        if (status['state'] not in ('normal','warning') or total+reserve+2*old.guard.reserve>=POLICY['max_state_bytes']*3//4 or
            status['available_bytes']-reserve-2*old.guard.reserve<=POLICY['critical_free_bytes']):
            raise m3_storage.StoragePressure('migration/backup admission blocked')
        parent=directory.parent/'backups'
        if not parent.exists():parent.mkdir(mode=0o700)
        private(parent,directory=True)
        backup_dir=parent/('before-v2-'+uuid.uuid4().hex);backup_dir.mkdir(mode=0o700)
        backup=backup_dir/'handoff.sqlite'
        fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd)
        db=sqlite3.connect(backup,isolation_level=None)
        try:old.db.backup(db,pages=16)
        finally:db.close()
        db=sqlite3.connect(backup,isolation_level=None)
        try:
            if db.execute('PRAGMA journal_mode=DELETE').fetchone()!=('delete',):raise Invalid('backup finalization failed')
        finally:db.close()
        db=sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True)
        try:
            LiveStore._identity(db)
            if db.execute('PRAGMA integrity_check').fetchone()!=('ok',) or snapshot(db)!=before:raise Invalid('backup verification failed')
        finally:db.close()
        private(backup)
        metadata=dict(kind='pre-v2-backup',source_version=1,target_version=2,backup=str(backup),
                      history_hash=digest('hids.m4.history/1',before),counts={name:len(rows) for name,rows in before.items()})
        p=backup_dir/'manifest.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(metadata,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        for path in (backup,backup_dir,parent):
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        fault('backup_verified')
        if aggregate(directory.parent)+2*old.guard.reserve>=POLICY['max_state_bytes']*3//4:raise Invalid('aggregate budget exceeded')
        with old.transaction():
            for n,statement in enumerate((s.strip() for s in MIGRATION.split(';') if s.strip()),1):
                old.db.execute(statement);fault('statement_'+str(n))
            RuleStore._identity(old.db)
            if snapshot(old.db)!=before or old.db.execute('PRAGMA foreign_key_check').fetchall():raise Invalid('migration changed history')
            if any(row!=('[]',) for row in old.db.execute('SELECT rule_plan FROM m4h_bindings')):raise Invalid('historical rule plan not empty')
            fault('before_commit')
        fault('after_commit')
        return dict(result='passed',version=2,**metadata)
    finally:old.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true',required=True);parser.parse_args()
    if sys.platform!='linux' or os.getuid()!=0 or os.geteuid()!=0:raise PermissionError('explicit Ubuntu root migration required')
    try:
        a=pwd.getpwnam('hids-ingest');os.setgroups([]);os.setgid(a.pw_gid);os.setuid(a.pw_uid)
        if os.getresuid()!=(a.pw_uid,)*3 or os.getresgid()!=(a.pw_gid,)*3 or os.getgroups():raise Invalid('identity drop incomplete')
        caps={line.split(':',1)[0]:int(line.split()[1],16) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('CapEff:','CapPrm:','CapInh:'))}
        if set(caps)!={'CapEff','CapPrm','CapInh'} or any(caps.values()):raise Invalid('capabilities remain after identity drop')
        result=migrate_store(STATE_DIRECTORY)
    except Exception:print(json.dumps(dict(result='failed',error='migration_refused_or_failed')),flush=True);return 1
    print(json.dumps(result,sort_keys=True),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
