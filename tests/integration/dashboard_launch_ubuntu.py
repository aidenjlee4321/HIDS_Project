"""Production launch-path acceptance over retained data. No source activation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
UNITS=('hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket')


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--certutil',type=Path,required=True);a=p.parse_args()
    assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
    sys.path.insert(0,str(ROOT/'scripts'));import dev;dev.verify(ROOT,a.expected_manifest)
    sys.path.insert(0,str(ROOT/'tests/integration'));import dashboard_pilot_ubuntu as lab
    before=lab.preserved();work=Path(tempfile.mkdtemp(prefix='hids-launch-acceptance.',dir='/opt'));work.chmod(0o700)
    report=dict(result='running',source_manifest=a.expected_manifest,checks={});checks=report['checks'];created=[]
    install=Path('/opt/hids-dashboard');profiles=set(Path('/tmp').glob('hids-dashboard-browser.*'));policy=Path('/sys/kernel/security/apparmor/profiles').read_text()
    def system(*args):return subprocess.run(['/usr/bin/systemctl',*args],check=True,capture_output=True,text=True,timeout=20).stdout.strip()
    def hashes():return {str(p):dev.sha(p) for p in Path('/var/lib/hids/process').iterdir() if not p.name.endswith('-shm')}
    initial=hashes()
    try:
        for name in UNITS:assert not Path('/run/systemd/system',name).exists() and not Path('/etc/systemd/system',name).exists()
        assert (install/'TRIAL_MARKER').read_text()=='hids-p01-combined-trial\n'
        install.rename(install.with_name('hids-dashboard-retained-'+work.name.split('.')[-1]));install.mkdir(mode=0o755);install.chmod(0o755)
        (install/'TRIAL_MARKER').write_text('hids-p01-combined-trial\n');(install/'code').mkdir(mode=0o755)
        for folder in ('api','engine','shared','rules'):shutil.copytree(ROOT/folder,install/'code'/folder,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(a.assets,install/'assets');(install/'venv').symlink_to('/opt/hids-dashboard-pilot/venv')
        for parent,dirs,files in os.walk(install):
            Path(parent).chmod(0o755)
            for name in files:Path(parent,name).chmod(0o644)
        # Reuse the already tested Ubuntu certificate-tool closure. The copy is
        # root-controlled and used only under the ordinary browser identity.
        tools=work/'prerequisites';tools.mkdir(mode=0o755);tools.chmod(0o755);certutil=tools/'certutil';shutil.copyfile(a.certutil,certutil);certutil.chmod(0o555);work.chmod(0o755)
        for name in UNITS:
            target=Path('/run/systemd/system',name);shutil.copyfile(ROOT/'packaging/systemd'/name,target);target.chmod(0o644);created.append(target)
        system('daemon-reload')
        meta=json.loads(Path('/opt/hids-combined-trial.l9hsxmqa/ground-truth.json').read_text())
        selected=meta['process']['selected'];bindings=meta['history']['bindings']
        sys.path.insert(0,str(install/'code'));from api.dashboard_launch import prepare,browser,stop,recent
        from api.dashboard_service import config
        from api.dashboard_cli import request
        checks['explicit_recent_metadata_matches_selection']=recent('process')==selected and recent('history')==bindings
        cert=prepare(selected,bindings);first=config();checks['root_prepare_uses_selected_families']=first['process']['selected']==selected and first['history']['bindings']==bindings
        browser(pwd.getpwnam('ivy'),'/opt/hids-browser-leaf.940b2j6b/browser/chrome',certutil,cert,temporary_userns=True,headless_check=True)
        checks['production_pipe_browser_completed']=True
        old=request('mint');stop();cert=prepare(selected,bindings);second=config()
        checks['valid_leaf_reused_on_explicit_reopen']=first['tls_generation']==second['tls_generation'] and first['certificate_sha256']==second['certificate_sha256']
        import ssl,urllib.request,urllib.error
        ctx=ssl.create_default_context(cafile=str(cert));opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx))
        req=urllib.request.Request('https://127.0.0.1:18765/v0/auth/redeem',data=json.dumps(dict(grant=old.split('#grant=')[1])).encode(),headers={'Sec-Fetch-Site':'same-origin','Origin':'https://127.0.0.1:18765','Content-Type':'application/json'})
        try:opener.open(req,timeout=3)
        except urllib.error.HTTPError as e:checks['reopen_revokes_prior_bootstrap']=e.code==403
        else:checks['reopen_revokes_prior_bootstrap']=False
        stop();checks['new_profile_removed']=set(Path('/tmp').glob('hids-dashboard-browser.*'))==profiles
        checks['old_leaf_material_private']=all((p.stat().st_mode&0o777)==0o700 for p in Path('/etc/hids/dashboard-tls').iterdir() if p.name!=second['tls_generation'])
        dev.verify(ROOT,a.expected_manifest)
    except Exception as e:
        report['error_type']=type(e).__name__
        import traceback;(work/'failure.txt').write_text(traceback.format_exc())
    finally:
        subprocess.run(['/usr/bin/systemctl','stop',*UNITS],capture_output=True,timeout=20)
        subprocess.run(['/usr/bin/systemctl','reset-failed',*UNITS],capture_output=True,timeout=10)
        for path in created:path.unlink()
        system('daemon-reload');checks['browser_policy_restored']=Path('/sys/kernel/security/apparmor/profiles').read_text()==policy
        checks['original_state_preserved']=lab.preserved()==before;checks['process_bytes_preserved']=hashes()==initial
        checks['sources_stopped']=all(system('show',u,'-p','ActiveState','--value')=='inactive' for u in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service'))
        report['result']='passed' if all(checks.values()) and 'error_type' not in report else 'failed'
        work.chmod(0o700);(work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(work/'report.json'),checks=checks,error_type=report.get('error_type'))))
    return 0 if report['result']=='passed' else 1
if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
