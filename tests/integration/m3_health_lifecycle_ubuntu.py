"""Explicit isolated VM test of metadata-endpoint failure and backend death."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from m3_runtime_ubuntu_acceptance import Reader, control, query, until


def run(*args, check=True):
    return subprocess.run(args,check=check,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)


def main():
    assert os.getuid()==0
    run('systemctl','stop','hids-m3.socket','hids-m3.service')
    parent=Path('/run/hids/m3/health')
    workspace=Path(tempfile.mkdtemp(prefix='hids-health-lifecycle.',dir='/run'))
    preserved=workspace/'health'
    os.rename(parent,preserved)
    parent.mkdir(mode=0o750)
    activation=None
    reader=None
    restored=False
    try:
        run('systemctl','start','hids-m3.socket')
        status=control('status')
        assert status['health_reporting_error']=='health_endpoint_unavailable'
        activation=str(uuid.uuid4())
        control('activate',activation)
        reader=Reader()
        until(lambda:control('status')['source_ready'])
        fixture=Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines()
        fixture[-1]+=b' '
        reader.send(b'\n'.join(fixture)+b'\n')
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        assert control('status')['failure'] is None
        print('PASS: unavailable health endpoint is visible while event collection and root control remain usable',flush=True)
        run('systemctl','kill','--kill-whom=main','--signal=KILL','hids-m3.service')
        until(lambda:run('systemctl','is-active','--quiet','hids-m3-health.timer',check=False).returncode!=0)
        until(lambda:run('systemctl','is-active','--quiet','hids-m3-health.service',check=False).returncode!=0)
        assert reader.process.wait(timeout=4)!=0
        print('PASS: backend SIGKILL automatically stops checker and timer',flush=True)
        parent.rmdir()
        os.rename(preserved,parent)
        restored=True
        status=control('status')
        assert status['interval']['state']=='interrupted'
        assert status['interval']['code']=='backend_restart'
        assert status['health_reporting_error'] is None
        assert not status['source_ready']
        assert query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)]
        print('PASS: repaired endpoint recovers without automatic source reauthorization or loss of committed events',flush=True)
    finally:
        if activation:
            try: control('deactivate',activation)
            except Exception: pass
        if reader: reader.close()
        run('systemctl','stop','hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service',check=False)
        if not restored:
            parent.rmdir()
            os.rename(preserved,parent)
        print('Restored health endpoint directory; all M3/checker units stopped',flush=True)


if __name__=='__main__': main()
