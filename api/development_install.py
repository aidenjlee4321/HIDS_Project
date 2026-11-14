"""Debian maintainer metadata only. Never opens a source or security database."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import uuid

UNITS=('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket','hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket')
ROOTS=('/opt/hids-dashboard','/opt/hids-process-pipeline')


def require(value):
    if not value:raise ValueError('HIDS install refused; inspect existing configuration')


def stopped():
    if not Path('/run/systemd/system').is_dir():return
    for name in UNITS:
        p=subprocess.run(['/usr/bin/systemctl','show',name,'-p','ActiveState','--value'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=3)
        require(p.returncode==0 and p.stdout.strip() in ('inactive','failed'))


def safe(path,directory=False):
    p=Path(path);s=p.lstat();require(p.resolve()==p and s.st_uid==0 and not s.st_mode&0o022)
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1)
    for parent in p.parents:
        s=parent.lstat();require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022)


def preflight():
    require(os.getuid()==os.geteuid()==0);stopped()
    release=dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    require(release.get('ID','').strip('"')=='ubuntu' and release.get('VERSION_ID','').strip('"')=='26.04')
    for name in ROOTS:
        root=Path(name)
        if root.exists():
            safe(root,True);safe(root/'DEVELOPMENT_PACKAGE')
            require((root/'DEVELOPMENT_PACKAGE').read_text()=='hids-development/1\n')
    # Refuse unknown local unit overrides instead of overwriting or bypassing them.
    for name in UNITS:
        require(not Path('/etc/systemd/system',name).exists() and not Path('/run/systemd/system',name).exists())
        require(not Path('/etc/systemd/system',name+'.d').exists() and not Path('/run/systemd/system',name+'.d').exists())
    for name in ('hids-ingest','hids-process'):
        try:
            p=pwd.getpwnam(name);require(p.pw_uid>0 and p.pw_shell=='/usr/sbin/nologin' and sorted(set(os.getgrouplist(name,p.pw_gid)))==[p.pw_gid])
        except KeyError:pass


def directory(path,mode,uid=0,gid=0):
    p=Path(path)
    if not p.exists():p.mkdir(mode=mode);p.chmod(mode);os.chown(p,uid,gid)
    s=p.lstat();require(p.resolve()==p and stat.S_ISDIR(s.st_mode) and s.st_uid==uid and s.st_gid==gid and stat.S_IMODE(s.st_mode)==mode)


def write_bytes(path,data,mode=0o600,gid=0):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    try:
        os.fchown(fd,0,gid);os.fchmod(fd,mode)
        offset=0
        while offset<len(data):offset+=os.write(fd,data[offset:])
        os.fsync(fd)
    finally:os.close(fd)


def write(path,value,mode=0o600,gid=0):
    write_bytes(path,json.dumps(value,sort_keys=True,separators=(',',':')).encode(),mode,gid)


def sync_directory(path):
    fd=os.open(path,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def update_process_config(cfgpath,cfg,digest,gid,*,fault=lambda point:None):
    safe(cfgpath);history=cfgpath.parent/'process-config-history'
    if not history.exists():
        history.mkdir(mode=0o700);history.chmod(0o700);sync_directory(cfgpath.parent)
    safe(history,True);require(stat.S_IMODE(history.stat().st_mode)==0o700)
    # Keep a separately durable byte-exact backup without ever unpublishing the
    # active file. Interrupted retries see the complete old or complete new ID.
    write_bytes(history/(uuid.uuid4().hex+'.json'),cfgpath.read_bytes())
    sync_directory(history);fault('after_archive_sync')
    pending=cfgpath.with_name('process-'+uuid.uuid4().hex+'.pending')
    write(pending,dict(cfg,binary_sha256=digest),0o440,gid);fault('after_pending_sync')
    fault('before_publish');os.replace(pending,cfgpath);fault('after_publish')
    fault('before_directory_sync');sync_directory(cfgpath.parent);fault('after_directory_sync')


def require_fresh_process_config(cfgpath):
    # An older interrupted upgrade may already have removed the active file.
    # Ambiguous retained metadata needs explicit recovery, never a new source ID.
    history=cfgpath.parent/'process-config-history'
    require(not history.exists() and not history.is_symlink() and not any(cfgpath.parent.glob('process-*.pending')))


def configure():
    # dpkg may retry postinst without rerunning preinst. Refuse conflicts before
    # creating accounts, then recheck the resulting role identities below.
    preflight()
    for name in ('hids-ingest','hids-process'):
        try:pwd.getpwnam(name)
        except KeyError:subprocess.run(['/usr/sbin/useradd','--system','--user-group','--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin',name],check=True)
    preflight();backend=pwd.getpwnam('hids-ingest');reader=pwd.getpwnam('hids-process');require(backend.pw_uid!=reader.pw_uid)
    for p in ('/etc/hids','/var/lib/hids'):
        if not Path(p).exists():Path(p).mkdir(mode=0o755);Path(p).chmod(0o755)
        safe(p,True)
    # Existing private parent access must already permit the designated backend.
    s=Path('/etc/hids').stat();require(s.st_mode&0o001 or s.st_gid==backend.pw_gid and s.st_mode&0o010)
    directory('/var/lib/hids/process',0o700,backend.pw_uid,backend.pw_gid)
    directory('/etc/hids/setup',0o750,0,backend.pw_gid)
    path=Path('/var/lib/hids/install.json')
    if not path.exists():write(path,dict(version=1,installation_id=str(uuid.uuid4())))
    else:safe(path)
    binary=Path('/opt/hids-process-pipeline/process-collector');digest=hashlib.sha256(binary.read_bytes()).hexdigest();cfgpath=Path('/etc/hids/process.json')
    if not cfgpath.exists():
        require_fresh_process_config(cfgpath)
        write(cfgpath,dict(version=1,source_id=str(uuid.uuid4()),code='/opt/hids-process-pipeline/code',binary=str(binary),binary_sha256=digest,max_events=10000,max_bytes=64*1024*1024,minimum_free=256*1024*1024),0o440,backend.pw_gid)
    else:
        safe(cfgpath);cfg=json.loads(cfgpath.read_text())
        from engine.ingestion import process_contract as c
        require(type(cfg) is dict and set(cfg)=={'version','source_id','code','binary','binary_sha256','max_events','max_bytes','minimum_free'} and cfg['version']==1 and c.uuid_valid(cfg['source_id']) and cfg['code']=='/opt/hids-process-pipeline/code' and cfg['binary']==str(binary))
        if cfg['binary_sha256']!=digest:
            update_process_config(cfgpath,cfg,digest,backend.pw_gid)
    subprocess.run(['/usr/bin/systemd-tmpfiles','--create','/usr/lib/tmpfiles.d/hids-process.conf'],check=True)
    if Path('/run/systemd/system').is_dir():subprocess.run(['/usr/bin/systemctl','daemon-reload'],check=True)
    # No preset, enable/start/restart, database creation, logging or trust edits.


def main():
    try:
        require(len(sys.argv)==2)
        if sys.argv[1]=='preflight':preflight()
        elif sys.argv[1]=='configure':configure()
        elif sys.argv[1]=='stopped':stopped()
        else:raise ValueError()
        return 0
    except Exception:print('HIDS package metadata refused; existing state retained.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
