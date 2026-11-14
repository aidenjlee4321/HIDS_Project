#!/usr/bin/env python3
"""Offline Ubuntu arm64 development artifact. No installation or source activity."""
import argparse
import base64
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import dev


def require(value):
    if not value:raise ValueError('development package inputs refused')


def copy(src,dst,mode=0o644):
    require(src.is_file() and not src.is_symlink());dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);dst.chmod(mode)


def audit_stage(stage):
    """No runtime state, lab manuals, private keys or unexpected external links."""
    count=0
    for path in stage.rglob('*'):
        rel=path.relative_to(stage).as_posix()
        require(not rel.startswith(('var/lib/hids','etc/hids','run/')))
        if path.is_symlink():
            require(rel=='opt/hids-dashboard/venv/bin/python3' and os.readlink(path)=='/usr/bin/python3');continue
        if not path.is_file():continue
        count+=1;require(not (rel.startswith(('opt/hids-dashboard/code/','opt/hids-process-pipeline/code/')) and path.suffix=='.md'))
        data=path.read_bytes()
        require(b'-----BEGIN PRIVATE KEY-----' not in data and b'-----BEGIN RSA PRIVATE KEY-----' not in data)
    return count


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);p.add_argument('--workflow-report',type=Path,required=True);p.add_argument('--expected-native-sha256',required=True);p.add_argument('--native-source',type=Path,required=True);p.add_argument('--native-report',type=Path,required=True);p.add_argument('--runtime-site',type=Path,required=True);p.add_argument('--modules',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--version',required=True);a=p.parse_args()
    require(sys.platform=='linux' and os.getuid()!=0 and sys.version_info[:2]==(3,14))
    require(subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()=='arm64' and re.fullmatch(r'0\.1\.0~dev[0-9.]+',a.version))
    root=Path(__file__).resolve().parents[1];dev.verify(root,a.expected_manifest)
    workflow=json.loads(a.workflow_report.read_text());require(workflow['status']=='passed' and workflow['source_sha256']==a.expected_manifest)
    require({v['name'] for v in workflow['phases']}=={'process_view','combined_http','history_regression','sessions_regression','setup_regression','installer_regression','source_control_regression','session_https','client','types','build_dashboard','build_history','build_setup'})
    native=json.loads(a.native_report.read_text());require(native['status']=='passed' and native['scope']=='process_pipeline_offline');dev.verify(a.native_source,native['source_sha256'])
    for name in dev.source_files(root):
        if name.startswith('collector/') or name in ('scripts/process_workflow.py','tests/unit/process_pipeline_test.cpp'):
            require((a.native_source/name).is_file() and (root/name).read_bytes()==(a.native_source/name).read_bytes())
    binary=a.native_report.parent/'process-collector';require(binary.is_file() and re.fullmatch('[0-9a-f]{64}',a.expected_native_sha256) and dev.sha(binary)==a.expected_native_sha256)
    output=dev.private_dir(a.output.absolute());work=Path(tempfile.mkdtemp(prefix='deb-build.',dir=output));stage=work/'root';stage.mkdir()
    provenance=dict(package_version=a.version,source_manifest=a.expected_manifest,native_source=native['source_sha256'],binary_sha256=dev.sha(binary),runtime={},frontend_lock_sha256=dev.sha(root/'frontend/package-lock.json'))
    for install in ('hids-dashboard','hids-process-pipeline'):
        target=stage/'opt'/install;(target/'code').mkdir(parents=True)
        for folder in ('api','engine','shared','rules'):
            for src in (root/folder).rglob('*'):
                if src.is_file() and src.suffix in ('.py','.json','.yaml','.yml'):copy(src,target/'code'/src.relative_to(root))
        (target/'DEVELOPMENT_PACKAGE').write_text('hids-development/1\n')
    process=stage/'opt/hids-process-pipeline';copy(binary,process/'process-collector',0o555)
    manifest={str(f.relative_to(process/'code')):dev.sha(f) for f in (process/'code').rglob('*.py')}
    (process/'code-manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':')))
    assets=a.workflow_report.parent/'frontend-build'
    for name in ('dashboard','setup','history'):shutil.copytree(assets/('dist-'+name),stage/'opt/hids-dashboard'/('assets' if name=='dashboard' else 'assets-'+name))
    site=stage/'opt/hids-dashboard/venv/lib/python3.14/site-packages';site.mkdir(parents=True)
    wanted={line.split('==')[0].lower().replace('_','-'):line.split('==')[1] for line in (root/'api/requirements-pilot.txt').read_text().splitlines() if line.strip()}
    distributions={d.metadata['Name'].lower().replace('_','-'):d for d in importlib.metadata.distributions(path=[str(a.runtime_site)])}
    for name,version in wanted.items():
        d=distributions[name];require(d.version==version);provenance['runtime'][name]=dict(version=version,files={})
        for rel in d.files or []:
            rel=Path(str(rel))
            if '..' in rel.parts or rel.is_absolute() or rel.suffix=='.pyc':continue
            src=a.runtime_site/rel;require(src.resolve().is_relative_to(a.runtime_site.resolve()) and not src.is_symlink())
            # Distribution RECORD authenticates each vendored runtime input;
            # RECORD itself is included in the artifact's provenance manifest.
            h=next((f.hash for f in d.files if str(f)==str(rel)),None)
            if h is not None:
                require(h.mode=='sha256' and base64.urlsafe_b64encode(hashlib.sha256(src.read_bytes()).digest()).decode().rstrip('=')==h.value)
            else:require(rel.name=='RECORD')
            copy(src,site/rel);provenance['runtime'][name]['files'][str(rel)]=dev.sha(src)
    venv=site.parents[2];(venv/'bin').mkdir();(venv/'bin/python3').symlink_to('/usr/bin/python3');(venv/'pyvenv.cfg').write_text('home = /usr/bin\ninclude-system-site-packages = false\nversion = 3.14\n')
    for name in ('hids-dashboard','hids-sources','hids-browser-prepare'):copy(root/'packaging'/name,stage/'usr/bin'/name,0o755)
    for name in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket','hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket'):copy(root/'packaging/systemd'/name,stage/'usr/lib/systemd/system'/name)
    copy(root/'packaging/systemd/hids-process.tmpfiles.conf',stage/'usr/lib/tmpfiles.d/hids-process.conf')
    copy(root/'packaging/browser-inputs.json',stage/'opt/hids-dashboard/BROWSER_INPUTS.json')
    docs=stage/'usr/share/doc/hids-development';docs.mkdir(parents=True)
    for name in ('LICENSE','LICENSE.MIT'):
        if (root/name).exists():copy(root/name,docs/name)
    copy(root/'collector/third_party/nlohmann/LICENSE.MIT',docs/'nlohmann-json-LICENSE.MIT')
    for name in ('react','react-dom'):copy(a.modules/name/'LICENSE',docs/(name+'-LICENSE'))
    copy(root/'packaging/DEVELOPMENT.md',docs/'README.md');copy(root/'api/requirements-pilot.txt',docs/'runtime-requirements.txt');copy(root/'frontend/package-lock.json',docs/'frontend-package-lock.json')
    (docs/'BUILD_INPUTS.json').write_text(json.dumps(provenance,sort_keys=True,indent=2))
    debian=stage/'DEBIAN';debian.mkdir()
    (debian/'control').write_text('Package: hids-development\nVersion: '+a.version+'\nArchitecture: arm64\nMaintainer: HIDS Project\nDepends: python3 (>= 3.14), python3 (<< 3.15), libc6, libstdc++6, libgcc-s1, systemd, passwd, openssl, libnss3-tools\nDescription: Local HIDS process and frozen history development build\n Ubuntu 26.04 arm64 only. Manual root activation; no automatic collection.\n')
    # preinst cannot import not-yet-unpacked files. Ship the exact standalone
    # metadata helper in its own script; no application/database reads occur.
    helper=(root/'api/development_install.py').read_text();(debian/'preinst').write_text('#!/usr/bin/python3 -IB\n'+helper.split("if __name__=='__main__':")[0]+'\ntry:\n if len(sys.argv)>2 and subprocess.run(["/usr/bin/dpkg","--compare-versions",sys.argv[2],"gt","'+a.version+'"]).returncode==0:raise ValueError("downgrade refused")\n preflight()\nexcept Exception:print("HIDS existing installation conflict or downgrade; no changes authorized.",file=sys.stderr);raise SystemExit(1)\n')
    (debian/'postinst').write_text('#!/bin/sh\nset -eu\n[ "$1" = configure ] || exit 0\nexec /usr/bin/python3 -I -B -c \'import sys;sys.path.insert(0,"/opt/hids-dashboard/code");from api.development_install import configure;configure()\'\n')
    (debian/'prerm').write_text('#!/bin/sh\nset -eu\nexec /usr/bin/python3 -I -B -c \'import sys;sys.path.insert(0,"/opt/hids-dashboard/code");from api.development_install import stopped;stopped()\'\n')
    for parent,dirs,files in os.walk(stage):
        Path(parent).chmod(0o755)
        for f in files:
            path=Path(parent)/f
            if not path.is_symlink() and not path.stat().st_mode&0o111:path.chmod(0o644)
    for name in ('preinst','postinst','prerm'):(debian/name).chmod(0o755)
    payload_files=audit_stage(stage)
    artifact=output/('hids-development_'+a.version+'_arm64.deb');require(not artifact.exists())
    subprocess.run(['/usr/bin/dpkg-deb','--root-owner-group','--build',str(stage),str(artifact)],check=True)
    dev.verify(root,a.expected_manifest)
    receipt=dict(artifact=str(artifact),sha256=dev.sha(artifact),version=a.version,source_manifest=a.expected_manifest,stage=str(stage),bytes=artifact.stat().st_size,payload_files=payload_files)
    (work/'report.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt));return 0
if __name__=='__main__':raise SystemExit(main())
