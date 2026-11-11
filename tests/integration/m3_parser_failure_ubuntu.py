"""Root-only installed-runtime parser failure using a test-only linked binary.

The trusted launcher retains real peer, ownership and privilege-drop checks.
Sanitized fixtures only; no Audit configuration, rules or plugins are changed.
"""
import argparse
import os
from pathlib import Path
import subprocess
import uuid
from m3_runtime_ubuntu_acceptance import Reader, control, query, until


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fault_plugin',type=Path)
    parser.add_argument('--expected-code',choices=('collector_parser_failure','collector_capacity'),default='collector_parser_failure')
    args=parser.parse_args()
    assert os.getuid()==0
    units=('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')
    subprocess.run(['systemctl','stop',*units],check=True)
    subprocess.run(['systemctl','start','hids-m3.socket'],check=True)
    reader=None;activation=None
    try:
        activation=str(uuid.uuid4());control('activate',activation)
        reader=Reader(plugin=args.fault_plugin)
        until(lambda:control('status')['source_ready'])
        lines=Path('tests/fixtures/audit/structural-exec.log').read_bytes().splitlines()
        lines[-1]+=b' '
        reader.send(lines[0].replace(b':100)',b':820001)')+b'\n')
        reader.send((b'\n'.join(lines)+b'\n').replace(b':100)',b':820002)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        reader.send((b'\n'.join(lines[1:])+b'\n').replace(b':100)',b':820001)'))
        assert reader.process.wait(timeout=8)!=0
        status=control('status')
        assert status['interval']['code']==args.expected_code
        assert status['possible_gap'] and not status['source_ready'] and status['failure'] is None
        assert query(activation,'SELECT identity FROM m3_execution')==[('1794096000.123:820002',)]
        assert query(activation,"SELECT state FROM m3_disposition WHERE identity='1794096000.123:820001'")==[('interrupted',)]
        assert query(activation,'SELECT scanned=frontier FROM m3_cursor')==[(1,)]
        print('PASS: actual native '+args.expected_code+' reports a gap, interrupts A, preserves committed B and stops its reader without false rejection',flush=True)
        reader.close();reader=None
        activation=str(uuid.uuid4());control('activate',activation)
        reader=Reader()
        until(lambda:control('status')['source_ready'])
        reader.send((b'\n'.join(lines)+b'\n').replace(b':100)',b':820003)'))
        until(lambda:query(activation,'SELECT COUNT(*) FROM m3_execution')==[(1,)])
        assert control('status')['source_ready']
        print('PASS: a new explicitly authorized production reader commits C after the injected parser failure',flush=True)
    finally:
        if activation:
            try:control('deactivate',activation)
            except Exception:pass
        if reader:reader.close()
        subprocess.run(['systemctl','stop',*units],check=True)


if __name__=='__main__':main()
