"""Explicit root-only native execution matrix; lab policy restored, no raw copies."""
import argparse
import base64
import ctypes
import json
import os
from pathlib import Path
import pwd
import re
import signal
import tempfile
import uuid
from m3_rotation_ubuntu import inventory,preserved,restore_all,run,settings
from m3_runtime_ubuntu_acceptance import control,query,until

UNITS=('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-audit',action='store_true',required=True)
    parser.parse_args();assert os.getuid()==0
    assert all(run('systemctl','show',u,'-p','ActiveState','--value').stdout.strip()==b'inactive' for u in UNITS)
    assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
    assert run('auditctl','-l').stdout.strip()==b'No rules'
    config=Path('/etc/audit/auditd.conf');original=config.read_bytes();policy=settings(original)
    active=Path(policy['log_file']);assert active.is_absolute() and active.resolve()==active
    before=inventory(active);current=next(v for v in before if v['suffix']==0)
    assert int(policy['max_log_file'])*1024*1024-current['bytes']>=2*1024*1024
    workspace=Path(tempfile.mkdtemp(prefix='hids-m3-native-workload.',dir='/root'));workspace.chmod(0o700)
    backup=workspace/'auditd.conf';backup.write_bytes(original);backup.chmod(0o600)
    byte_path=os.fsencode(workspace)+b'/byte name-\xff'
    source=Path('/usr/bin/true').read_bytes()
    fd=os.open(byte_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o700)
    with os.fdopen(fd,'wb') as stream:stream.write(source)
    script=workspace/'script-case';script.write_bytes(b'#!/bin/sh\nexit 0\n');script.chmod(0o700)
    nobody=pwd.getpwnam('nobody')
    cases=[
        ('plain','exec',b'/usr/bin/true',[b'true'],0),
        ('empty_argument','exec',b'/usr/bin/true',[b'true',b''],0),
        ('encoded_arguments','exec',b'/usr/bin/true',[b'true',b'space newline\nbyte-\xff'],0),
        ('fragmented_argument','exec',b'/usr/bin/true',[b'true',b'x'*10000],0),
        ('byte_path','exec',byte_path,[b'byte name-\xff'],0),
        ('script','exec',os.fsencode(script),[b'script-case'],0),
        ('execveat_empty_path','execveat',b'/usr/bin/true',[b'true',b'fd-exec'],0),
        ('nonroot_identity','exec',b'/usr/bin/true',[b'true'],nobody.pw_uid),
        ('failed_exec','failed',os.fsencode(workspace/'does-not-exist'),[b'no-such-program'],0),
    ]
    activation=str(uuid.uuid4());plugin=Path('/etc/audit/plugins.d/hids-m3-native-workload.conf')
    assert not plugin.exists() and not plugin.is_symlink()
    raw,count=re.subn(rb'(?m)^\s*log_format\s*=.*$',b'log_format = RAW',original);assert count==1
    report={'scope':'real_native_execution_matrix','cases':[],'source_before':before}
    def save():
        out=workspace/'report.json';out.write_text(json.dumps(report,sort_keys=True)+'\n');out.chmod(0o600)
    save();rule=None;child=None;release=None;created=False;started=False
    loginuid=int(Path('/proc/self/loginuid').read_text());session=int(Path('/proc/self/sessionid').read_text())
    try:
        run('systemctl','start','hids-m3.socket');control('activate',activation);started=True
        fd=os.open(plugin,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o640);created=True
        with os.fdopen(fd,'w') as stream:
            stream.write('active = yes\npath = /usr/lib/hids/hids-audit-launcher\ntype = always\nformat = string\n')
        config.write_bytes(raw);run('auditctl','--signal','reload');until(lambda:control('status')['source_ready'])
        initial=control('status');report['activation']=activation;report['generation']=initial['interval']['generation']
        kernel_before=run('auditctl','-s').stdout
        # Exercise unrelated shared-stream traffic deliberately, rather than
        # depending on the health timer's incidental schedule.
        run('auditctl','-m','hids native background fixture')
        run('systemctl','start','hids-m3-health.service')
        until(lambda:control('status')['source_ready'])
        report['background_traffic']='explicit USER message and health service lifecycle'
        def counter(data,key):return next(line.split()[1] for line in data.splitlines() if line.startswith(key+b' '))
        for label,kind,path,arguments,uid in cases:
            offset=active.stat().st_size;inode=active.stat().st_ino
            read,release=os.pipe();child=os.fork()
            if child==0:
                try:
                    os.close(release);os.read(read,1);os.close(read)
                    if uid:
                        os.setgroups([]);os.setresgid(nobody.pw_gid,nobody.pw_gid,nobody.pw_gid)
                        os.setresuid(uid,uid,uid)
                    if kind=='execveat':
                        descriptor=os.open(path,os.O_RDONLY)
                        argv=(ctypes.c_char_p*(len(arguments)+1))(*arguments,None)
                        envp=(ctypes.c_char_p*1)(None);libc=ctypes.CDLL(None,use_errno=True)
                        libc.execveat.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.POINTER(ctypes.c_char_p),ctypes.POINTER(ctypes.c_char_p),ctypes.c_int)
                        libc.execveat(descriptor,b'',argv,envp,4096)
                        os._exit(111)
                    try:os.execve(path,arguments,{})
                    except FileNotFoundError:
                        if kind=='failed':os._exit(0)
                        raise
                except BaseException:os._exit(112)
                os._exit(113)
            os.close(read);target=child
            rule=['always,exit','-F','arch=b64','-S','execve,execveat','-F',f'pid={target}','-k','hids_m3_native_matrix']
            run('auditctl','-a',*rule);os.write(release,b'x');os.close(release);release=None
            _,status=os.waitpid(child,0);child=None;assert status==0,(label,'child failed',status)
            run('auditctl','-d',*rule);rule=None
            def source_identity():
                assert active.stat().st_ino==inode,'unexpected external rotation'
                with active.open('rb') as stream:
                    stream.seek(offset);data=stream.read(256*1024)
                found=[]
                for line in data.splitlines():
                    if line.startswith(b'type=SYSCALL ') and re.search(rb'(?:^| )pid='+str(target).encode()+rb'(?: |$)',line):
                        found.append(re.search(rb'msg=audit\(([^)]+)\)',line).group(1).decode())
                assert len(found)<=1,(label,'ambiguous source identity')
                return found[0] if found else False
            identity=until(source_identity)
            if kind=='failed':
                until(lambda:query(activation,f"SELECT reason FROM m3_rejections WHERE identity='{identity}'")==[('execve_missing_argc',)])
                assert not query(activation,f"SELECT identity FROM m3_execution WHERE identity='{identity}'")
                result={'name':label,'identity':identity,'disposition':'rejected','reason':'execve_missing_argc'}
            else:
                rows=until(lambda:query(activation,f"SELECT payload FROM m3_execution WHERE identity='{identity}'"))
                assert len(rows)==1;event=json.loads(rows[0][0])
                expected_exe=os.fsencode(os.path.realpath('/bin/sh')) if kind=='exec' and label=='script' else os.path.realpath(path)
                # Descriptor exec uses the resolved file name, unlike pathname exec.
                expected_comm=os.path.basename(os.path.realpath(path) if kind=='execveat' else path)[:15]
                assert event['pid']==target and event['ppid']==os.getpid()
                assert all(event[k]==uid for k in ('uid','euid','suid','fsuid'))
                assert event['auid']==(None if loginuid==2**32-1 else loginuid)
                assert event['session']==(None if session==2**32-1 else session)
                assert event['syscall']==(281 if kind=='execveat' else 221)
                assert event['success'] and event['result']==0
                assert event['exe_base64']==base64.b64encode(expected_exe).decode()
                assert event['comm_base64']==base64.b64encode(expected_comm).decode()
                assert not any(k in event for k in ('argc','argv','cwd','proctitle','path','arguments'))
                result={'name':label,'identity':identity,'disposition':'accepted','syscall':event['syscall'],'path_count':event['path_count']}
            assert query(activation,f"SELECT COUNT(*) FROM m3_eoe WHERE identity='{identity}'")==[(1,)]
            status=control('status');assert status['source_ready'] and status['failure'] is None
            assert status['interval']['generation']==report['generation']
            report['cases'].append(result);save();print('PASS: native '+label+' '+result['disposition'],flush=True)
        kernel_after=run('auditctl','-s').stdout
        assert counter(kernel_after,b'lost')==counter(kernel_before,b'lost')
        assert counter(kernel_after,b'pid')==counter(kernel_before,b'pid')
        report['event_health']=control('status')['event_health']
        assert len(query(activation,'SELECT identity FROM m3_execution'))==8
        control('deactivate',activation);preserved(before,inventory(active));report['result']='passed';save()
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
                except Exception:pass
        def verify():
            assert config.read_bytes()==original
            assert run('auditctl','-l').stdout.strip()==b'No rules'
            assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
        restore_all([('child',finish_child),('rule',lambda:run('auditctl','-d',*rule) if rule else None),
            ('revocation',revoke),('plugin',lambda:plugin.unlink(missing_ok=True) if created else None),
            ('configuration',lambda:config.write_bytes(original)),('reload',lambda:run('auditctl','--signal','reload')),
            ('units',lambda:run('systemctl','stop',*UNITS)),('policy',verify),
            ('source',lambda:preserved(before,inventory(active)))])
        report['restoration']='verified';save();print('Restored policy and preserved source; private report '+str(workspace/'report.json'),flush=True)


if __name__=='__main__':main()
