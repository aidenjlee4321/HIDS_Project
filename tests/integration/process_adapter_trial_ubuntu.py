"""Owner-approved, one-shot native trial; native payload stays root-private on VM."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import resource
import signal
import stat
import subprocess
import sys
import tempfile
import time

BINARY_SHA = 'b5e3327b74c9018a2228438c8193bfd093464a95451aad6a4e7c56336452b5ca'
ROLE = 'hids-process'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def write_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def identity():
    role = pwd.getpwnam(ROLE)
    group = grp.getgrnam(ROLE)
    require(role.pw_uid > 0 and role.pw_gid == group.gr_gid > 0, 'distinct nonroot role required')
    require(role.pw_shell == '/usr/sbin/nologin' and role.pw_dir == '/nonexistent', 'unexpected account attributes')
    require(not any(ROLE in g.gr_mem for g in grp.getgrall()), 'supplementary membership refused')
    require(not any(p.pw_uid == role.pw_uid and p.pw_name != ROLE for p in pwd.getpwall()), 'shared UID refused')
    return role


def command(role, executable, *args):
    return ['/usr/bin/setpriv', '--reuid='+str(role.pw_uid), '--regid='+str(role.pw_gid),
            '--clear-groups', '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all',
            '--no-new-privs', '--', str(executable), *args]


def limits():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16384, 16384))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (128*1024*1024, 128*1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (8, 8))


def environment():
    return {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LANG':'C', 'LC_ALL':'C'}


def inspect_root(root):
    root = Path(root)
    s = root.lstat()
    require(root.parent == Path('/opt') and root.name.startswith('hids-process-trial.'), 'invalid trial root')
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o750, 'unsafe trial root')
    role = identity()
    require(s.st_gid == role.pw_gid, 'unexpected trial group')
    p = root/'trial'
    s = p.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_gid == role.pw_gid and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o550, 'unsafe pinned executable')
    require(hashlib.sha256(p.read_bytes()).hexdigest() == BINARY_SHA, 'pinned executable changed')
    private = root/'private'; s = private.lstat()
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o700, 'unsafe report directory')
    return root, role


def prepare(binary):
    data = Path(binary).read_bytes()
    require(hashlib.sha256(data).hexdigest() == BINARY_SHA, 'tested binary mismatch')
    try:
        pwd.getpwnam(ROLE)
    except KeyError:
        try:
            grp.getgrnam(ROLE)
        except KeyError:
            pass
        else:
            raise RuntimeError('pre-existing unexpected group refused')
        subprocess.run(['/usr/sbin/useradd', '--system', '--user-group', '--no-create-home',
                        '--home-dir', '/nonexistent', '--shell', '/usr/sbin/nologin', ROLE], check=True)
    role = identity()
    root = Path(tempfile.mkdtemp(prefix='hids-process-trial.', dir='/opt'))
    os.chown(root, 0, role.pw_gid); os.chmod(root, 0o750)
    (root/'private').mkdir(mode=0o700)
    fd = os.open(root/'trial', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o500)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.chown(root/'trial', 0, role.pw_gid); os.chmod(root/'trial', 0o550)
    inspect_root(root)
    p = subprocess.run(command(role, root/'trial', '--self-test'), capture_output=True,
                       env=environment(), cwd='/', preexec_fn=limits, timeout=10)
    require(p.returncode == 0 and b'12 offline invariant groups passed' in p.stdout, 'role offline self-test failed')
    check = '''import os,pathlib,json,sys
s=pathlib.Path('/proc/self/status').read_text().splitlines()
c={k:v.strip() for k,v in (x.split(':',1) for x in s if ':' in x)}
assert all(int(c[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
assert c['NoNewPrivs']=='1' and not os.getgroups()
try:os.listdir(sys.argv[1])
except PermissionError:pass
else:raise AssertionError('private report readable')
print('identity_and_private_directory_passed')'''
    p = subprocess.run(command(role,'/usr/bin/python3','-I','-B','-c',check,str(root/'private')),
                       capture_output=True, env=environment(),cwd='/',preexec_fn=limits,timeout=10)
    require(p.returncode==0 and p.stdout.strip()==b'identity_and_private_directory_passed','role boundary check failed')
    write_private(root/'private'/'prepared.json', {'binary_sha256':BINARY_SHA,'uid':role.pw_uid,
                  'gid':role.pw_gid,'offline_role_checks':True,'live_attempted':False})
    print(json.dumps({'prepared':str(root),'offline_role_checks':True,'uid':role.pw_uid,'gid':role.pw_gid}))


def live(root):
    root, role = inspect_root(root)
    require((root/'private'/'prepared.json').is_file(), 'preparation missing')
    # A durable marker precedes any launch: never silently rerun this live scope.
    write_private(root/'private'/'live-attempt.json', {'started':time.time(),'binary_sha256':BINARY_SHA})
    fd = os.open(root/'private'/'native.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    timed_out=False;forced=False
    try:
        with (root/'private'/'stdout').open('xb') as out,(root/'private'/'stderr').open('xb') as err:
            os.chmod(root/'private'/'stdout',0o600);os.chmod(root/'private'/'stderr',0o600)
            child = subprocess.Popen(command(role,root/'trial','--live','--report-fd',str(fd)),
                         stdin=subprocess.DEVNULL,stdout=out,stderr=err,pass_fds=(fd,),
                         env=environment(),cwd='/',preexec_fn=limits,start_new_session=True)
            try:
                code=child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                timed_out=True;os.killpg(child.pid,signal.SIGTERM)
                try:code=child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    forced=True;os.killpg(child.pid,signal.SIGKILL);code=child.wait(timeout=3)
    finally:
        os.close(fd)
    native_path=root/'private'/'native.json'
    require(native_path.stat().st_size<=16384,'oversize native report')
    native=json.loads(native_path.read_text()) if native_path.stat().st_size else {}
    # Only these aggregate outcomes can be returned to project/chat. Never native events.
    allowed=('owned_lifecycle_observed','subscription_acknowledged','any_delivery_observed',
             'incomplete_interval','capture_overflow','child_cleanup_forced','open_calls',
             'control_send_calls','close_calls','open_errno','listen_send_errno',
             'ignore_send_errno','close_errno','ignore_completion')
    summary={k:native[k] for k in allowed if k in native}
    summary.update(exit_code=code,timed_out=timed_out,forced_termination=forced,
                   retained_event_count=len(native.get('events',[])),binary_sha256=BINARY_SHA)
    write_private(root/'private'/'summary.json',summary)
    print(json.dumps({'trial_root':str(root),'summary':summary},sort_keys=True))


if __name__=='__main__':
    require(os.getuid()==0 and os.geteuid()==0,'root supervisor required')
    os.umask(0o077)
    require(len(sys.argv)==3 and sys.argv[1] in ('prepare','live'),'explicit prepare/live required')
    if sys.argv[1]=='prepare':prepare(sys.argv[2])
    else:live(sys.argv[2])
