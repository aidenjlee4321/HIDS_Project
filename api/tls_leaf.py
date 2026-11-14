"""Explicit leaf/key validation for synthetic TLS trials; no trust-store edits."""
import hashlib
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

class TLSError(ValueError):
    pass

def _openssl(*args):
    try:
        result=subprocess.run(['/usr/bin/openssl',*map(str,args)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3,check=True)
        if len(result.stdout)>65536:raise TLSError('TLS validation refused')
        return result.stdout
    except (OSError,subprocess.SubprocessError):raise TLSError('TLS validation refused') from None

def validated_context(cert,key,fingerprint,backend_gid,*,_private=False):
    cert,key=Path(cert),Path(key)
    if type(_private) is not bool or _private and (os.getuid()!=0 or os.geteuid()!=0):raise TLSError('TLS validation refused')
    directory_mode,key_mode,gid=(0o700,0o600,0) if _private else (0o750,0o440,backend_gid)
    if not re.fullmatch('[0-9a-f]{64}',fingerprint):raise TLSError('TLS validation refused')
    if cert.parent!=key.parent:raise TLSError('TLS validation refused')
    for path in (cert,key,cert.parent):
        if not path.is_absolute() or path.resolve()!=path:raise TLSError('TLS validation refused')
        info=path.lstat()
        if info.st_uid!=0:raise TLSError('TLS validation refused')
        if path==cert.parent:
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=directory_mode or info.st_gid!=gid:raise TLSError('TLS validation refused')
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<info.st_size<=32768:
            raise TLSError('TLS validation refused')
    if stat.S_IMODE(key.stat().st_mode)!=key_mode or key.stat().st_gid!=gid or stat.S_IMODE(cert.stat().st_mode)!=0o644:raise TLSError('TLS validation refused')
    # Every ancestor is root-controlled: no caller-writable path substitution.
    for parent in cert.parent.parents:
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise TLSError('TLS validation refused')
    der=_openssl('x509','-in',cert,'-outform','DER')
    if hashlib.sha256(der).hexdigest()!=fingerprint:raise TLSError('TLS validation refused')
    def extension(name):return _openssl('x509','-in',cert,'-noout','-ext',name).decode('ascii').splitlines()[1:]
    if ''.join(extension('basicConstraints')).strip()!='CA:FALSE':raise TLSError('TLS validation refused')
    if ''.join(extension('subjectAltName')).strip()!='IP Address:127.0.0.1':raise TLSError('TLS validation refused')
    if ''.join(extension('extendedKeyUsage')).strip()!='TLS Web Server Authentication':raise TLSError('TLS validation refused')
    dates=_openssl('x509','-in',cert,'-noout','-dates').decode('ascii').splitlines()
    try:
        start,end=[ssl.cert_time_to_seconds(value.split('=',1)[1]) for value in dates]
        now=time.time()
        if not start<=now or end-now<660 or not 0<end-start<=7*86400:raise TLSError('TLS validation refused')
    except (ValueError,IndexError):raise TLSError('TLS validation refused') from None
    _openssl('verify','-trusted',cert,'-check_ss_sig','-purpose','sslserver','-verify_ip','127.0.0.1',cert)
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    try:ctx.load_cert_chain(cert,key)
    except (OSError,ssl.SSLError):raise TLSError('TLS validation refused') from None
    return ctx
