#!/usr/bin/env python3
"""Reproducible M3 development/VM acceptance; no Git publication or package installs."""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import dev

ROOT = Path(__file__).resolve().parents[1]
UNITS = ('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')
FIXTURE = 'tests/fixtures/audit/structural-exec.log'
FLAGS = ['-std=c++20','-Wall','-Wextra','-Wpedantic','-Werror',
         '-Icollector/include','-Icollector/third_party']
ARTIFACTS = ('hids-audit-plugin','hids-m3-health','producer','health-isolation-probe',
             'hids-audit-plugin-init-fault','hids-audit-plugin-allocate-fault')
BUDGET = {'component': 6, 'checkpoint': 30}


def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def check(ok,message):
    if not ok: raise dev.WorkflowError(message)


def private_json(path,value):
    dev.write_new(path,dev.json_bytes(value),private=True)


def atomic_bytes(path,data,mode):
    """Replace one regular application file; services must already be stopped."""
    path=Path(path)
    check(not path.is_symlink(),'refuse symlink target: '+str(path))
    if path.exists(): dev.regular(path)
    with tempfile.NamedTemporaryFile(prefix='.hids-stage-',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name)
        try:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.fchmod(stream.fileno(),mode)
            os.replace(temporary,path)
        finally:
            if temporary.exists():temporary.unlink()


class Run:
    def __init__(self,output,scope,source):
        root=dev.private_dir(Path(output).absolute())
        self.path=root/dev.unique('run');self.path.mkdir(mode=0o700)
        self.started=time.monotonic()
        self.user=None;self.work=None
        if os.getuid()==0 and os.environ.get('SUDO_UID'):
            uid=int(os.environ['SUDO_UID']);check(uid>0,'ordinary invoking user required')
            self.user=pwd.getpwuid(uid)
            self.work=Path(tempfile.mkdtemp(prefix='hids-m3-unpriv.'))
            os.chown(self.work,self.user.pw_uid,self.user.pw_gid)
        self.report=dict(report_version=1,scope=scope,source_sha256=source,
            started_utc=now(),status='running',phases=[],error=None)

    def phase(self,name,command,*,env=None,timeout=180,unprivileged=False):
        check(re.fullmatch('[a-z0-9_-]+',name) is not None,'invalid phase name')
        check(not any(p['name']==name for p in self.report['phases']),'duplicate phase')
        started=time.monotonic()
        out=self.path/(name+'.stdout');err=self.path/(name+'.stderr')
        environment=os.environ.copy();environment.pop('BASH_ENV',None)
        environment.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT))
        if env:environment.update(env)
        identity={}
        if unprivileged and os.getuid()==0:
            check(self.user is not None,'run guest through sudo from an ordinary VM account')
            identity=dict(user=self.user.pw_uid,group=self.user.pw_gid,extra_groups=[])
            environment.update(HOME=self.user.pw_dir,USER=self.user.pw_name,LOGNAME=self.user.pw_name,TMPDIR=str(self.work))
        code=127;error=None
        with out.open('xb') as stdout,err.open('xb') as stderr:
            os.chmod(out,0o600);os.chmod(err,0o600)
            try:
                # New group prevents timed-out test descendants from writing
                # after cleanup has started. Full logs remain private.
                child=subprocess.Popen(command,cwd=ROOT,env=environment,
                    stdout=stdout,stderr=stderr,start_new_session=True,**identity)
                try:code=child.wait(timeout=timeout)
                except (subprocess.TimeoutExpired,KeyboardInterrupt):
                    import signal
                    os.killpg(child.pid,signal.SIGKILL);child.wait()
                    code=124;error='phase interrupted or timed out'
            except OSError as exc:error=type(exc).__name__
        # Scan incrementally; never pull a long log into model context.
        skipped=False;test_count=None
        for file in (out,err):
            with file.open(errors='replace') as stream:
                for line in stream:
                    if re.search(r'OK \(skipped=\d+\)|\.\.\. skipped ',line):skipped=True
                    count=re.search(r'Ran (\d+) tests? in ',line)
                    if count:test_count=int(count.group(1))
        item=dict(name=name,exit_code=code,seconds=round(time.monotonic()-started,3),
            skipped=skipped,test_count=test_count,stdout_sha256=dev.sha(out),stderr_sha256=dev.sha(err))
        self.report['phases'].append(item)
        print(json.dumps({k:item[k] for k in ('name','exit_code','seconds','skipped','test_count')},sort_keys=True),flush=True)
        if code or skipped or name in ('python','workflow') and not test_count:
            if error:item['error']=error
            # A bounded tail is enough to locate the protected full report.
            for file in (err,out):
                with file.open('rb') as stream:
                    stream.seek(max(0,file.stat().st_size-1800))
                    tail=stream.read().decode(errors='replace')
                if tail:print(tail,flush=True)
            raise dev.WorkflowError('failed or skipped phase: '+name)

    def finish(self,error=None,*,dispatched=False):
        self.report.update(finished_utc=now(),status='failed' if error else ('dispatched' if dispatched else 'passed'),error=error)
        self.report['wall_seconds']=round(time.monotonic()-self.started,3)
        self.report['retained_log_bytes']=sum(p.stat().st_size for p in self.path.glob('*.std*'))
        self.report['phase_console_bytes']=sum(len(json.dumps({k:p[k] for k in
            ('name','exit_code','seconds','skipped','test_count')},sort_keys=True).encode())+1 for p in self.report['phases'])
        self.report['build_commands']=sum(p['name'].startswith('build_') for p in self.report['phases'])
        self.report['phase_seconds']=round(sum(p['seconds'] for p in self.report['phases']),3)
        private_json(self.path/'report.json',self.report)
        print(json.dumps(dict(status=self.report['status'],report=str(self.path/'report.json'),
            phases=len(self.report['phases']),phase_seconds=self.report['phase_seconds'],error=error)),flush=True)


