"""Explicit Linux 2 operator transition; archive stopped manual code, retain data.

This is a pinned lab tool, not an automatic product migration or general installer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[2]
UNITS=('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket','hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def system(*args):return subprocess.check_output(['systemctl',*args],text=True,timeout=20).strip()
def main():
 a=argparse.ArgumentParser();a.add_argument('--expected-manifest',required=True);a.add_argument('--package',type=Path,required=True);a.add_argument('--sha256',required=True);args=a.parse_args()
 assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
 sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests/integration')]
 import dev,dashboard_pilot_ubuntu as lab
 from api.development_install import safe,preflight
 dev.verify(ROOT,args.expected_manifest);assert sha(args.package)==args.sha256
 assert all(system('show',u,'-p','ActiveState','--value')=='inactive' for u in UNITS)
 assert not Path('/run/hids/process/next-start.json').exists()
 assert subprocess.run(['dpkg-query','-W','hids-development'],capture_output=True).returncode!=0
 for name in UNITS:
  assert not Path('/run/systemd/system',name).exists()
  for parent in ('/etc/systemd/system','/run/systemd/system'):assert not Path(parent,name+'.d').exists()
 before=lab.preserved();backup=Path(tempfile.mkdtemp(prefix='hids-prepackage.',dir='/opt'));backup.chmod(0o700)
 retained={str(p):sha(p) for parent in ('/var/lib/hids/process','/etc/hids/setup') for p in Path(parent).iterdir() if p.is_file() and not p.name.endswith('-shm')}
 retained['/etc/hids/process.json']=sha('/etc/hids/process.json')
 with tarfile.open(backup/'retained-state.tar','w') as t:
  for name in ('/etc/hids','/var/lib/hids/process','/usr/lib/tmpfiles.d/hids-process.conf'):t.add(name,arcname=name.removeprefix('/'),recursive=True)
 with (backup/'retained-state.tar').open('rb') as f:os.fsync(f.fileno())
 report=dict(result='running',source_manifest=args.expected_manifest,artifact_sha256=args.sha256,archive=str(backup/'retained-state.tar'),moves=[],checks={});(backup/'transition.json').write_text(json.dumps(report,indent=2))
 try:
  candidates=[Path('/opt/hids-dashboard'),Path('/opt/hids-process-pipeline')]+[Path('/etc/systemd/system',n) for n in UNITS]
  for path in candidates:
   if not path.exists():continue
   safe(path,path.is_dir());assert not (path.is_dir() and (path/'DEVELOPMENT_PACKAGE').exists())
   target=backup/path.relative_to('/');target.parent.mkdir(parents=True,exist_ok=True);path.rename(target)
   report['moves'].append(dict(original=str(path),archived=str(target)));(backup/'transition.json').write_text(json.dumps(report,indent=2))
  system('daemon-reload')
  try:preflight()
  except BaseException:
   for row in reversed(report['moves']):
    assert not Path(row['original']).exists();Path(row['archived']).rename(row['original'])
   system('daemon-reload');raise
  # The package still enforces its normal unknown-installation conflict checks.
  r=subprocess.run(['dpkg','--install',str(args.package)],capture_output=True,text=True,timeout=90)
  (backup/'dpkg.stdout').write_text(r.stdout);(backup/'dpkg.stderr').write_text(r.stderr);assert r.returncode==0
  report['checks']['normal_dpkg_install_configured']=subprocess.check_output(['dpkg-query','-W','-f=${Status}','hids-development'],text=True)=='install ok installed'
  report['checks']['retained_data_ids_choices_unchanged']=all(sha(p)==v for p,v in retained.items())
  report['checks']['original_baseline_preserved']=lab.preserved()==before
  report['checks']['nothing_started']=all(system('show',u,'-p','ActiveState','--value')=='inactive' for u in UNITS)
  report['checks']['no_grant']=not Path('/run/hids/process/next-start.json').exists()
  report['checks']['operator_commands_available']=all(shutil.which(n) for n in ('hids-dashboard','hids-sources','hids-browser-prepare'))
  report['result']='passed' if all(report['checks'].values()) else 'failed'
 except BaseException as exc:
  import traceback
  report.update(result='failed',error_type=type(exc).__name__);(backup/'failure.txt').write_text(traceback.format_exc())
 finally:
  (backup/'transition.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(backup/'transition.json'),checks=report['checks'],error_type=report.get('error_type'))))
 return int(report['result']!='passed')
if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
