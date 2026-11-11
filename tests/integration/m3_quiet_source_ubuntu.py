"""Explicit root-only quiet-source probe for an isolated Ubuntu acceptance VM.

Temporarily installs two Audit plugins and one PID-scoped execution rule. Retains
only record types/timing and HIDS/dispatcher status, never native payload values.
A restart is an explicit test option, not an application startup action.
"""

import argparse
import json
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid

from m3_runtime_ubuntu_acceptance import control, query, until

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--quiet-seconds', type=float, default=12)
parser.add_argument('--audit-start', choices=('reload', 'restart'), required=True)
parser.add_argument('--expect', choices=('accepted', 'assembly_timeout'), required=True)
args = parser.parse_args()
assert 1 <= args.quiet_seconds <= 60
assert os.getuid() == 0
assert subprocess.run(['systemctl', 'is-active', '--quiet', 'hids-m3.service']).returncode != 0
for existing in Path('/etc/audit/plugins.d').glob('*.conf'):
    assert not re.search(rb'(?mi)^\s*active\s*=\s*yes\s*$', existing.read_bytes()), 'Use an isolated VM without active plugins'
assert subprocess.check_output(['auditctl','-l']).strip() == b'No rules'
configuration = Path('/etc/audit/auditd.conf')
original = configuration.read_bytes()
raw, changed = re.subn(rb'(?m)^\s*log_format\s*=.*$', b'log_format = RAW', original)
assert changed == 1
workspace = Path(tempfile.mkdtemp(prefix='hids-m3-quiet.', dir='/run'))
workspace.chmod(0o755)
(workspace/'auditd.conf').write_bytes(original)
(workspace/'auditd.conf').chmod(0o600)
output = workspace/'out'
output.mkdir(mode=0o700)
nobody = pwd.getpwnam('nobody')
os.chown(output, nobody.pw_uid, nobody.pw_gid)
observer = workspace/'observer.py'
observer.write_text('''import json,os,re,select,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGHUP, signal.SIG_IGN)
signal.pthread_sigmask(signal.SIG_SETMASK, [])
output=Path(sys.argv[1])
output.write_text(json.dumps(dict(ready=True))+'\\n')
identity=None
first=None
buffer=bytearray()
count=0
while True:
    chunk=os.read(0,4096)
    if not chunk: break
    buffer.extend(chunk)
    if len(buffer)>65537: raise SystemExit(1)
    while (end:=buffer.find(b'\\n'))>=0:
        line=bytes(buffer[:end+1]);del buffer[:end+1]
        match=re.match(rb'type=([A-Z_]+) msg=audit\\(([^)]+)\\):',line)
        if not match: continue
        kind,key=match.groups()
        if identity is None and kind==b'SYSCALL' and b' key="hids_m3_quiet_probe"' in line:
            identity=key;first=time.monotonic()
        if key!=identity or count>=32: continue
        with output.open('a') as stream:
            stream.write(json.dumps(dict(type=kind.decode('ascii'),elapsed=round(time.monotonic()-first,6)))+'\\n')
        count+=1
''')
observer.chmod(0o644)
launcher = workspace/'observe'
launcher.write_text(f'#!/bin/sh\numask 077\nexec /usr/bin/setpriv --reuid={nobody.pw_uid} --regid={nobody.pw_gid} --clear-groups --no-new-privs /usr/bin/python3 -B {observer} {output}/records.jsonl\n')
launcher.chmod(0o755)
files = [Path('/etc/audit/plugins.d/hids-m3-quiet-runtime.conf'),Path('/etc/audit/plugins.d/hids-m3-quiet-observer.conf')]
assert all(not file.exists() and not file.is_symlink() for file in files)
activation=str(uuid.uuid4())
rule=None
child=None
release=None
report={}
try:
    subprocess.run(['systemctl','start','hids-m3.socket'],check=True)
    control('activate',activation)
    for file,path in zip(files, ['/usr/lib/hids/hids-audit-launcher',str(launcher)]):
        fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
        with os.fdopen(fd,'w') as stream:
            stream.write(f'active = yes\npath = {path}\ntype = always\nformat = string\n')
    configuration.write_bytes(raw)
    subprocess.run(['systemctl', 'restart', 'auditd'] if args.audit_start == 'restart'
                   else ['auditctl', '--signal', 'reload'], check=True)
    until(lambda: control('status')['source_ready'])
    until(lambda: (output/'records.jsonl').exists())
    read,release=os.pipe()
    child=os.fork()
    if child==0:
        os.close(release)
        os.read(read,1)
        os.close(read)
        os.execv('/usr/bin/true',['true','quiet-probe','x'*10000])
    os.close(read)
    rule=['always,exit','-F','arch=b64','-S','execve,execveat','-F',f'pid={child}','-k','hids_m3_quiet_probe']
    subprocess.run(['auditctl','-a',*rule],check=True)
    os.write(release,b'x');os.close(release);release=None
    os.waitpid(child,0);child=None
    quiet=args.quiet_seconds
    time.sleep(quiet)
    records=[json.loads(line) for line in (output/'records.jsonl').read_text().splitlines()]
    report['quiet_seconds']=quiet
    report['audit_start']=args.audit_start
    report['status_before_removal']=control('status')
    report['before_rule_removal']=records
    report['stored_before_removal']=query(activation,'SELECT COUNT(*) FROM m3_execution')[0][0]
    subprocess.run(['auditctl','-d',*rule],check=True);rule=None
    time.sleep(0.7)
    report['after_rule_removal']=[json.loads(line) for line in (output/'records.jsonl').read_text().splitlines()]
    report['stored_after_removal']=query(activation,'SELECT COUNT(*) FROM m3_execution')[0][0]
    subprocess.run(['auditctl','--signal','cont'],check=True)
    time.sleep(.2)
    state=Path('/run/audit/auditd.state').read_text()
    names=('Number of active plugins','current plugin queue depth','max plugin queue depth used','plugin queue size','plugin queue overflow detected','plugin queueing suspended')
    report['dispatcher_metrics']=[line for line in state.splitlines() if line.partition(' = ')[0] in names]
    reader_uid=pwd.getpwnam('hids-audit').pw_uid
    for directory in Path('/proc').iterdir():
        if directory.name.isdigit():
            try:
                if directory.stat().st_uid!=reader_uid: continue
                values=dict(line.split(':',1) for line in (directory/'status').read_text().splitlines())
                report['reader_sigblk']=values['SigBlk'].strip()
                report['reader_termination_blocked']=bool(int(values['SigBlk'],16)&(1<<(signal.SIGTERM-1)))
            except (FileNotFoundError,ProcessLookupError):
                pass
    print(json.dumps(report,sort_keys=True),flush=True)
    types = [row.get('type') for row in report['before_rule_removal']]
    assert 'SYSCALL' in types and 'PROCTITLE' in types
    status = report['status_before_removal']
    if args.expect == 'accepted':
        assert 'EOE' in types, 'EOE was delayed upstream until later Audit traffic'
        assert report['stored_before_removal'] == report['stored_after_removal'] == 1
        assert status['source_ready'] and status['interval']['state'] == 'streaming'
    else:
        assert 'EOE' not in types
        assert report['stored_before_removal'] == report['stored_after_removal'] == 0
        assert status['interval']['state'] == 'streaming'
        assert status['interval']['code'] is None
        assert status['possible_gap'] and status['source_ready']
        assert status['event_health']['timeouts'] == 1
        assert control('status')['event_health']['late_records'] >= 1
        assert 'EOE' in [row.get('type') for row in report['after_rule_removal']]

finally:
    if release is not None: os.close(release)
    if child is not None:
        try: os.kill(child,signal.SIGTERM)
        except ProcessLookupError: pass
        os.waitpid(child,0)
    if rule is not None: subprocess.run(['auditctl','-d',*rule],check=True)
    try: control('deactivate',activation)
    except Exception: pass
    for file in files: file.unlink(missing_ok=True)
    configuration.write_bytes(original)
    subprocess.run(['auditctl','--signal','reload'],check=True)
    assert configuration.read_bytes()==original
    assert subprocess.check_output(['auditctl','-l']).strip()==b'No rules'
    subprocess.run(['systemctl','is-active','auditd'],check=True)
    subprocess.run(['systemctl','stop','hids-m3.socket','hids-m3.service'],check=True)
    print('Protected metadata evidence '+str(output/'records.jsonl'),flush=True)