def offline(run,tier,headers=None):
    run.phase('python',[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test_m3*.py'],unprivileged=True)
    run.phase('workflow',[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test*workflow*.py'],unprivileged=True)
    if tier=='focused':return
    env={}
    if headers:env=dict(HIDS_M3_AUPARSE='1',HIDS_AUDIT_INCLUDE_DIR=str(headers),HIDS_AUPARSE_LIBRARY='-l:libauparse.so.0')
    for name in ('reconstruction','native_contract','parser_failures'):
        run.phase(name,['bash','tests/integration/validate_m3_'+name+'.sh','--sanitize'],env=env,unprivileged=True)
    run.phase('crash',[sys.executable,'-B','tests/integration/m3_crash_matrix.py'],unprivileged=True)


def source_digest():
    return digest({name:dev.sha(ROOT/name) for name in dev.source_files(ROOT)})


def dependency_inputs(paths,root):
    return {(p.resolve().relative_to(root).as_posix() if p.resolve().is_relative_to(root) else str(p.resolve())):
            dev.sha(p.resolve()) for p in paths}


def dependency_info(headers):
    compiler=shutil.which('c++');check(compiler is not None,'C++ compiler missing')
    check(headers.is_dir(),'explicit existing Audit headers required')
    library=Path(subprocess.check_output([compiler,'-print-file-name=libauparse.so.0'],text=True).strip())
    check(library.is_absolute() and library.is_file(),'libauparse runtime not found')
    # Include transitive system/C++ headers, not just the explicit Audit headers.
    units=[*sorted((ROOT/'collector/src/audit').glob('*.cpp')),
           ROOT/'collector/src/health/main.cpp',ROOT/'collector/src/health/snapshot.cpp',
           *(ROOT/'collector/src'/g/n for g in ('pilot','journal') for n in ('contract.cpp','transport.cpp')),
           *sorted((ROOT/'tests/unit').glob('m3_*.cpp')),ROOT/'tests/integration/m3_fixture_producer.cpp']
    deps=subprocess.check_output([compiler,*FLAGS,'-I'+str(headers),'-DHIDS_M3_AUPARSE','-M',
        *(str(p) for p in units)],cwd=ROOT,text=True,timeout=30)
    paths={Path(p) if Path(p).is_absolute() else ROOT/p for p in
           shlex.split(deps.replace('\\\n',' ')) if not p.endswith(':')}
    inputs=dependency_inputs(paths,ROOT)
    packages=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}=${Version}\n'],text=True,timeout=20)
    return dict(transitive_input_sha256=digest(inputs),transitive_input_count=len(inputs),
        packages_sha256=hashlib.sha256(packages.encode()).hexdigest(),
        compiler=compiler,compiler_sha256=dev.sha(Path(compiler).resolve()),
        compiler_version=subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
        headers={n:dev.sha(headers/n) for n in ('auparse.h','auparse-defs.h')},
        library=str(library.resolve()),library_sha256=dev.sha(library.resolve()),
        platform=platform.platform(),machine=platform.machine(),flags=FLAGS,
        python=sys.version,sqlite=sqlite3.sqlite_version)


def build_valid(directory,key):
    try:
        if directory.is_symlink() or directory.stat().st_uid!=os.getuid() or stat.S_IMODE(directory.stat().st_mode)!=0o700:return False
        meta=dev.read_json(directory/'build.json')
        if meta['key']!=key or set(meta['artifacts'])!=set(ARTIFACTS):return False
        for name,wanted in meta['artifacts'].items():
            path=directory/name;info=dev.regular(path)
            if info.st_uid!=os.getuid() or not info.st_mode&0o100 or dev.sha(path)!=wanted:return False
        return True
    except (OSError,ValueError,KeyError,dev.WorkflowError):return False


def build(run,cache,headers,environment,phase_prefix="build"):
    # Only native inputs participate; docs/Python changes do not force relinking.
    inputs={n:dev.sha(ROOT/n) for n in dev.source_files(ROOT)
            if Path(n).suffix in ('.cpp','.hpp','.h') and (n.startswith('collector/') or n.startswith('tests/unit/m3_') or n=='tests/integration/m3_fixture_producer.cpp')}
    key=digest(dict(version=1,inputs=inputs,dependencies=environment,
                    recipe=hashlib.sha256(inspect.getsource(build).encode()).hexdigest(),artifacts=ARTIFACTS))
    cache=dev.private_dir(cache);directory=cache/key
    candidates=[directory,*sorted(cache.glob(key+'-retry-*'))]
    valid=next((p for p in candidates if build_valid(p,key)),None)
    hit=valid is not None
    if hit:directory=valid
    run.report['build']=dict(key=key,cache_hit=hit,dependencies=environment)
    if hit:return directory
    # Retain invalid/partial builds as evidence; never silently reuse them.
    if directory.exists():directory=cache/(key+'-'+dev.unique('retry'))
    directory.mkdir(mode=0o700)
    compiler=environment['compiler'];flags=[*FLAGS,'-I'+str(headers)]
    common=[str(p) for group in ('pilot','journal') for p in
        (Path('collector/src')/group/'contract.cpp',Path('collector/src')/group/'transport.cpp')]
    audit=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'collector/src/audit').glob('*.cpp'))]
    def compile(name,sources,extra=()):
        run.phase(phase_prefix+'_'+name.replace('-','_'),[compiler,*flags,*sources,*extra,'-o',str((run.work or directory)/name)],unprivileged=True)
    compile('hids-audit-plugin',audit+common,['-l:libauparse.so.0'])
    compile('hids-m3-health',['collector/src/health/main.cpp','collector/src/health/snapshot.cpp'])
    compile('health-isolation-probe',['tests/unit/m3_health_isolation_probe.cpp','collector/src/health/snapshot.cpp'])
    producer=[p for p in audit if not p.endswith(('plugin_main.cpp','auparse_execution.cpp','current_tail.cpp'))]
    compile('producer',producer+common+['tests/integration/m3_fixture_producer.cpp'])
    for name,extra in (('init',[]),('allocate',['-DHIDS_M3_FAULT_ALLOCATE'])):
        compile('hids-audit-plugin-'+name+'-fault',audit+common+['tests/unit/m3_auparse_init_fault.cpp'],
            [*extra,'-Wl,--wrap=auparse_init','-l:libauparse.so.0'])
    if run.work:
        for name in ARTIFACTS:
            dev.regular(run.work/name)
            atomic_bytes(directory/name,(run.work/name).read_bytes(),0o755)
    private_json(directory/'build.json',dict(key=key,artifacts={n:dev.sha(directory/n) for n in ARTIFACTS}))
    return directory


