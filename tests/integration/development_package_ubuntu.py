"""Independent copy-on-write Ubuntu root acceptance. Never installs on the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[2]


def command(*args,**kw):return subprocess.run(list(map(str,args)),check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=40,**kw)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def config_crash_checks(configure_module,cfg,gid):
    parent=Path('/etc/hids/install-crash-tests');parent.mkdir(mode=0o700)
    points=('after_archive_sync','after_pending_sync','before_publish','after_publish','before_directory_sync','after_directory_sync')
    for index,point in enumerate(points):
        directory=parent/str(index);directory.mkdir(mode=0o700);path=directory/'process.json'
        original=dict(cfg,binary_sha256='0'*64,max_events=123)
        raw=(json.dumps(original,indent=2)+'\n').encode();path.write_bytes(raw);path.chmod(0o440);os.chown(path,0,gid)
        pid=os.fork()
        if pid==0:
            def fault(boundary):
                if boundary==point:os.kill(os.getpid(),signal.SIGKILL)
            try:configure_module.update_process_config(path,original,'1'*64,gid,fault=fault)
            except BaseException:os._exit(2)
            os._exit(3)
        _,status=os.waitpid(pid,0);assert os.waitstatus_to_exitcode(status)==-signal.SIGKILL
        active=json.loads(path.read_bytes());assert active in (original,dict(original,binary_sha256='1'*64))
        backups=list((directory/'process-config-history').glob('*.json'))
        assert any(p.read_bytes()==raw for p in backups)
        if active['binary_sha256']!='1'*64:configure_module.update_process_config(path,active,'1'*64,gid)
        assert json.loads(path.read_bytes())==dict(original,binary_sha256='1'*64)
        s=path.stat();assert s.st_uid==0 and s.st_gid==gid and s.st_mode&0o777==0o440 and s.st_nlink==1
    return len(points)


def dashboard_crash_checks(module,original,gid):
    parent=Path('/etc/hids/dashboard-crash-tests');parent.mkdir(mode=0o700)
    points=('after_pending_sync','after_archive_sync','before_publish','after_publish','before_directory_sync','after_directory_sync')
    previous=module.CONFIG;updated=dict(original,process=None,history=None)
    try:
        for index,point in enumerate(points):
            directory=parent/str(index);directory.mkdir(mode=0o700);path=directory/'dashboard.json';module.CONFIG=path
            raw=(json.dumps(original,indent=2)+'\n').encode();path.write_bytes(raw);path.chmod(0o440);os.chown(path,0,gid)
            pid=os.fork()
            if pid==0:
                def fault(boundary):
                    if boundary==point:os.kill(os.getpid(),signal.SIGKILL)
                try:module.publish(updated,gid,fault=fault)
                except BaseException:os._exit(2)
                os._exit(3)
            _,status=os.waitpid(pid,0);assert os.waitstatus_to_exitcode(status)==-signal.SIGKILL
            active=json.loads(path.read_bytes());assert active in (original,updated)
            assert all(active[k]==original[k] for k in ('tls_generation','certificate_sha256'))
            if active!=updated:module.publish(updated,gid)
            assert json.loads(path.read_bytes())==updated
            assert any(p.read_bytes()==raw for p in (directory/'dashboard-config-history').glob('*.json'))
            s=path.stat();assert s.st_uid==0 and s.st_gid==gid and s.st_mode&0o777==0o440 and s.st_nlink==1
    finally:module.CONFIG=previous
    return len(points)


def inside(work,artifact,upgrade=None):
    # This worker is PID 1 in a private PID/mount namespace. Every package write
    # goes to a fresh overlay upper layer, never the running VM's filesystem.
    command('mount','--make-rprivate','/')
    command('/usr/sbin/ip','link','set','lo','up')
    upper=work/'upper';overlaywork=work/'overlay-work';root=work/'root'
    for p in (upper,overlaywork,root):p.mkdir(mode=0o700)
    command('mount','-t','overlay','overlay','-o','lowerdir=/,upperdir='+str(upper)+',workdir='+str(overlaywork),root)
    root.chmod(0o755)
    for name in ('opt','home','root','run','tmp','sys','etc/hids','var/lib/hids','etc/systemd/system','usr/lib/hids'):
        target=root/name;target.mkdir(parents=True,exist_ok=True)
        command('mount','-t','tmpfs','-o','mode=755,nosuid,nodev','tmpfs',target)
    # Fresh identity definitions preserve OS system accounts, strip all HIDS
    # roles and lock every password. No host password hash enters this test root.
    for name in ('passwd','group'):
        src=Path('/etc')/name;target=root/'etc'/name
        lines=[line for line in src.read_text().splitlines() if not line.startswith('hids-')]
        target.write_text('\n'.join(lines)+'\n');target.chmod(0o644)
    (root/'etc/shadow').write_text(''.join(line.split(':')[0]+':!:::::::\n' for line in (root/'etc/passwd').read_text().splitlines()));(root/'etc/shadow').chmod(0o600)
    (root/'etc/gshadow').write_text(''.join(line.split(':')[0]+':!::\n' for line in (root/'etc/group').read_text().splitlines()));(root/'etc/gshadow').chmod(0o600)
    command('mount','-t','proc','proc',root/'proc')
    # Use only harmless device endpoints needed by normal package tools.
    command('mount','-t','tmpfs','-o','mode=755,nosuid','tmpfs',root/'dev')
    import stat
    for name,minor in [('null',3),('zero',5),('random',8),('urandom',9)]:
        os.mknod(root/'dev'/name,stat.S_IFCHR|0o666,os.makedev(1,minor));(root/'dev'/name).chmod(0o666)
    shutil.copyfile(artifact,root/'input.deb')
    if upgrade:shutil.copyfile(upgrade,root/'upgrade.deb')
    # Stage sanitized fixture inputs before hiding the original source tree.
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests/unit'));from test_process_pipeline import fixture,status,PRODUCER
    events=[fixture(kind) for kind in ('fork','exec','exit')];interval=status(delivery=True,stopped=True,reason='stopped')
    os.chroot(root);os.chdir('/')
    for name in list(sys.modules):
        if name in ('api','engine') or name.startswith(('api.','engine.')):del sys.modules[name]
    sys.path[:]=[p for p in sys.path if p not in (str(ROOT),str(ROOT/'tests/unit'))]
    checks={};report=dict(result='running',checks=checks)
    try:
        first=command('/usr/bin/dpkg','-i','/input.deb');Path('/tmp/install.log').write_text(first.stdout+first.stderr)
        checks['fresh_install_configured']=True
        sys.path.insert(0,'/opt/hids-dashboard/code')
        from api.development_install import preflight
        preflight()
        from api.dashboard_tls import ensure_leaf
        from api.dashboard_launch import publish
        from api.dashboard_cli import request
        backend=pwd.getpwnam('hids-ingest');reader=pwd.getpwnam('hids-process');checks['isolated_nonlogin_roles']=backend.pw_uid>0 and reader.pw_uid>0 and backend.pw_uid!=reader.pw_uid and backend.pw_shell==reader.pw_shell=='/usr/sbin/nologin' and set(os.getgrouplist(backend.pw_name,backend.pw_gid))=={backend.pw_gid} and set(os.getgrouplist(reader.pw_name,reader.pw_gid))=={reader.pw_gid}
        cfgpath=Path('/etc/hids/process.json');cfg=json.loads(cfgpath.read_text());identity=Path('/var/lib/hids/install.json').read_bytes()
        checks['units_not_enabled']=not any(Path('/etc/systemd/system').iterdir())
        checks['no_collection_or_persistent_grant']=not Path('/run/hids/process/next-start.json').exists() and not Path('/var/lib/hids/process/store.sqlite').exists()
        from api.setup_store import root_store
        record=root_store().save([],0);selection=Path('/etc/hids/setup/selection-0001.json').read_bytes()
        from engine.ingestion.process_control import role_command
        checks['no_grant_runtime_refused']=subprocess.run(['/usr/bin/python3','-I','-B','-c','import sys;sys.path.insert(0,"/opt/hids-process-pipeline/code");from engine.ingestion.process_control import main;raise SystemExit(main())'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode!=0
        checks['collector_missing_config_refused']=subprocess.run(role_command(reader,'/opt/hids-process-pipeline/process-collector','/run/hids/process/nonexistent.json'),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode!=0
        for event in events:event['source'].update(mode='live',source_id=cfg['source_id'])
        interval['source']=events[0]['source']
        payload=dict(events=events,interval=interval,producer=PRODUCER);Path('/tmp/fixture.json').write_text(json.dumps(payload));Path('/tmp/fixture.json').chmod(0o644)
        source=events[0]['source']
        code='''import json,sys;from pathlib import Path
sys.path.insert(0,"/opt/hids-process-pipeline/code")
from engine.database.process_store import Store
v=json.loads(Path("/tmp/fixture.json").read_text());store=Store("/var/lib/hids/process/store.sqlite",v["events"][0]["source"])
for event in v["events"]:store.put(event)
store.interval(v["interval"],v["producer"]);print("ready",flush=True);sys.stdin.readline();store.close()
'''
        writer=subprocess.Popen(role_command(backend,'/usr/bin/python3','-I','-B','-c',code),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=Path('/tmp/fixture.stderr').open('w'),text=True);line=writer.stdout.readline()
        if line!='ready\n':
            print(Path('/tmp/fixture.stderr').read_text(),file=sys.stderr)
            for path in ['/', '/usr','/usr/lib','/usr/lib/aarch64-linux-gnu','/usr/lib/aarch64-linux-gnu/libm.so.6']:
                entry=Path(path);info=entry.stat();print('permission',path,oct(info.st_mode&0o777),info.st_uid,info.st_gid,file=sys.stderr)
            raise AssertionError('isolated fixture writer failed')
        store=Path('/var/lib/hids/process/store.sqlite');s=store.stat();leaf=ensure_leaf(backend.pw_gid)
        publish(dict(version=1,mode='frozen-dashboard',port=18765,process=dict(identity=[s.st_dev,s.st_ino],selected=[{k:source[k] for k in ('source_id','activation_id')}]),history=None,**leaf),backend.pw_gid)
        command('mount','--bind',store.parent,store.parent);command('mount','-o','remount,bind,ro',store.parent)
        listeners=[]
        http=socket.socket();http.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);http.bind(('127.0.0.1',18765));http.listen(16);listeners.append(http)
        runtime=Path('/run/hids-dashboard');runtime.mkdir(mode=0o700);runtime.chmod(0o700)
        control=socket.socket(socket.AF_UNIX);control.bind(str(runtime/'control.sock'));(runtime/'control.sock').chmod(0o600);control.listen(8);listeners.append(control)
        live=set()
        def start():
            pid=os.fork()
            if pid==0:
                import fcntl
                fds=[fcntl.fcntl(s.fileno(),fcntl.F_DUPFD_CLOEXEC,10) for s in listeners]
                for index,fd in enumerate(fds,3):os.dup2(fd,index,inheritable=True)
                for fd in fds:os.close(fd)
                env=dict(LISTEN_PID=str(os.getpid()),LISTEN_FDS='2',LISTEN_FDNAMES='http:control',PATH='/usr/bin:/bin')
                # Same fixed-role zero-capability executable closure. PID1 unit
                # hardening itself was tested separately on the installed VM.
                argv=role_command(backend,'/opt/hids-dashboard/venv/bin/python3','-I','-B','-c','import sys;sys.path.insert(0,"/opt/hids-dashboard/code");from api.dashboard_service import main;raise SystemExit(main())')
                null=os.open('/dev/null',os.O_RDWR);os.dup2(null,1);os.dup2(null,2)
                os.execve(argv[0],argv,env)
            live.add(pid);return pid
        def stop(pid):
            if pid not in live:return
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass
            _,status=os.waitpid(pid,0);live.remove(pid)
            code=os.waitstatus_to_exitcode(status);report.setdefault('server_exit_statuses',[]).append(code)
            assert code in (0,-signal.SIGTERM)
        cert=Path('/etc/hids/dashboard-tls')/leaf['tls_generation']/'leaf.pem';ctx=ssl.create_default_context(cafile=str(cert));opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx))
        def http_request(path,token=None,value=None):
            headers={'Sec-Fetch-Site':'same-origin'}
            if token:headers['Authorization']='Bearer '+token
            if value is not None:headers.update(Origin='https://127.0.0.1:18765',**{'Content-Type':'application/json'})
            req=urllib.request.Request('https://127.0.0.1:18765'+path,data=None if value is None else json.dumps(value).encode(),headers=headers)
            with opener.open(req,timeout=2) as response:return json.loads(response.read(65537))
        def ready(pid):
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                try:
                    with opener.open('https://127.0.0.1:18765/',timeout=.5):return
                except OSError:time.sleep(.05)
            raise AssertionError('packaged HTTPS runtime unavailable')
        server=None
        try:
            server=start();ready(server)
            token=http_request('/v0/auth/redeem',value=dict(grant=request('mint').split('#grant=')[1]))['token']
            view=http_request('/v0/dashboard',token);checks['packaged_runtime_https_and_frozen_data']=view['process']['available'] and view['process']['snapshot']['counts']['events']==3 and not view['history']['available']
            checks['unavailable_family_preserves_auth']=http_request('/v0/process/events',token)['items'][0]['activity_wall_time'] is None
            stop(server);server=None;server=start();ready(server)
            try:http_request('/v0/dashboard',token)
            except urllib.error.HTTPError as e:checks['restart_revokes_session']=e.code==403
            else:checks['restart_revokes_session']=False
            token=http_request('/v0/auth/redeem',value=dict(grant=request('mint').split('#grant=')[1]))['token'];checks['restart_keeps_frozen_history']=http_request('/v0/dashboard',token)['process']['snapshot']['counts']['events']==3
        finally:
            if server:stop(server)
            for listener in listeners:listener.close()
            writer.stdin.close();writer.wait(timeout=5);assert writer.returncode==0
        command('mount','-o','remount,bind,rw',store.parent)
        before={str(p):sha(p) for p in (store,cfgpath,Path('/etc/hids/dashboard.json'),Path('/etc/hids/setup/selection-0001.json'),cert,cert.with_name('leaf.key'))}
        if upgrade:
            # Exercise the actual installed postinst hash-update branch with
            # synthetic stale metadata, without replacing the native binary.
            cfgpath.write_text(json.dumps(dict(cfg,binary_sha256='0'*64)))
        second=command('/usr/bin/dpkg','-i','/upgrade.deb' if upgrade else '/input.deb');Path('/tmp/upgrade.log').write_text(second.stdout+second.stderr)
        checks['reinstall_preserves_data_ids_keys_choices']=all(sha(p)==h for p,h in before.items()) and Path('/var/lib/hids/install.json').read_bytes()==identity and Path('/etc/hids/setup/selection-0001.json').read_bytes()==selection
        require_uuid=__import__('uuid').UUID;checks['per_install_identifiers']=require_uuid(cfg['source_id']).version==4 and require_uuid(json.loads(identity)['installation_id']).version==4
        report['source_id_sha256']=hashlib.sha256(cfg['source_id'].encode()).hexdigest()
        report['synthetic_fixture_events']=3
        if upgrade:
            archived=[json.loads(p.read_text()) for p in Path('/etc/hids/process-config-history').glob('*.json')]
            checks['installed_hash_update_preserves_identity_limits']=json.loads(cfgpath.read_text())==cfg and any(v==dict(cfg,binary_sha256='0'*64) for v in archived)
            downgrade=subprocess.run(['/usr/bin/dpkg','-i','/input.deb'],capture_output=True,text=True,timeout=30)
            checks['downgrade_refused_without_data_change']=downgrade.returncode!=0 and all(sha(p)==h for p,h in before.items())
        import importlib
        from api import development_install
        development_install=importlib.reload(development_install)
        report['actual_config_sigkill_cases']=config_crash_checks(development_install,cfg,backend.pw_gid)
        checks['config_crash_retry_preserves_ids_limits']=report['actual_config_sigkill_cases']==6
        from api import dashboard_launch
        dashboard_launch=importlib.reload(dashboard_launch)
        report['dashboard_config_sigkill_cases']=dashboard_crash_checks(dashboard_launch,json.loads(Path('/etc/hids/dashboard.json').read_text()),backend.pw_gid)
        checks['dashboard_config_crash_retry_preserves_tls_and_selection']=report['dashboard_config_sigkill_cases']==6 and sha('/etc/hids/dashboard.json')==before['/etc/hids/dashboard.json']
        # Reproduce the missing-active-file shape left by an older interrupted
        # updater. Keep its retained copy; never guess which identity to restore.
        history=cfgpath.parent/'process-config-history';history.mkdir(mode=0o700,exist_ok=True)
        retained=cfgpath.read_bytes();cfgpath.rename(history/'legacy-interruption.json')
        try:
            refused=subprocess.run(['/usr/bin/python3','-I','-B','-c','import sys;sys.path.insert(0,"/opt/hids-dashboard/code");from api.development_install import configure;configure()'],capture_output=True,text=True,timeout=15)
            checks['legacy_missing_config_refused_without_new_identity']=refused.returncode!=0 and not cfgpath.exists() and (history/'legacy-interruption.json').read_bytes()==retained
        finally:
            if not cfgpath.exists():development_install.write_bytes(cfgpath,retained,0o440,backend.pw_gid)
        command('/usr/bin/systemd-tmpfiles','--create','/usr/lib/tmpfiles.d/hids-process.conf')
        checks['boot_metadata_does_not_authorize']=not Path('/run/hids/process/next-start.json').exists()
        report['result']='passed' if all(checks.values()) else 'failed'
    except Exception as e:
        import traceback;traceback.print_exc(file=sys.stderr)
        if isinstance(e,subprocess.CalledProcessError):print(e.stderr[-4000:],file=sys.stderr)
        report.update(result='failed',error_type=type(e).__name__)
    print(json.dumps(report),flush=True);return 0 if report['result']=='passed' else 1


def main():
    if len(sys.argv)>1 and sys.argv[1]=='_inside':return inside(Path(sys.argv[2]),Path(sys.argv[3]),None if len(sys.argv)<5 or sys.argv[4]=='-' else Path(sys.argv[4]))
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--upgrade-package',type=Path);p.add_argument('--upgrade-sha256');a=p.parse_args()
    assert os.getuid()==0 and sha(a.package)==a.sha256 and Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()=='46330e53-4a53-4a94-b9d4-0adefd192ab7'
    if a.upgrade_package:assert a.upgrade_sha256 and sha(a.upgrade_package)==a.upgrade_sha256
    sys.path.insert(0,str(ROOT/'tests/integration'));import dashboard_pilot_ubuntu as lab
    before=lab.preserved();work=Path(tempfile.mkdtemp(prefix='hids-package-acceptance.',dir='/opt'));work.chmod(0o700)
    result=subprocess.run(['/usr/bin/unshare','--mount','--pid','--net','--fork','/usr/bin/python3','-I','-B',str(Path(__file__)),'_inside',str(work),str(a.package),str(a.upgrade_package) if a.upgrade_package else '-'],stdout=(work/'worker.stdout').open('x'),stderr=(work/'worker.stderr').open('x'),timeout=120)
    lines=(work/'worker.stdout').read_text().splitlines();report=json.loads(lines[-1]) if lines else dict(result='failed',error_type='worker_failed_before_report')
    if report.get('source_id_sha256'):
        old=json.loads(Path('/etc/hids/process.json').read_text())['source_id']
        report.setdefault('checks',{})['source_identity_not_copied_from_vm']=report['source_id_sha256']!=hashlib.sha256(old.encode()).hexdigest()
    report.update(package_sha256=a.sha256,upgrade_package_sha256=a.upgrade_sha256,isolated_root_kind='private_pid_mount_network_namespace_copy_on_write_ubuntu_base',host_state_preserved=lab.preserved()==before)
    if result.returncode or not report['host_state_preserved']:report['result']='failed'
    (work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(result=report['result'],report=str(work/'report.json'),checks=report.get('checks',{}),host_state_preserved=report['host_state_preserved'],error_type=report.get('error_type'))))
    return 0 if report['result']=='passed' else 1
if __name__=='__main__':os.umask(0o077);raise SystemExit(main())
