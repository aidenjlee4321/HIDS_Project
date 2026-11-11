"""Explicit lab-only real Audit rotation with no deletion of existing logs.

No raw payload copies/archives. Keeps protected prefix hashes/inode metadata,
restores temporary plugin/format/rule changes, retains all HIDS history.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import sqlite3
import stat
import subprocess
import tempfile
import time


def run(*args):
    return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)


def settings(data):
    result={}
    for line in data.decode().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=map(str.strip,line.split('=',1));result[key]=value
    return result


def prefix_hash(path,length):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('untrusted log')
        digest=hashlib.sha256();remaining=length
        while remaining:
            block=os.read(fd,min(remaining,1024*1024))
            if not block:raise ValueError('original log truncated')
            digest.update(block);remaining-=len(block)
        return digest.hexdigest()
    finally:os.close(fd)


def inventory(active):
    values=[]
    for path in sorted(active.parent.iterdir()):
        if path.name!=active.name and not path.name.startswith(active.name+'.'):continue
        suffix=path.name[len(active.name):]
        if suffix and not re.fullmatch(r'\.[1-9][0-9]*',suffix):raise ValueError('unrecognized external log rotation')
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('untrusted log file')
        values.append(dict(path=str(path),suffix=int(suffix[1:]) if suffix else 0,
            device=info.st_dev,inode=info.st_ino,bytes=info.st_size,uid=info.st_uid,gid=info.st_gid,
            mode=stat.S_IMODE(info.st_mode),sha256=prefix_hash(path,info.st_size)))
    if not any(v['suffix']==0 for v in values):raise ValueError('active log missing')
    return values


def rotation_room(config,files,rotations):
    if config.get('max_log_file_action')!='ROTATE':raise ValueError('unsupported host retention policy')
    limit=int(config['num_logs']);ceiling=int(config['max_log_file'])*1024*1024
    if not 2<=limit<=999 or rotations<1:raise ValueError('invalid rotation budget')
    # Highest suffix matters even with gaps. Keep one extra slot for an
    # unexpected natural rotation; never cross the daemon's retirement boundary.
    if max(v['suffix'] for v in files)+rotations>limit-2:
        raise ValueError('insufficient no-deletion rotation headroom')
    active=next(v for v in files if v['suffix']==0)
    if ceiling-active['bytes']<1024*1024:raise ValueError('insufficient active-log byte headroom')


def preserved(before,after):
    current={(v['device'],v['inode']):v for v in after}
    for old in before:
        new=current.get((old['device'],old['inode']))
        if new is None:raise ValueError('original source inode disappeared')
        if new['uid']!=old['uid'] or new['gid']!=old['gid'] or new['mode']&~old['mode']:
            raise ValueError('source permissions broadened')
        if prefix_hash(Path(new['path']),old['bytes'])!=old['sha256']:
            raise ValueError('original source bytes changed')


def restore_all(actions):
    """Attempt every independent restoration even if an earlier one fails."""
    failures=[]
    for name,action in actions:
        try:action()
        except Exception:failures.append(name)
    if failures:raise RuntimeError('rotation cleanup needs attention: '+', '.join(failures))


def audit_status():
    return dict(line.split(None,1) for line in run('auditctl','-s').stdout.decode().splitlines() if len(line.split(None,1))==2)


def reader_pid():
    uid=pwd.getpwnam('hids-audit').pw_uid
    candidates=[]
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try:
                if path.stat().st_uid==uid and (path/'exe').resolve()==Path('/usr/lib/hids/hids-audit-plugin'):
                    candidates.append(int(path.name))
            except (OSError,PermissionError):pass
    if len(candidates)!=1:raise RuntimeError('single trusted reader not observed')
    return candidates[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-audit',action='store_true',required=True)
    args=parser.parse_args()
    assert os.getuid()==0 and args.live_audit
    from m3_runtime_ubuntu_acceptance import control,query,until
    import uuid
    units=('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')
    assert all(run('systemctl','show',u,'-p','ActiveState','--value').stdout.strip()==b'inactive' for u in units)
    assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
    assert run('auditctl','-l').stdout.strip()==b'No rules'
    configuration=Path('/etc/audit/auditd.conf');original=configuration.read_bytes();config=settings(original)
    active=Path(config['log_file']);assert active.is_absolute() and active.resolve()==active
    before=inventory(active);rotation_room(config,before,2)
    assert all(v['uid']==0 and not v['mode']&0o027 for v in before)
    workspace=Path(tempfile.mkdtemp(prefix='hids-m3-rotation.',dir='/root'));workspace.chmod(0o700)
    (workspace/'auditd.conf').write_bytes(original);(workspace/'auditd.conf').chmod(0o600)
    report=dict(scope='plugin_stream_rotation_no_retirement',before=before,rotations=[],executions=[])
    def save():
        (workspace/'report.json').write_text(json.dumps(report,sort_keys=True)+'\n');(workspace/'report.json').chmod(0o600)
    save()
    plugin=Path('/etc/audit/plugins.d/hids-m3-rotation-acceptance.conf')
    assert not plugin.exists() and not plugin.is_symlink()
    raw,count=re.subn(rb'(?m)^\s*log_format\s*=.*$',b'log_format = RAW',original);assert count==1
    activation=str(uuid.uuid4());rule=None;child=None;release=None;started=False;created_plugin=False
    try:
        run('systemctl','start','hids-m3.socket');control('activate',activation);started=True
        fd=os.open(plugin,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o640)
        created_plugin=True
        with os.fdopen(fd,'w') as stream:
            stream.write('active = yes\npath = /usr/lib/hids/hids-audit-launcher\ntype = always\nformat = string\n')
        configuration.write_bytes(raw);run('auditctl','--signal','reload')
        until(lambda:control('status')['source_ready'])
        initial=control('status');pid=reader_pid();kernel=audit_status()
        report.update(activation=activation,generation=initial['interval']['generation'],reader_pid=pid,kernel_before=kernel)
        def execute():
            nonlocal rule,child,release
            read,release=os.pipe();child=os.fork()
            if child==0:
                os.close(release);os.read(read,1);os.close(read)
                os.execv('/usr/bin/true',['true','rotation-acceptance','x'*10000])
            os.close(read);target=child
            rule=['always,exit','-F','arch=b64','-S','execve,execveat','-F',f'pid={target}','-k','hids_m3_rotation']
            run('auditctl','-a',*rule)
            os.write(release,b'x');os.close(release);release=None
            _,status=os.waitpid(child,0);child=None;assert status==0
            run('auditctl','-d',*rule);rule=None
            return target
        def accepted(target):
            rows=query(activation,'SELECT identity,payload FROM m3_execution')
            found=[(i,json.loads(p)) for i,p in rows if json.loads(p)['pid']==target]
            if not found:return False
            assert len(found)==1
            identity,event=found[0]
            assert event['exe_base64']==base64.b64encode(os.fsencode(os.path.realpath('/usr/bin/true'))).decode()
            assert event['comm_base64']=='dHJ1ZQ==' and event['success']
            assert query(activation,f"SELECT COUNT(*) FROM m3_eoe WHERE identity='{identity}'")==[(1,)]
            report['executions'].append(dict(pid=target,identity=identity));return True
        target=execute();until(lambda:accepted(target),timeout=12)
        for index in range(2):
            files=inventory(active);rotation_room(config,files,2-index)
            old_inode=active.stat().st_ino
            blocker=None
            try:
                if index==1:
                    # Hold only a short bounded lock; do not wait for completion
                    # while holding it or change the normal storage timeout.
                    from m3_runtime_ubuntu_acceptance import STATE
                    blocker=sqlite3.connect(STATE/f'{activation}.sqlite',isolation_level=None,timeout=1)
                    blocker.execute('BEGIN IMMEDIATE')
                target=execute()
                run('auditctl','--signal','rotate')
                if blocker:time.sleep(.25)
            finally:
                if blocker:blocker.rollback();blocker.close()
            until(lambda:active.stat().st_ino!=old_inode)
            until(lambda:accepted(target),timeout=12)
            after=inventory(active);preserved(before,after);preserved(files,after)
            status=control('status')
            assert status['source_ready'] and status['reader_connected'] and status['failure'] is None
            assert status['interval']['generation']==report['generation'] and reader_pid()==pid
            report['rotations'].append(dict(index=index+1,with_writer_lock=index==1,files=after,event_health=status['event_health']))
            save();print('PASS: real rotation '+str(index+1)+' preserves original logs, known execution, reader PID and plugin-stream generation',flush=True)
        final=audit_status();assert final['pid']==kernel['pid'] and final['lost']==kernel['lost']
        report.update(kernel_after=final,status_before_revocation=control('status'))
        assert len(report['executions'])==3
        control('deactivate',activation)
        assert len(query(activation,'SELECT identity FROM m3_execution'))>=3
        report['result']='passed';save()
    finally:
        def finish_child():
            if release is not None:os.close(release)
            if child:
                try:os.kill(child,signal.SIGKILL)
                except ProcessLookupError:pass
                os.waitpid(child,0)
        def revoke():
            if started:
                try:control('deactivate',activation)
                except Exception:pass  # final unit stop still runs independently
        def verify_policy():
            assert configuration.read_bytes()==original and run('auditctl','-l').stdout.strip()==b'No rules'
            assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
        restore_all([
            ('child',finish_child),
            ('rule',lambda:run('auditctl','-d',*rule) if rule else None),
            ('revocation',revoke),
            ('plugin',lambda:plugin.unlink(missing_ok=True) if created_plugin else None),
            ('configuration',lambda:configuration.write_bytes(original)),
            ('reload',lambda:run('auditctl','--signal','reload')),
            ('units',lambda:run('systemctl','stop',*units)),
            ('policy verification',verify_policy),
            ('source verification',lambda:preserved(before,inventory(active))),
        ])
        report['restoration']='verified';save()
        print('Restored original Audit policy; all original source bytes/inodes retained; private report '+str(workspace/'report.json'),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
