"""Provisional M3 disk admission policy; no evidence deletion or host collection.

Private file metadata and statvfs only. SQLite checkpointing preserves committed
rows and is never replaced with unlinking journal or evidence files. This is an
application admission guard, not a filesystem quota against external writers.
"""
import os
from pathlib import Path
import sqlite3
import stat
import time
from contextlib import contextmanager

MIB=1024*1024
FIELDS={'max_wal_bytes','max_state_bytes','warning_free_bytes','critical_free_bytes','minimum_free_bytes'}
STATES={'normal','warning','critical','exhausted','unknown'}
REASONS={None,'wal_budget','state_budget','filesystem_reserve','inspection_unavailable'}


class StoragePressure(RuntimeError):
    pass


def defaults(max_pages,max_activations):
    # Allow room for a full-database transaction plus two bookkeeping frames.
    # The tested SQLite page size is 4096; the connection verifies it below.
    reserve=(max_pages+2)*(4096+24)+32
    wal=max(8*MIB,8*reserve)
    return dict(max_wal_bytes=wal,
        max_state_bytes=max(256*MIB,(max_activations+1)*(max_pages*4096+wal+65536)),
        warning_free_bytes=1024*MIB,critical_free_bytes=512*MIB,minimum_free_bytes=256*MIB)


def validate(options,max_pages,max_activations):
    if options is not None and type(options) is not dict:raise ValueError('invalid storage policy')
    options=defaults(max_pages,max_activations) if options is None else dict(options)
    if options.keys()!=FIELDS or any(type(v) is not int or not 0<v<2**63 for v in options.values()):
        raise ValueError('invalid storage policy')
    reserve=(max_pages+2)*(4096+24)+32
    if not (options['minimum_free_bytes']<options['critical_free_bytes']<options['warning_free_bytes'] and
            options['max_wal_bytes']>=8*reserve and options['max_state_bytes']>=16*reserve):
        raise ValueError('insufficient storage reserve')
    return options


