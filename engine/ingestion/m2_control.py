"""Root-only local activation client. Never reads journals or writes SQLite."""
import argparse
import os
import socket
import stat
import struct
import sys
import uuid
from pathlib import Path
from engine.ingestion.m2_contract import decode, frame
from engine.ingestion.m1_contract import keys, integer, uuid_valid
from engine.ingestion.m2_service import load_config


def main():
    parser = argparse.ArgumentParser(description='HIDS root-only M2 activation control')
    parser.add_argument('command', choices=('activate', 'deactivate', 'status'))
    parser.add_argument('--config', default='/etc/hids/m2.json')
    parser.add_argument('--activation-id')
    args = parser.parse_args()
    try:
        if sys.platform != 'linux' or os.getuid() != 0 or os.geteuid() != 0:
            raise PermissionError('root_control_required')
        settings = load_config(args.config)
        endpoint = Path('/run/hids/control.sock')
        if endpoint.resolve() != endpoint:
            raise PermissionError('control_path')
        for path in (endpoint, endpoint.parent):
            i = path.lstat()
            if i.st_uid != 0 or i.st_gid != 0:
                raise PermissionError('control_owner')
        i = endpoint.lstat()
        if not stat.S_ISSOCK(i.st_mode) or stat.S_IMODE(i.st_mode) != 0o600:
            raise PermissionError('control_mode')
        request = {'protocol_version': 2, 'command': args.command}
        if args.command != 'status':
            activation = args.activation_id or (str(uuid.uuid4()) if args.command == 'activate' else None)
            if activation is None:
                raise ValueError('deactivation_requires_activation_id')
            request.update(source_id=settings['source_id'], activation_id=activation)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(str(endpoint))
            # Socket-activated control listener is created/owned by systemd root.
            # Data IPC instead authenticates the backend-created hids-ingest socket.
            pid, uid, gid = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if pid <= 0 or uid != 0 or gid != 0:
                raise PermissionError('systemd_control_peer')
            sock.sendall(frame(request, 2048))
            response = bytearray()
            while True:
                byte = sock.recv(1)
                if not byte:
                    raise EOFError('control_outcome_unconfirmed')
                if byte == b'\n':
                    break
                if len(response) == 2048:
                    raise ValueError('control_response_limit')
                response.extend(byte)
            result = decode(bytes(response), 2048)
            if result.get('protocol_version') != 2 or type(result['protocol_version']) is not int or result.get('result') not in ('activated', 'deactivated', 'status', 'rejected', 'error'):
                raise ValueError('control_response')
            if result['result'] in ('activated','deactivated'):
                keys(result,'protocol_version result activation_id')
                if result['activation_id']!=request['activation_id']:
                    raise ValueError('control_activation_mismatch')
            elif result['result']=='status':
                keys(result,'protocol_version result source_id activation_id state revision failure durable_failure reader_connected reader_pid')
                if result['source_id']!=settings['source_id'] or (result['activation_id'] is not None and not uuid_valid(result['activation_id'])):
                    raise ValueError('control_status_identity')
                integer(result['revision'],0,2**63-1)
                if type(result['reader_connected']) is not bool or (result['reader_pid'] is not None and (type(result['reader_pid']) is not int or result['reader_pid']<=0)):
                    raise ValueError('control_status_peer')
            else:
                keys(result,'protocol_version result code')
                if result['code'] not in ('invalid_json','invalid_event','unsupported_version','frame_too_large','inactive_source','reader_busy','stale_revision','storage_outcome_unconfirmed'):
                    raise ValueError('control_result_code')
            print(frame(result, 2048).decode('ascii'), end='')
            return 0 if result['result'] in ('activated','deactivated','status') else 1
    except Exception:
        print('m2_control_failure_or_unconfirmed_outcome', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