def command(*args):return subprocess.check_output(args,stderr=subprocess.STDOUT,timeout=20)
def stopped():
    return all(command('systemctl','show',u,'-p','ActiveState','--value').strip()==b'inactive' for u in UNITS)
def stop():
    command('systemctl','stop',*UNITS)
    # Only called after ownership of this isolated lab run is established.
    # Test-induced failed/start-limit states must not contaminate the next phase.
    for unit in UNITS:
        if command('systemctl','show',unit,'-p','ActiveState','--value').strip()==b'failed':
            command('systemctl','reset-failed',unit)
def policy():
    files=[Path('/etc/audit/auditd.conf'),*sorted(Path('/etc/audit/plugins.d').glob('*.conf'))]
    return dict(files={str(p):dev.sha(p) for p in files},rules=command('auditctl','-l').decode())


@contextmanager
def owner():
    account=pwd.getpwnam('hids-ingest');uid,gid=os.geteuid(),os.getegid()
    try:
        os.setegid(account.pw_gid);os.seteuid(account.pw_uid);yield
    finally:os.seteuid(uid);os.setegid(gid)


def activation_count():
    with owner():
        path=Path('/var/lib/hids/m3/control.sqlite')
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:return db.execute('SELECT COUNT(*) FROM m3_intervals').fetchone()[0]
        finally:db.close()


