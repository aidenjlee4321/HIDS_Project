"""Explicit-root local leaf lifecycle. No background renewal or trust-store edits."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import uuid
from api.pilot_service import trusted
from api.pilot_sessions import Denied
from api.tls_leaf import validated_context, _openssl

ROOT=Path('/etc/hids/dashboard-tls')


def ensure_leaf(gid,current=None,*,root=ROOT):
    if os.getuid()!=0 or os.geteuid()!=0:raise Denied()
    for parent in root.parents:trusted(parent,True)
    if not root.exists():root.mkdir(mode=0o750);root.chmod(0o750);os.chown(root,0,gid)
    info=root.lstat()
    if root.resolve()!=root or not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_gid!=gid or stat.S_IMODE(info.st_mode)!=0o750:raise Denied()
    if current is not None:
        from engine.ingestion.m1_contract import uuid_valid
        if type(current) is not dict or set(current)!={'tls_generation','certificate_sha256'} or not uuid_valid(current['tls_generation']):raise Denied()
        directory=root/current['tls_generation']
        # Unsafe or replaced material is refused, rather than silently repaired.
        # Only a fully validated leaf may be reused; date expiry alone may renew.
        for p,mode in ((directory,0o750),(directory/'leaf.key',0o440),(directory/'leaf.pem',0o644)):
            info=p.lstat()
            if p.resolve()!=p or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=mode or (p==directory and (not stat.S_ISDIR(info.st_mode) or info.st_gid!=gid)) or (p!=directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1)) or (p.name=='leaf.key' and info.st_gid!=gid):raise Denied()
        der=_openssl('x509','-in',directory/'leaf.pem','-outform','DER')
        if hashlib.sha256(der).hexdigest()!=current['certificate_sha256']:raise Denied()
        def extension(name):return ''.join(_openssl('x509','-in',directory/'leaf.pem','-noout','-ext',name).decode('ascii').splitlines()[1:]).strip()
        if extension('basicConstraints')!='CA:FALSE' or extension('subjectAltName')!='IP Address:127.0.0.1' or extension('extendedKeyUsage')!='TLS Web Server Authentication':raise Denied()
        _openssl('verify','-trusted',directory/'leaf.pem','-check_ss_sig','-no_check_time','-purpose','sslserver','-verify_ip','127.0.0.1',directory/'leaf.pem')
        import ssl
        check=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);check.load_cert_chain(directory/'leaf.pem',directory/'leaf.key')
        # Use the same strict verifier, permitting renewal only when the
        # certificate is outside its lifetime / within the explicit renewal edge.
        import ssl,time
        dates=_openssl('x509','-in',directory/'leaf.pem','-noout','-dates').decode('ascii').splitlines()
        start,end=[ssl.cert_time_to_seconds(v.split('=',1)[1]) for v in dates]
        if not 0<end-start<=7*86400 or start>time.time():raise Denied()
        if end-time.time()>=3600:
            validated_context(directory/'leaf.pem',directory/'leaf.key',current['certificate_sha256'],gid)
            return dict(current)
    generation=str(uuid.uuid4());directory=root/generation
    directory.mkdir(mode=0o700);directory.chmod(0o700);os.chown(directory,0,0)
    try:
        subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','7','-subj','/CN=HIDS localhost dashboard','-addext','basicConstraints=critical,CA:FALSE','-addext','subjectAltName=IP:127.0.0.1','-addext','extendedKeyUsage=serverAuth','-keyout',str(directory/'leaf.key'),'-out',str(directory/'leaf.pem')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=True)
        os.chown(directory/'leaf.key',0,0);(directory/'leaf.key').chmod(0o600);(directory/'leaf.pem').chmod(0o644)
        fingerprint=hashlib.sha256(_openssl('x509','-in',directory/'leaf.pem','-outform','DER')).hexdigest()
        # This root-only staging mode runs the same crypto/leaf/pin checks. The
        # service's normal validation still requires its exact 0750/0440 roles.
        validated_context(directory/'leaf.pem',directory/'leaf.key',fingerprint,gid,_private=True)
        os.chown(directory/'leaf.key',0,gid);(directory/'leaf.key').chmod(0o440)
        os.chown(directory,0,gid)
        for path in (directory/'leaf.key',directory/'leaf.pem',directory):
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        directory.chmod(0o750)
        for path in (directory,root):
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        return dict(tls_generation=generation,certificate_sha256=fingerprint)
    except BaseException:
        # Preserve failed attempts for inspection, but keep their keys root-only.
        directory.chmod(0o700)
        raise
