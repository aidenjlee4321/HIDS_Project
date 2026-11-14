"""Explicit root copy of a pinned external browser. No download, trust or launch."""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess
import sys
import uuid
from api.pilot_service import trusted
from api.pilot_sessions import Denied

MANIFEST=Path('/opt/hids-dashboard/BROWSER_INPUTS.json')
TARGET=Path('/opt/hids-browser')
PIN='40c121f803bd7f2c3dc394a12f064d14af1faea4baf7938dd2a8edd5175086f6'


def require(value):
    if not value:raise Denied()


def validate(value):
    require(type(value) is dict and set(value)=={'format','version','toolchain','files','links'} and value['format']=='hids.browser-inputs/1' and value['version']=='Chrome/158.0.8127.18' and value['links']=={})
    files=value['files'];require(type(files) is dict and 1<=len(files)<=1000)
    for name,item in files.items():
        path=PurePosixPath(name);require(type(name) is str and not path.is_absolute() and str(path)==name and all(part not in ('..','.','') for part in path.parts) and not any(ord(ch)<32 for ch in name) and '\\' not in name and len(name)<=256)
        require(type(item) is dict and set(item)=={'sha256','mode'} and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']) and type(item['mode']) is int and item['mode'] in (0o644,0o755))
    require(files.get('chrome',{}).get('sha256')==PIN)
    return value


def inventory(root,files,installed=False):
    require(root.is_absolute() and root.resolve()==root and root.is_dir())
    found=set();total=0
    if installed:
        info=root.lstat();require(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o755)
    for parent,dirs,names in os.walk(root,followlinks=False):
        for name in dirs:
            p=Path(parent,name);s=p.lstat();require(stat.S_ISDIR(s.st_mode) and not p.is_symlink())
            if installed:require(s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o755)
        for name in names:
            p=Path(parent,name);s=p.lstat();require(stat.S_ISREG(s.st_mode) and s.st_nlink==1)
            rel=p.relative_to(root).as_posix()
            if installed and rel=='.hids-browser-inputs':
                require(s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o644);continue
            require(rel in files and rel not in found and s.st_size<=512*1024*1024);found.add(rel);total+=s.st_size;require(total<=1024*1024*1024)
            if installed:require(s.st_uid==0 and stat.S_IMODE(s.st_mode)==files[rel]['mode'])
    require(found==set(files));return total


def file_digest(path):
    h=hashlib.sha256();fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno());require(stat.S_ISREG(s.st_mode) and s.st_nlink==1)
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def install(source,*,manifest_path=MANIFEST,target=TARGET):
    require(os.getuid()==os.geteuid()==0)
    for parent in manifest_path.parents:trusted(parent,True)
    trusted(manifest_path);require(manifest_path.stat().st_size<=128*1024)
    value=validate(json.loads(manifest_path.read_text()));files=value['files'];pin=file_digest(manifest_path)
    if os.path.lexists(target):
        trusted(target,True);require((target/'.hids-browser-inputs').read_text()==pin+'\n');inventory(target,files,True)
        require(all(file_digest(target/name)==meta['sha256'] for name,meta in files.items()));return target/'chrome'
    trusted(target.parent,True);total=inventory(source,files);space=os.statvfs(target.parent);require(space.f_bavail*space.f_frsize>=total+256*1024*1024)
    stage=target.with_name(target.name+'.pending-'+uuid.uuid4().hex);stage.mkdir(mode=0o700);stage.chmod(0o700)
    for name,meta in files.items():
        src=source/name;dst=stage/name;dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        read=os.open(src,os.O_RDONLY|os.O_NOFOLLOW);write=os.open(dst,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);digest=hashlib.sha256();count=0
        try:
            info=os.fstat(read);require(stat.S_ISREG(info.st_mode) and info.st_nlink==1)
            while True:
                data=os.read(read,1024*1024)
                if not data:break
                count+=len(data);require(count<=512*1024*1024);digest.update(data);offset=0
                while offset<len(data):offset+=os.write(write,data[offset:])
            require(digest.hexdigest()==meta['sha256']);os.fchmod(write,meta['mode']);os.fsync(write)
        finally:os.close(read);os.close(write)
    for parent,dirs,names in os.walk(stage):Path(parent).chmod(0o755)
    from engine.ingestion.process_control import role_command
    import pwd
    probe=subprocess.run(role_command(pwd.getpwnam('hids-process'),'/usr/bin/ldd',stage/'chrome'),capture_output=True,text=True,timeout=10)
    require(probe.returncode==0 and 'not found' not in probe.stdout and len(probe.stdout)<65536)
    marker=stage/'.hids-browser-inputs';marker.write_text(pin+'\n');marker.chmod(0o644)
    inventory(stage,files,True);require(not os.path.lexists(target));stage.rename(target)
    fd=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return target/'chrome'


def main():
    p=argparse.ArgumentParser(description='Prepare the exact tested external browser; never downloads or starts it.');p.add_argument('--from',dest='source',type=Path,required=True);a=p.parse_args()
    try:print('Verified external browser prepared: '+str(install(a.source.resolve())));return 0
    except Exception:print('Browser input, destination or Ubuntu library prerequisite refused; no existing browser was replaced.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
