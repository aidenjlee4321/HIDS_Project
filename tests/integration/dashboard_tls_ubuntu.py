"""Root-only isolated leaf lifecycle regression; no listeners or trust edits."""
import hashlib
import os
from pathlib import Path
import pwd
import tempfile
import subprocess
import time
import uuid
from unittest.mock import patch
from api.dashboard_tls import ensure_leaf
from api.pilot_sessions import Denied


def main():
 assert os.getuid()==0
 os.umask(0o077);gid=pwd.getpwnam('hids-ingest').pw_gid
 work=Path(tempfile.mkdtemp(prefix='hids-leaf-regression.',dir='/opt'));work.chmod(0o755)
 root=work/'tls';first=ensure_leaf(gid,root=root);assert root.stat().st_mode&0o777==0o750
 directory=root/first['tls_generation'];assert directory.stat().st_mode&0o777==0o750
 before={p.name:p.read_bytes() for p in directory.iterdir()}
 assert ensure_leaf(gid,first,root=root)==first and before=={p.name:p.read_bytes() for p in directory.iterdir()}
 bad=dict(first,certificate_sha256='0'*64)
 try:ensure_leaf(gid,bad,root=root)
 except Denied:pass
 else:raise AssertionError('wrong pin accepted')
 (directory/'leaf.key').chmod(0o444)
 try:ensure_leaf(gid,first,root=root)
 except Denied:pass
 else:raise AssertionError('unsafe key accepted')
 (directory/'leaf.key').chmod(0o440)
 assert before=={p.name:p.read_bytes() for p in directory.iterdir()}
 # Exercise the real renewal branch with a local mocked clock; the VM clock
 # and browser/system trust stores never change.
 now=time.time()
 with patch('time.time',return_value=now+7*86400-1200):near=ensure_leaf(gid,first,root=root)
 assert near['tls_generation']!=first['tls_generation']
 assert before=={p.name:p.read_bytes() for p in directory.iterdir()}
 expired=root/str(uuid.uuid4());expired.mkdir(mode=0o750);expired.chmod(0o750);os.chown(expired,0,gid)
 import shutil
 shutil.copyfile(directory/'leaf.key',expired/'leaf.key');shutil.copyfile(directory/'leaf.pem',expired/'valid.pem')
 (expired/'index').touch();(expired/'serial').write_text('0A\n');(expired/'newcerts').mkdir()
 conf='''[ca]
default_ca=local
[local]
database={r}/index
serial={r}/serial
new_certs_dir={r}/newcerts
certificate={r}/valid.pem
private_key={r}/leaf.key
default_md=sha256
policy=names
x509_extensions=leaf
[names]
commonName=supplied
[leaf]
basicConstraints=critical,CA:FALSE
extendedKeyUsage=serverAuth
subjectAltName=IP:127.0.0.1
'''.format(r=expired)
 (expired/'ca.conf').write_text(conf)
 def run(*args):return subprocess.check_output(['/usr/bin/openssl',*map(str,args)],stderr=subprocess.DEVNULL,timeout=10)
 run('req','-new','-key',expired/'leaf.key','-subj','/CN=HIDS localhost dashboard','-out',expired/'expired.csr')
 run('ca','-selfsign','-batch','-notext','-config',expired/'ca.conf','-in',expired/'expired.csr','-startdate','20260101000000Z','-enddate','20260102000000Z','-out',expired/'leaf.pem')
 (expired/'leaf.pem').chmod(0o644);os.chown(expired/'leaf.key',0,gid);(expired/'leaf.key').chmod(0o440)
 old=hashlib.sha256((expired/'leaf.pem').read_bytes()).hexdigest()
 current=dict(tls_generation=expired.name,certificate_sha256=hashlib.sha256(run('x509','-in',expired/'leaf.pem','-outform','DER')).hexdigest())
 renewed=ensure_leaf(gid,current,root=root)
 assert renewed['tls_generation']!=expired.name and old==hashlib.sha256((expired/'leaf.pem').read_bytes()).hexdigest()
 print('PASS restrictive-umask reuse wrong-pin unsafe-key near-expiry-renewal expired-renewal unchanged-material')
if __name__=='__main__':main()
