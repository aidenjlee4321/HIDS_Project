"""Replace only the stopped experimental process package; retain a private backup."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

BASE=Path('/opt/hids-process-pipeline')
UNITS=('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket')
def check(value):
    if not value:raise RuntimeError('process_upgrade_refused')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cmd(*args):return subprocess.check_output(args,text=True,timeout=20).strip()
def replace(path,data,mode,gid=0):
    temp=path.with_name(path.name+'.upgrade-pending');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,gid);os.fchmod(f.fileno(),mode)
    os.replace(temp,path)
def main():
    check(os.getuid()==0 and len(sys.argv)==6)
    source=Path(sys.argv[1]);manifest=sys.argv[2];build=Path(sys.argv[3]);binary_sha=sys.argv[4];trial_sha=sys.argv[5]
    check(Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7')
    sys.path.insert(0,str(source/'scripts'));import dev;dev.verify(source,manifest)
    report=json.loads((build/'report.json').read_text());check(report['status']=='passed' and report['source_sha256']==manifest)
    check(sha(build/'process-collector')==binary_sha and sha(build/'process-owned-trial')==trial_sha)
    check(all(cmd('systemctl','show',n,'-p','ActiveState','--value')=='inactive' for n in UNITS))
    check(not Path('/run/hids/process/next-start.json').exists())
    old=json.loads((BASE/'code-manifest.json').read_text());check(all(sha(BASE/'code'/name)==digest for name,digest in old.items()))
    cfg=json.loads(Path('/etc/hids/process.json').read_text());check(sha(BASE/'process-collector')==cfg['binary_sha256'])
    backup=Path(tempfile.mkdtemp(prefix='hids-process-upgrade.',dir='/opt'));backup.chmod(0o700)
    shutil.copytree(BASE,backup/'previous-package');shutil.copy2('/etc/hids/process.json',backup/'previous-config.json')
    for name in UNITS:
        p=Path('/etc/systemd/system')/name
        if p.exists():shutil.copy2(p,backup/name)
    files={}
    for name in ('engine','api'):
        for p in sorted((source/name).rglob('*.py')):
            rel=p.relative_to(source);target=BASE/'code'/rel;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            data=p.read_bytes();replace(target,data,0o644);files[str(rel)]=hashlib.sha256(data).hexdigest()
    for d in (BASE/'code').rglob('*'):
        if d.is_dir():d.chmod(0o755)
    replace(BASE/'code-manifest.json',json.dumps(files,sort_keys=True).encode(),0o644)
    for name,digest in [('process-collector',binary_sha),('process-owned-trial',trial_sha)]:
        data=(build/name).read_bytes();check(hashlib.sha256(data).hexdigest()==digest);replace(BASE/name,data,0o555)
    cfg['binary_sha256']=binary_sha;replace(Path('/etc/hids/process.json'),json.dumps(cfg,sort_keys=True,separators=(',',':')).encode(),0o440,pwd.getpwnam('hids-ingest').pw_gid)
    backend=Path('/run/hids/process-backend')
    if not backend.exists():backend.mkdir(mode=0o750);backend.chmod(0o750);os.chown(backend,0,pwd.getpwnam('hids-ingest').pw_gid)
    for name in UNITS:
        data=(source/'packaging/systemd'/name).read_bytes()
        if name.endswith('.service'):check(b'RestrictSUIDSGID=yes' in data)
        replace(Path('/etc/systemd/system')/name,data,0o644)
    replace(Path('/usr/lib/tmpfiles.d/hids-process.conf'),(source/'packaging/systemd/hids-process.tmpfiles.conf').read_bytes(),0o644)
    cmd('systemd-tmpfiles','--create','/usr/lib/tmpfiles.d/hids-process.conf')
    cmd('systemd-analyze','verify',*[str(Path('/etc/systemd/system')/n) for n in UNITS]);cmd('systemctl','daemon-reload')
    dev.verify(source,manifest)
    out=dict(source_manifest=manifest,backup=str(backup),collection_started=False,identity_filter_retained=True,root_coordinator_capabilities=['CAP_CHOWN'])
    (backup/'upgrade.json').write_text(json.dumps(out));(backup/'upgrade.json').chmod(0o600);print(json.dumps(out))
if __name__=='__main__':os.umask(0o077);main()
