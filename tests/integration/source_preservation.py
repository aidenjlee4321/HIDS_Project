"""Lab-only preservation of authorized prefixes across host-managed log rotation.

Never import from product preflight. No baseline updates, log copying or repair.
"""
import hashlib
import os
from pathlib import Path
import re
import stat

class PreservationError(ValueError):pass

def require(value):
    if not value:raise PreservationError('source preservation unavailable')

def verify_prefixes(rows,*,owner=0):
    require(type(rows) is list and 1<=len(rows)<=16)
    result=[];total=0
    for row in rows:
        path=Path(row['path']);directory=path.parent
        require(path.is_absolute() and directory.resolve()==directory and re.fullmatch(r'audit\.log(?:\.[0-9]+)?',path.name))
        d=directory.lstat();require(stat.S_ISDIR(d.st_mode) and d.st_uid==owner and not d.st_mode&0o022)
        require(type(row['inode']) is int and row['inode']>0 and type(row['bytes']) is int and 0<=row['bytes']<=64*1024*1024 and re.fullmatch('[0-9a-f]{64}',row['sha256']))
        total+=row['bytes'];require(total<=256*1024*1024)
        matches=[];entries=0;candidates=0
        with os.scandir(directory) as scan:
            for entry in scan:
                entries+=1;require(entries<=256)
                if not re.fullmatch(r'audit\.log(?:\.[0-9]+)?',entry.name):continue
                candidates+=1;require(candidates<=32)
                s=entry.stat(follow_symlinks=False)
                require(stat.S_ISREG(s.st_mode) and s.st_uid==owner and s.st_nlink==1 and not s.st_mode&0o027)
                if (s.st_dev,s.st_ino)==(d.st_dev,row['inode']):matches.append(Path(entry.path))
        require(len(matches)==1);current=matches[0]
        fd=os.open(current,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            s=os.fstat(fd);require((s.st_dev,s.st_ino)==(d.st_dev,row['inode']) and s.st_uid==owner and s.st_nlink==1 and s.st_size>=row['bytes'])
            digest=hashlib.sha256();left=row['bytes']
            while left:
                block=os.read(fd,min(left,65536));require(block);digest.update(block);left-=len(block)
            require(digest.hexdigest()==row['sha256'])
            after=os.fstat(fd);named=current.lstat()
            require(after.st_nlink==1 and (named.st_dev,named.st_ino)==(s.st_dev,s.st_ino) and stat.S_ISREG(named.st_mode))
        finally:os.close(fd)
        result.append(dict(original=str(path),current=str(current),inode=row['inode'],bytes=row['bytes'],sha256=row['sha256']))
    return result