def preflight(args):
    check(sys.platform=='linux' and os.getuid()==0 and os.geteuid()==0,'guest workflow requires VM root')
    check(platform.machine()=='aarch64','only the verified AArch64 profile is supported')
    check(Path('/etc/os-release').read_text().find('VERSION_ID="26.04"')>=0,'Ubuntu 26.04 required')
    check(stopped(),'stop M3/checker units before starting; do not interrupt an active session')
    required=[FIXTURE,'packaging/hids-audit-launcher','packaging/systemd/hids-m3.tmpfiles.conf',
              *('packaging/systemd/'+name for name in UNITS)]
    check(all((ROOT/name).is_file() for name in required),'source snapshot lacks required fixture/deployment artifacts')
    for name in ('hids-ingest','hids-audit'):pwd.getpwnam(name)
    check(command('systemctl','is-active','auditd').strip()==b'active','Audit must already be active')
    check(shutil.disk_usage('/var/lib/hids/m3').free>2*1024**3,'at least 2 GiB free required for this lab run')
    config=Path('/etc/hids/m3.json');info=config.lstat()
    check(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022,'unsafe HIDS config')
    original=config.read_bytes();settings=json.loads(original)
    count=activation_count();budget=args.lab_activation_budget or settings['max_activations']
    check(budget>=settings['max_activations'] and budget<=65536,'lab budget may only increase within valid range')
    check(budget-count>=BUDGET[args.tier],'insufficient retained activation capacity; choose an explicit lab budget, never delete history')
    return config,original,info,settings,count,budget


def deploy(run,build_dir):
    check(stopped(),'deployment requires stopped services')
    mappings={str(p.relative_to(ROOT)):Path('/usr/lib/hids')/p.relative_to(ROOT)
              for p in sorted((ROOT/'engine').rglob('*.py'))}
    for name in ('hids-audit-plugin','hids-m3-health'):
        mappings['@'+name]=Path('/usr/lib/hids')/name
    for name in UNITS:mappings['packaging/systemd/'+name]=Path('/etc/systemd/system')/name
    mappings['packaging/systemd/hids-m3.tmpfiles.conf']=Path('/usr/lib/tmpfiles.d/hids-m3.conf')
    mappings['packaging/hids-audit-launcher']=Path('/usr/lib/hids/hids-audit-launcher')
    backups=run.path/'deployment-backup';backups.mkdir(mode=0o700)
    inventory=[]
    for index,(source,target) in enumerate(mappings.items()):
        check(not target.is_symlink(),'refuse deployment symlink')
        record=dict(source=source,target=str(target),previous=None)
        if target.exists():
            info=dev.regular(target);check(info.st_uid==0,'deployment target not root-owned')
            backup=backups/str(index);dev.write_new(backup,target.read_bytes(),private=True)
            record['previous']=dict(backup=str(backup),sha256=dev.sha(backup),mode=stat.S_IMODE(info.st_mode))
        inventory.append(record)
    private_json(run.path/'deployment.json',inventory)
    for record in inventory:
        source=record['source'];target=Path(record['target'])
        target.parent.mkdir(parents=True,exist_ok=True)
        data=(build_dir/source[1:] if source.startswith('@') else ROOT/source).read_bytes()
        executable=source.startswith('@') or source=='packaging/hids-audit-launcher'
        atomic_bytes(target,data,0o755 if executable else 0o644)
        record['sha256']=hashlib.sha256(data).hexdigest()
        check(dev.sha(target)==record['sha256'],'installed digest mismatch')
    command('systemctl','daemon-reload')
    command('systemd-tmpfiles','--create','/usr/lib/tmpfiles.d/hids-m3.conf')
    private_json(run.path/'installed.json',inventory)
    run.report['installed_files']=len(inventory)


