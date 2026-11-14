"""Root-owned immutable selection revisions. No activation authority is persisted."""
import os
from pathlib import Path
import re
import secrets
import stat
from api.setup_contract import selection_record,selected,empty_record,REGISTRY_HASH,canonical,require
from api.pilot_sessions import closed_json

DIRECTORY=Path('/etc/hids/setup')

def safe_read(path,owner,gid,mode,limit):
 require(path.is_absolute() and path.resolve()==path)
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==owner and info.st_gid==gid and stat.S_IMODE(info.st_mode)==mode and info.st_size<=limit)
  data=os.read(fd,limit+1);require(len(data)<=limit);return data
 finally:os.close(fd)

class _Store:
 # Internal filesystem seam for synthetic fixtures. The public root entry fixes
 # the directory/identity below; no HTTP/client supplies paths or owners.
 def __init__(self,directory,owner,gid,*,fault=lambda _:None):self.directory=Path(directory);self.owner=owner;self.gid=gid;self.fault=fault
 def check(self):
  p=self.directory;require(p.is_absolute() and p.resolve()==p)
  s=p.lstat();require(stat.S_ISDIR(s.st_mode) and s.st_uid==self.owner and s.st_gid==self.gid and stat.S_IMODE(s.st_mode)==0o750)
  for parent in p.parents:
   s=parent.lstat();require(s.st_uid in (0,self.owner) and (not s.st_mode&0o022 or s.st_uid==0 and s.st_mode&stat.S_ISVTX))
 def load(self):
  self.check();records={};pending=0
  for i,p in enumerate(self.directory.iterdir()):
   require(i<32)
   if re.fullmatch(r'pending-[0-9a-f]{32}\.tmp',p.name):
    safe_read(p,self.owner,self.gid,0o600,4096);pending+=1;require(pending<=16);continue
   require(re.fullmatch(r'selection-[0-9]{4}\.json',p.name))
   value=selection_record(closed_json(safe_read(p,self.owner,self.gid,0o440,4096),{'version','revision','selected','registry_sha256'}))
   require(value['revision']>0 and p.name==f"selection-{value['revision']:04d}.json" and value['revision'] not in records);records[value['revision']]=value
  require(sorted(records)==list(range(1,len(records)+1)) and len(records)<=16)
  return records[len(records)] if records else empty_record()
 def save(self,values,expected):
  require(os.geteuid()==self.owner);current=self.load();require(type(expected) is int and expected==current['revision'] and expected<16)
  values=selected(values);value=selection_record(dict(version=1,revision=expected+1,selected=values,registry_sha256=REGISTRY_HASH))
  temp=self.directory/('pending-'+secrets.token_hex(16)+'.tmp');target=self.directory/f'selection-{expected+1:04d}.json';published=False
  fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
  try:
   os.fchown(fd,self.owner,self.gid);raw=canonical(value).encode();offset=0
   while offset<len(raw):
    n=os.write(fd,raw[offset:]);require(n>0);offset+=n
   self.fault('before_file_sync');os.fsync(fd);self.fault('before_publish')
   require(not target.exists());os.fchmod(fd,0o440);os.fsync(fd);os.rename(temp,target);published=True;self.fault('after_publish')
   directory=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
   try:os.fsync(directory)
   finally:os.close(directory)
   self.fault('after_directory_sync');require(self.load()==value);return value
  finally:
   os.close(fd)
   # Remove only this operation's newly created unpublished temporary file.
   if not published and temp.exists():temp.unlink()

def root_store():
 import pwd
 require(os.getuid()==0 and os.geteuid()==0)
 return _Store(DIRECTORY,0,pwd.getpwnam('hids-ingest').pw_gid)
