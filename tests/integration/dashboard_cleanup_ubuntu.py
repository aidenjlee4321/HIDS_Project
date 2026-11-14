"""Explicit Linux 2 cleanup acceptance: synthetic units/browser, no source start."""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
VIEWER=('hids-dashboard.service','hids-dashboard-http.socket','hids-dashboard-control.socket')
SOURCES=('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket')

def state(unit):return subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','--value'],text=True).strip()
def children(pid):
    try:return [int(v) for v in Path('/proc',str(pid),'task',str(pid),'children').read_text().split()]
    except FileNotFoundError:return []
def collect():
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        try:pid,_=os.waitpid(-1,os.WNOHANG)
        except ChildProcessError:return
        if not pid:time.sleep(.02)
    raise AssertionError('owned child not reaped')

def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);a=p.parse_args()
    assert os.getuid()==0 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
    assert all(state(u)=='inactive' for u in (*VIEWER,*SOURCES))
    sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests/integration'),str(ROOT)]
    import dev
    dev.verify(ROOT,a.expected_manifest)
    import dashboard_pilot_ubuntu as lab
    from api import dashboard_launch as launch
    from api.dashboard_tls import ensure_leaf
    assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0  # own descendant reaping only
    baseline=lab.preserved();profiles=Path('/sys/kernel/security/apparmor/profiles')
    policy_before=set(profiles.read_text().splitlines());browser_before=set(Path('/tmp').glob('hids-dashboard-browser.*'))
    work=Path(tempfile.mkdtemp(prefix='hids-dashboard-cleanup.',dir='/opt'));work.chmod(0o700)
    report=dict(result='running',source_manifest=a.expected_manifest,checks={});checks=report['checks'];created=[];groups=[]
    names=tuple('hids-cleanup-'+uuid.uuid4().hex+'.service' for _ in range(3))
    try:
        for name in names:
            path=Path('/run/systemd/system')/name;assert not path.exists()
            path.write_text('[Service]\nType=simple\nUser=hids-ingest\nGroup=hids-ingest\nExecStart=/usr/bin/sleep 300\nNoNewPrivileges=yes\nCapabilityBoundingSet=\nPrivateNetwork=yes\nProtectSystem=strict\nProtectHome=yes\nInaccessiblePaths=/var/lib/hids /etc/hids /run/hids\n');path.chmod(0o644);created.append(path)
        subprocess.run(['systemctl','daemon-reload'],check=True)
        tls=work/'tls';leaf=ensure_leaf(0,root=tls);cert=tls/leaf['tls_generation']/'leaf.pem'
        actual_system=launch.system;started=[]
        def interrupted(*args):
            answer=actual_system(*args)
            if args[0]=='start':
                started.append(all(state(u)=='active' for u in names));raise KeyboardInterrupt()
            return answer
        with patch.object(launch,'UNITS',names),patch.object(launch,'CONFIG',work/'never-published.json'),patch.object(launch,'TLS',tls),patch.object(launch,'ensure_leaf',return_value=leaf),patch.object(launch,'publish'),patch.object(launch,'system',side_effect=interrupted):
            try:launch.prepare([],[])
            except KeyboardInterrupt:pass
            else:raise AssertionError('interrupt not delivered')
        checks['real_unit_start_interrupt_stops_owned_units']=started==[True] and all(state(u)=='inactive' for u in names)

        user=pwd.getpwnam('ivy');original_popen=subprocess.Popen
        # Only select the verified source import for this test. Production's
        # fixed installed path, browser flags and privilege drop are unchanged.
        def popen_factory(interrupt):
            def spawn(args,*pos,**kw):
                worker=isinstance(args,list) and len(args)>4 and args[0]=='/usr/bin/python3' and 'api.dashboard_browser' in str(args[4])
                if not worker:return original_popen(args,*pos,**kw)
                args=list(args);args[4]=args[4].replace('/opt/hids-dashboard/code',str(ROOT))
                child=original_popen(args,*pos,**kw)
                class Worker:
                    def __getattr__(self,key):return getattr(child,key)
                    def wait(self,timeout=None):
                        if not interrupt or timeout is not None:return child.wait(timeout=timeout)
                        deadline=time.monotonic()+12
                        while time.monotonic()<deadline:
                            for pid in children(child.pid):
                                try:argv=Path('/proc',str(pid),'cmdline').read_bytes()
                                except FileNotFoundError:continue
                                if b'--remote-debugging-pipe' in argv:
                                    assert os.getpgid(pid)==pid;groups.append(pid)
                                    child.terminate();return child.wait(timeout=15)
                            if child.poll() is not None:raise AssertionError('worker exited before browser')
                            time.sleep(.02)
                        raise AssertionError('browser startup deadline')
                return Worker()
            return spawn
        for interrupt in (False,True):
            with patch.object(launch,'request',return_value='https://127.0.0.1:18765/#grant='+'A'*43),patch.object(launch.subprocess,'Popen',side_effect=popen_factory(interrupt)):
                try:launch.browser(user,'/opt/hids-browser/chrome','/usr/bin/certutil',cert,temporary_userns=True,headless_check=True)
                except launch.Denied:
                    if not interrupt:raise
                else:
                    if interrupt:raise AssertionError('terminated worker reported success')
            collect()
            checks['real_browser_term_cleanup' if interrupt else 'real_browser_normal_cleanup']=set(Path('/tmp').glob('hids-dashboard-browser.*'))==browser_before
        checks['owned_browser_group_gone']=True
        for group in groups:
            try:os.killpg(group,0)
            except ProcessLookupError:continue
            checks['owned_browser_group_gone']=False
        dev.verify(ROOT,a.expected_manifest)
    except BaseException as e:
        report['error_type']=type(e).__name__
        import traceback
        (work/'failure.txt').write_text(traceback.format_exc())
    finally:
        for group in groups:
            try:os.killpg(group,signal.SIGKILL)
            except ProcessLookupError:pass
        for pid in children(os.getpid()):
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
        collect()
        subprocess.run(['systemctl','stop',*names],capture_output=True,timeout=20)
        subprocess.run(['systemctl','reset-failed',*names],capture_output=True,timeout=10)
        for path in created:path.unlink()
        subprocess.run(['systemctl','daemon-reload'],check=True)
        checks['temporary_policy_restored']=set(profiles.read_text().splitlines())==policy_before
        checks['original_state_preserved']=lab.preserved()==baseline
        checks['sources_and_viewer_remain_stopped']=all(state(u)=='inactive' for u in (*VIEWER,*SOURCES))
        checks['no_production_config_published']=not (work/'never-published.json').exists()
        report['result']='passed' if checks and all(checks.values()) and 'error_type' not in report else 'failed'
        (work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(work/'report.json'),checks=checks,error_type=report.get('error_type'))))
    return int(report['result']!='passed')

if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