class Guard:
    def __init__(self,directory,max_pages,max_activations,options=None,*,clock=time.monotonic,space=None):
        self.directory=Path(directory)
        self.options=validate(options,max_pages,max_activations)
        self.reserve=(max_pages+2)*(4096+24)+32
        self.clock=clock
        self.space=space or self._available
        self.files={}
        self.last_scan=None
        self.scan_ok=False
        self.recovery_depth=0
        self.last_checkpoint={}

    def _available(self):
        value=os.statvfs(self.directory)
        return value.f_bavail*value.f_frsize

    def _file(self,path):
        try: info=path.lstat()
        except FileNotFoundError:return None
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
                info.st_nlink!=1 or stat.S_IMODE(info.st_mode)&~0o600):
            raise OSError('untrusted storage file')
        return max(info.st_size,info.st_blocks*512)

    def observe(self,path=None,*,force=False):
        try:
            now=self.clock()
            if force or not self.scan_ok or self.last_scan is None or now-self.last_scan>=1:
                files={}
                for entry in self.directory.iterdir():
                    size=self._file(entry)
                    if size is not None:files[entry]=size
                self.files=files;self.last_scan=now;self.scan_ok=True
            if path is not None:
                for suffix in ('','-wal','-shm','-journal'):
                    item=Path(str(path)+suffix);size=self._file(item)
                    if size is None:self.files.pop(item,None)
                    else:self.files[item]=size
            available=self.space()
            if type(available) is not int or available<0:raise OSError('invalid available storage')
            state_bytes=sum(self.files.values())
            wal=max((size for file,size in self.files.items() if file.name.endswith('-wal')),default=0)
            p=self.options;r=self.reserve
            state='normal';reason=None
            if available<=p['minimum_free_bytes']:state='exhausted';reason='filesystem_reserve'
            elif state_bytes>=p['max_state_bytes']:state='exhausted';reason='state_budget'
            elif wal>=p['max_wal_bytes']:state='exhausted';reason='wal_budget'
            elif available-2*r<=p['critical_free_bytes']:state='critical';reason='filesystem_reserve'
            elif state_bytes+2*r>=p['max_state_bytes']*3//4:state='critical';reason='state_budget'
            elif wal+r>=p['max_wal_bytes']*3//4:state='critical';reason='wal_budget'
            elif available<=p['warning_free_bytes']:state='warning';reason='filesystem_reserve'
            elif state_bytes>=p['max_state_bytes']//2:state='warning';reason='state_budget'
            elif wal>=p['max_wal_bytes']//2:state='warning';reason='wal_budget'
            return dict(state=state,reason=reason,available_bytes=available,state_bytes=state_bytes,
                wal_bytes=wal,**p)
        except (OSError,ValueError):
            self.scan_ok=False
            return dict(state='unknown',reason='inspection_unavailable',available_bytes=None,
                state_bytes=None,wal_bytes=None,**self.options)

    @contextmanager
    def recovery(self):
        self.recovery_depth+=1
        try:yield
        finally:self.recovery_depth-=1

    def before(self,path):
        value=self.observe(path)
        if self.recovery_depth:
            p=self.options;r=self.reserve
            safe=(value['state']!='unknown' and value['available_bytes']-2*r>p['minimum_free_bytes'] and
                  value['state_bytes']+2*r<p['max_state_bytes'] and value['wal_bytes']+r<p['max_wal_bytes'])
        else:safe=value['state'] in ('normal','warning')
        if not safe:raise StoragePressure('M3 storage admission blocked')

    def after(self,path):
        # Never raise after a committed transaction: its authoritative result
        # remains committed even if subsequent metadata inspection fails.
        self.observe(path)

    def checkpoint(self,connection,path):
        now=self.clock()
        if connection.in_transaction:return
        cached_wal=max((size for file,size in self.files.items() if file.name.endswith('-wal')),default=0)
        urgent=cached_wal+self.reserve>=self.options['max_wal_bytes']*3//4
        if not urgent and now-self.last_checkpoint.get(path,-1e30)<1:return
        self.last_checkpoint[path]=now
        value=self.observe(path)
        if value['state']=='unknown' or value['available_bytes']<=self.options['minimum_free_bytes']+self.reserve:return
        if value['wal_bytes']<self.options['max_wal_bytes']//2:return
        try:
            sqlite3.Connection.execute(connection,'PRAGMA busy_timeout=0')
            sqlite3.Connection.execute(connection,'PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        except sqlite3.Error:pass
        finally:
            sqlite3.Connection.execute(connection,'PRAGMA busy_timeout=1000')
        self.observe(path,force=True)


class Connection(sqlite3.Connection):
    guard=None
    storage_path=None
    data_read_only=False

    def execute(self,sql,parameters=()):
        text=sql.lstrip().upper()
        verb=text.split(None,1)[0] if text else ''
        writes=verb in ('BEGIN','INSERT','UPDATE','DELETE','REPLACE','CREATE','DROP','ALTER','VACUUM','REINDEX') or (verb=='PRAGMA' and '=' in text)
        if writes and self.data_read_only:
            raise StoragePressure('restart required before SQL data writes')
        boundary=writes and not self.in_transaction
        if self.guard is not None and boundary:
            self.guard.checkpoint(self,self.storage_path)
            self.guard.before(self.storage_path)
        result=super().execute(sql,parameters)
        if self.guard is not None and not self.in_transaction and (writes or verb in ('COMMIT','ROLLBACK','END')):
            self.guard.after(self.storage_path)
        return result


def connect(path,guard):
    options=dict(isolation_level=None,timeout=1,factory=Connection)
    if hasattr(sqlite3,'LEGACY_TRANSACTION_CONTROL'):options['autocommit']=sqlite3.LEGACY_TRANSACTION_CONTROL
    connection=sqlite3.connect(path,**options)
    connection.guard=guard;connection.storage_path=Path(path)
    # Guard sizing is pinned to this actual SQLite page size.
    if connection.execute('PRAGMA page_size').fetchone()!=(4096,):
        connection.close();raise ValueError('unsupported storage page size')
    return connection


def validate_status(value):
    if type(value) is not dict or value.keys()!=FIELDS|{'state','reason','available_bytes','state_bytes','wal_bytes'}:
        raise ValueError('invalid storage status')
    if value['state'] not in STATES or value['reason'] not in REASONS:
        raise ValueError('invalid storage state')
    for key in FIELDS|{'available_bytes','state_bytes','wal_bytes'}:
        if value[key] is None and key not in FIELDS and value['state']=='unknown':continue
        if type(value[key]) is not int or not 0<=value[key]<2**63:raise ValueError('invalid storage number')
