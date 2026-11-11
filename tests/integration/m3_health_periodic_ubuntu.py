"""Lab-only operator test: temporarily publish periodic derived metadata."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid
from m3_runtime_ubuntu_acceptance import Reader, control, query, until


def run(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)


def main():
    assert os.getuid() == 0
    conf=Path('/etc/audit/auditd.conf')
    original=conf.read_bytes()
    replacement,count=re.subn(rb'(?m)^\s*report_interval\s*=\s*0\s*$', b'report_interval = 1', original)
    assert count==1
    assert run('auditctl','-l').stdout.strip()==b'No rules'
    workspace=Path(tempfile.mkdtemp(prefix='hids-health-periodic.',dir='/run'))
    (workspace/'auditd.conf').write_bytes(original)
    (workspace/'auditd.conf').chmod(0o600)
    state=Path('/run/audit/auditd.state')
    had_state=state.exists()
    if had_state: os.rename(state,workspace/'original.state')
    activation=None
    reader=None
    try:
        conf.write_bytes(replacement)
        run('auditctl','--signal','reload')
        run('systemctl','start','hids-m3.socket')
        activation=str(uuid.uuid4())
        control('activate',activation)
        reader=Reader()
        until(lambda: control('status')['source_ready'])
        fixture=Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines()
        fixture[-1]+=b' '
        fixture=b'\n'.join(fixture)+b'\n'
        samples=[]
        end=time.monotonic()+35
        while len(samples)<3 and time.monotonic()<end:
            status=control('status')
            health=status['upstream_health']
            if (status['upstream_loss']['kernel']=='sampled' and status['upstream_loss']['dispatcher']=='inactive'
                    and health and (not samples or health['received_at']!=samples[-1]['received_at'])):
                sample=dict(received_at=health['received_at'], report_mtime_ns=health['observation']['dispatcher']['report_mtime_ns'],
                            report_age_ns=health['observation']['dispatcher']['age_ns'], lost=health['observation']['kernel']['lost'])
                if samples: assert sample['report_mtime_ns']>samples[-1]['report_mtime_ns']
                samples.append(sample)
                reader.send(fixture.replace(b':100)', f':{800000+len(samples)})'.encode()))
                until(lambda: query(activation,'SELECT COUNT(*) FROM m3_execution')==[(len(samples),)])
            time.sleep(.2)
        assert len(samples)==3
        assert reader.process.poll() is None and control('status')['source_ready']
        assert conf.read_bytes()==replacement
        assert run('auditctl','-l').stdout.strip()==b'No rules'
        print('PASS: three consecutive passive timer observations of real kernel and periodic dispatcher metadata; independent event ingestion continues',flush=True)
        print(json.dumps(samples,sort_keys=True),flush=True)
    finally:
        if activation:
            try: control('deactivate',activation)
            except Exception: pass
        if reader: reader.close()
        run('systemctl','stop','hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')
        conf.write_bytes(original)
        run('auditctl','--signal','reload')
        time.sleep(.3)
        if state.exists(): state.unlink()
        if had_state: os.rename(workspace/'original.state',state)
        assert conf.read_bytes()==original
        assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
        print('Restored original operator logging setting and derived report; retained private evidence '+str(workspace),flush=True)


if __name__=='__main__': main()