def installed_tests(run,args,directory):
    def step(*command,**options):
        run.phase(*command,**options);stop()
    python=[sys.executable,'-B'];base='tests/integration/'
    producer=directory/'producer'
    if run.work:
        producer=run.work/'transport-producer'
        atomic_bytes(producer,(directory/'producer').read_bytes(),0o755)
    step('transport',python+['-m','tests.integration.test_m3_fixture_transport',str(producer)],unprivileged=True)
    for name in ('event','storage'):
        step('installed_'+name,python+[base+'m3_'+name+'_ubuntu.py'])
    if args.tier!='checkpoint':return
    command('systemctl','start','hids-m3.socket')
    runtime=python+[base+'m3_runtime_ubuntu_acceptance.py',FIXTURE,'--capacity-limits']
    if args.live_audit:runtime.append('--live-audit')
    step('runtime',runtime,timeout=240)
    step('load',python+[base+'m3_load_ubuntu.py',FIXTURE,'--events','4096'],timeout=300)
    step('resources',python+[base+'m3_resource_ubuntu.py'])
    # Fault/probe executables are restored/removed even if a test fails.
    for kind,code in (('init','collector_parser_failure'),('allocate','collector_capacity')):
        name='hids-audit-plugin-'+kind+'-fault'
        with temporary_binary(directory/name,Path('/usr/lib/hids')/name):
            step('installed_'+kind+'_fault',python+[base+'m3_parser_failure_ubuntu.py',
                '/usr/lib/hids/'+name,'--expected-code',code])
    with temporary_binary(directory/'health-isolation-probe',Path('/usr/lib/hids/health-isolation-probe')):
        step('health',python+[base+'m3_health_ubuntu.py',FIXTURE,
            '--isolation-probe','/usr/lib/hids/health-isolation-probe'])
    if args.live_audit:
        step('health_periodic',python+[base+'m3_health_periodic_ubuntu.py'])
    step('health_lifecycle',python+[base+'m3_health_lifecycle_ubuntu.py'])


@contextmanager
def temporary_binary(source,target):
    old=None;mode=None
    if target.exists():
        info=dev.regular(target);check(info.st_uid==0,'unsafe previous probe')
        old=target.read_bytes();mode=stat.S_IMODE(info.st_mode)
    atomic_bytes(target,source.read_bytes(),0o755)
    try:yield
    finally:
        stop()
        if old is None:target.unlink()
        else:atomic_bytes(target,old,mode)


def guest(args):
    check(sys.platform=='linux' and os.getuid()==0,'guest requires root')
    check(args.experiment not in ('rotation','native') or args.live_audit,'source experiment requires explicit --live-audit lab scope')
    _,source=dev.verify(ROOT,args.expected_manifest)
    run=Run(args.output,'ubuntu_'+args.tier+'_'+args.experiment,source);error=None;baseline=None;config=None
    # Serialize all lab work sharing installed services and state.
    lock=Path('/run/lock/hids-m3-workflow.lock')
    fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        check(os.fstat(fd).st_uid==0 and stat.S_IMODE(os.fstat(fd).st_mode)==0o600,'unsafe workflow lock')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        environment=dependency_info(args.headers.resolve())
        config,original,info,settings,count,budget=preflight(args)
        baseline=policy();private_json(run.path/'baseline.json',dict(policy=baseline,config=settings,activation_count=count))
        run.report['preflight']=dict(activation_count=count,lab_activation_budget=budget,live_audit=args.live_audit)
        offline(run,args.tier,args.headers.resolve())
        cache=args.cache_root or Path(args.output).absolute()/'builds'
        run.report['cache_root']=str(cache)
        directory=build(run,cache,args.headers.resolve(),environment)
        if args.experiment=='performance':
            check(args.baseline_root is not None and args.baseline_manifest,'verified baseline snapshot required')
            _,before_sha=dev.verify(args.baseline_root,args.baseline_manifest)
            run.report['baseline_source_sha256']=before_sha
            after_build=run.report['build'];current_root=ROOT
            globals()['ROOT']=args.baseline_root.resolve()
            try:
                before_env=dependency_info(args.headers.resolve())
                before=build(run,cache,args.headers.resolve(),before_env,'build_before')
                run.report['baseline_build']=run.report['build']
            finally:globals()['ROOT']=current_root;run.report['build']=after_build
            run.phase('performance',[sys.executable,'-B','tests/integration/m3_performance_ubuntu.py',
                '--before',str(args.baseline_root),'--before-plugin',str(before/'hids-audit-plugin'),
                '--after',str(ROOT),'--after-plugin',str(directory/'hids-audit-plugin'),
                '--events',str(args.events),'--history-files',str(args.history_files),'--output',str(run.path/'performance.json')],timeout=900)
            dev.verify(args.baseline_root,args.baseline_manifest)
        else:
            settings['max_activations']=budget
            atomic_bytes(config,dev.json_bytes(settings),stat.S_IMODE(info.st_mode));os.chown(config,info.st_uid,info.st_gid)
            deploy(run,directory)
            if args.experiment=='soak':
                run.phase('long_load',[sys.executable,'-B','tests/integration/m3_load_ubuntu.py',FIXTURE,
                    '--events',str(args.events),'--duration-seconds',str(args.duration_seconds),'--varied',
                    '--progress',str(run.path/'load-progress.json')],
                    timeout=args.duration_seconds+180)
            elif args.experiment=='rotation':
                run.phase('rotation',[sys.executable,'-B','tests/integration/m3_rotation_ubuntu.py','--live-audit'],timeout=180)
            elif args.experiment=='native':
                run.phase('native_workload',[sys.executable,'-B','tests/integration/m3_native_workload_ubuntu.py','--live-audit'],timeout=180)
            elif args.experiment=='filesystem':
                run.phase('filesystem',[sys.executable,'-B','tests/integration/m3_filesystem_ubuntu.py'],timeout=180)
            elif args.experiment=='quota':
                helper=run.path/'quota-helper'
                run.phase('build_quota_helper',['c++','-std=c++20','-Wall','-Wextra','-Wpedantic','-Werror',
                    'tests/integration/m3_quota_helper.cpp','-o',str(helper)])
                os.chmod(helper,0o700)
                run.phase('quota',[sys.executable,'-B','tests/integration/m3_quota_ubuntu.py','--helper',str(helper)],timeout=180)
            else:installed_tests(run,args,directory)
    except Exception as exc:error=str(exc)
    finally:
        if baseline is not None:
            try:
                stop()
                atomic_bytes(config,original,stat.S_IMODE(info.st_mode));os.chown(config,info.st_uid,info.st_gid)
                check(policy()==baseline,'NEEDS ATTENTION: Audit policy differs; protected baseline retained')
                check(config.read_bytes()==original and stopped(),'final cleanup failed')
                account=pwd.getpwnam('hids-ingest');state=Path('/var/lib/hids/m3')
                check(stat.S_IMODE(state.stat().st_mode)==0o700,'state directory permissions differ')
                check(all(p.stat().st_uid==account.pw_uid and stat.S_IMODE(p.stat().st_mode)==0o600
                          for p in state.iterdir() if p.is_file()),'state permissions differ')
                check(command('systemctl','is-active','auditd').strip()==b'active','Audit no longer active')
                installed=run.path/'installed.json'
                if installed.exists():
                    check(all(dev.sha(Path(r['target']))==r['sha256'] for r in dev.read_json(installed)),
                          'installed artifacts changed during acceptance')
                dev.verify(ROOT,args.expected_manifest)
                run.report['cleanup']='verified'
            except Exception as exc:
                error=(error+'; ' if error else '')+str(exc);run.report['cleanup']='needs_attention'
        os.close(fd)
        run.finish(error)
    return 1 if error else 0


def archive_metadata(info):
    # Source bytes are pinned by the manifest; do not preserve irrelevant host
    # timestamps/identities or flood logs when guest and host clocks differ.
    info.mtime=0;info.uid=0;info.gid=0;info.uname='';info.gname=''
    info.pax_headers={}
    return info


def ssh_options(args,tty=False):
    check(re.fullmatch(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.:-]+',args.host) is not None,'explicit user@host required')
    check(args.known_hosts.is_file(),'existing known-hosts file required')
    return ['ssh',*(['-tt'] if tty else ['-T']),'-o','ConnectTimeout=8',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(args.known_hosts.resolve()),args.host]


def baseline_snapshot(ref,state):
    commit=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',ref+'^{commit}'],cwd=ROOT,text=True).strip()
    check(re.fullmatch('[0-9a-f]{40}',commit) is not None,'invalid baseline commit')
    exports=dev.private_dir(state/'exports');directory=exports/dev.unique('baseline');directory.mkdir(mode=0o700)
    archive=directory/'source.tar'
    with archive.open('xb') as out:
        subprocess.run(['git','archive','--format=tar',commit],cwd=ROOT,stdout=out,check=True)
    source=directory/'source';source.mkdir(mode=0o700)
    with tarfile.open(archive) as stream:
        for member in stream:
            rel=Path(member.name)
            check(not rel.is_absolute() and '..' not in rel.parts and (member.isdir() or member.isfile()),'unsafe baseline archive')
            target=source/rel
            if member.isdir():dev.private_dir(target)
            else:
                check(member.size<=32*1024*1024,'baseline file too large')
                dev.private_dir(target.parent)
                with stream.extractfile(member) as incoming,target.open('xb') as output:shutil.copyfileobj(incoming,output)
    path,sha,_=dev.create_snapshot(source,state)
    return path,sha,commit


def remote(args):
    check(os.getuid()!=0,'host workflow runs as an ordinary user')
    check(args.experiment not in ('rotation','native') or args.live_audit,'source experiment requires explicit --live-audit lab scope')
    state=dev.private_dir(args.state_dir.absolute())
    start=time.monotonic()
    snapshot,manifest,count=dev.create_snapshot(ROOT,state)
    run=Run(state/'runs','host_orchestration',manifest);error=None;dispatched=False
    try:
        before=None
        if args.experiment=='performance':
            check(args.baseline_ref is not None,'--baseline-ref required for a controlled performance run')
            before,before_sha,commit=baseline_snapshot(args.baseline_ref,state)
            run.report['baseline_commit']=commit
        ssh=ssh_options(args)
        destination=subprocess.check_output([*ssh,shlex.join(['python3','-c',
            'import tempfile;print(tempfile.mkdtemp(prefix="hids-m3-source."))'])],text=True).strip()
        check(re.fullmatch(r'/tmp/hids-m3-source\.[a-zA-Z0-9_-]+',destination) is not None,'unexpected guest staging path')
        archive=run.path/'source.tar'
        with tarfile.open(archive,'x',format=tarfile.PAX_FORMAT) as stream:
            stream.add(snapshot,arcname=snapshot.name,filter=archive_metadata)
            if before:stream.add(before,arcname=before.name,filter=archive_metadata)
        os.chmod(archive,0o600)
        with archive.open('rb') as stream:
            subprocess.run([*ssh,shlex.join(['tar','xf','-','-C',destination])],stdin=stream,check=True)
        guest_root=destination+'/'+snapshot.name
        argv=['python3','-B',guest_root+'/scripts/m3_workflow.py','guest','--expected-manifest',manifest,
            '--output',args.guest_output,'--cache-root',args.guest_output+'/builds','--headers',args.headers,'--tier',args.tier,
            '--experiment',args.experiment,'--events',str(args.events),'--duration-seconds',str(args.duration_seconds),
            '--history-files',str(args.history_files)]
        if before:argv+=['--baseline-root',destination+'/'+before.name,'--baseline-manifest',before_sha]
        if args.live_audit:argv.append('--live-audit')
        if args.lab_activation_budget:argv+=['--lab-activation-budget',str(args.lab_activation_budget)]
        # Authentication is interactive terminal IO, never stored in scripts/logs.
        if args.detach:
            job='hids-m3-lab-'+uuid_token()
            job_output=args.guest_output+'/jobs/'+job
            argv[argv.index('--output')+1]=job_output
            limit=(args.duration_seconds if args.experiment=='soak' else 900)+1200
            start_command=['systemd-run','--quiet','--unit',job,'--property=UMask=0077',
                '--property=WorkingDirectory='+guest_root,'--property=RuntimeMaxSec='+str(limit),
                '--property=TimeoutStopSec=30','--property=KillMode=control-group']
            payload='exec '+shlex.join(start_command)+' --setenv=SUDO_UID="$SUDO_UID" -- '+shlex.join(argv)
            result=subprocess.run([*ssh_options(args,True),shlex.join(['sudo','-p','HIDS-SUDO:','sh','-c',payload])])
            check(result.returncode==0,'VM job dispatch failed')
            dispatched=True;run.report.update(job=job,guest_output=job_output)
            print(json.dumps(dict(status='dispatched',job=job,guest_output=job_output)),flush=True)
        else:
            result=subprocess.run([*ssh_options(args,True),
                'cd '+shlex.quote(guest_root)+' && '+shlex.join(['sudo','-p','HIDS-SUDO:',*argv])])
            check(result.returncode==0,'guest workflow failed; see printed private guest report')
        run.report.update(snapshot_files=count,guest_source=guest_root)
    except Exception as exc:error=str(exc)
    run.report['wall_seconds']=round(time.monotonic()-start,3)
    run.finish(error,dispatched=dispatched)
    return 1 if error else 0


def uuid_token():
    import uuid
    return uuid.uuid4().hex[:12]


def vm_status(args):
    check(re.fullmatch('hids-m3-lab-[0-9a-f]{12}',args.job) is not None,'invalid lab job name')
    code='''import json,pathlib,subprocess,sys
p=pathlib.Path(sys.argv[1]);job=sys.argv[2]
c=subprocess.run(['systemctl','show',job,'-p','ActiveState','-p','Result','-p','ExecMainStatus'],capture_output=True,text=True)
u=dict(line.split('=',1) for line in c.stdout.splitlines() if '=' in line)
files=sorted(p.glob('run-*/report.json'))
r=json.loads(files[-1].read_text()) if files else None
progress=sorted(p.glob('run-*/load-progress.json'))
heartbeat=json.loads(progress[-1].read_text()) if progress else None
state='running' if u.get('ActiveState') in ('active','activating') else 'incomplete'
if r and u.get('ActiveState') not in ('active','activating'):state='passed' if r['status']=='passed' and u.get('ActiveState')!='failed' and u.get('ExecMainStatus','0')=='0' else 'failed'
payload=dict(job=job,status=state,unit=u,report=str(files[-1]) if files else None,error=r.get('error') if r else None,progress=heartbeat)
'''
    if args.compact:
        code+='''if heartbeat and state=='running':
 s=heartbeat['sample'];payload=dict(status=state,events=s['events'],elapsed_seconds=s['elapsed_seconds'],backend_rss_kib=s['backend']['VmRSS'],collector_rss_kib=s['collector']['VmRSS'],storage=s['storage']['state'])
'''
    code+='print(json.dumps(payload,sort_keys=True),flush=True)\n'
    if args.watch_seconds:
        check(1<=args.watch_seconds<=18000,'watch duration out of range')
        code=('import time\nwatch_end=time.monotonic()+'+str(args.watch_seconds)+'\nwhile True:\n'+
              textwrap.indent(code,'    ')+
              "    if state != 'running' or time.monotonic()>=watch_end:break\n    time.sleep(60)\n")
    target=args.guest_output+'/jobs/'+args.job
    return subprocess.run([*ssh_options(args,True),shlex.join(['sudo','-p','HIDS-SUDO:','python3','-B','-c',code,target,args.job])]).returncode


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    plan=sub.add_parser('plan');plan.add_argument('--tier',choices=('focused','component','checkpoint'),default='focused')
    summary=sub.add_parser('summary');summary.add_argument('reports',type=Path,nargs='+')
    local=sub.add_parser('local');local.add_argument('--tier',choices=('focused','component'),default='focused')
    local.add_argument('--output',type=Path,default=Path(tempfile.gettempdir()).resolve()/'hids-m3-workflow-local')
    status=sub.add_parser('vm-status');status.add_argument('--host',required=True)
    status.add_argument('--known-hosts',type=Path,required=True);status.add_argument('--job',required=True)
    status.add_argument('--guest-output',default='/var/tmp/hids-m3-workflow')
    status.add_argument('--watch-seconds',type=int,default=0);status.add_argument('--compact',action='store_true')
    vm=sub.add_parser('vm');vm.add_argument('--detach',action='store_true');vm.add_argument('--host',required=True);vm.add_argument('--known-hosts',type=Path,required=True)
    vm.add_argument('--state-dir',type=Path,required=True);vm.add_argument('--guest-output',default='/var/tmp/hids-m3-workflow')
    vm.add_argument('--baseline-ref')
    vm.add_argument('--headers',required=True,help='Existing absolute guest Audit header directory')
    guest_parser=sub.add_parser('guest');guest_parser.add_argument('--expected-manifest',required=True)
    guest_parser.add_argument('--output',type=Path,default=Path('/var/tmp/hids-m3-workflow'))
    guest_parser.add_argument('--headers',type=Path,required=True)
    guest_parser.add_argument('--cache-root',type=Path)
    guest_parser.add_argument('--baseline-root',type=Path);guest_parser.add_argument('--baseline-manifest')
    for part in (vm,guest_parser):
        part.add_argument('--tier',choices=('component','checkpoint'),default='component')
        part.add_argument('--live-audit',action='store_true',help='Explicit lab scope: temporary Audit rule/plugin/report tests, restored afterward')
        part.add_argument('--lab-activation-budget',type=int)
        part.add_argument('--experiment',choices=('acceptance','performance','soak','rotation','native','filesystem','quota'),default='acceptance')
        part.add_argument('--events',type=int,default=4096)
        part.add_argument('--duration-seconds',type=int,default=7200)
        part.add_argument('--history-files',type=int,default=0)
    args=parser.parse_args(argv)
    try:
        if args.command=='plan':
            print(json.dumps(dict(tier=args.tier,offline=['python','workflow']+([] if args.tier=='focused' else
                ['sanitized_native','crash']),installed=[] if args.tier=='focused' else
                (['transport','event','storage'] if args.tier=='component' else
                 ['transport','event','storage','runtime','load','resources','parser_faults','health','health_lifecycle']),
                live_audit_opt_in=True,reboot='separate operator test; never automatic'),sort_keys=True));return 0
        if args.command=='summary':
            for path in args.reports:
                report=dev.read_json(path)
                check(report.get('report_version')==1 and report.get('status') in ('passed','failed','dispatched'),'invalid report')
                print(json.dumps({key:report.get(key) for key in ('scope','status','source_sha256','wall_seconds',
                    'phase_seconds','build_commands','retained_log_bytes','phase_console_bytes','cleanup','error')},sort_keys=True))
            return 0
        if args.command=='vm-status':return vm_status(args)
        if args.command=='vm':return remote(args)
        if args.command=='guest':return guest(args)
        run=Run(args.output,'local_'+args.tier,source_digest());error=None
        try:offline(run,args.tier)
        except Exception as exc:error=str(exc)
        run.finish(error);return 1 if error else 0
    except (OSError,ValueError,dev.WorkflowError) as exc:
        print('hids-m3-workflow: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
