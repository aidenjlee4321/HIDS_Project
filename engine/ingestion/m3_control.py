"""Root-only local M3 activation control. Never reads native Audit input."""

import argparse
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import uuid

from engine.ingestion.m1_contract import keys, uuid_valid
from engine.ingestion.m2_contract import decode, frame
from engine.ingestion.m3_service import load_config
from engine.ingestion import m3_health, m3_storage, m3_event

ENDPOINT = Path('/run/hids/m3/control.sock')


def request(command):
    if sys.platform != 'linux' or os.getuid() != 0 or os.geteuid() != 0:
        raise PermissionError('root_control_required')
    if ENDPOINT.resolve() != ENDPOINT:
        raise PermissionError('control_path')
    for path in (ENDPOINT, ENDPOINT.parent, ENDPOINT.parent.parent):
        info = path.lstat()
        if info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022:
            raise PermissionError('control_owner')
    info = ENDPOINT.lstat()
    if not stat.S_ISSOCK(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError('control_mode')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(str(ENDPOINT))
        pid, uid, gid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if pid <= 0 or uid != 0 or gid != 0:
            raise PermissionError('root_listener_required')
        connection.sendall(frame(command, 2048))
        raw = bytearray()
        while len(raw) <= 4096:
            byte = connection.recv(1)
            if not byte:
                raise EOFError('control_outcome_unconfirmed')
            if byte == b'\n':
                result = decode(bytes(raw), 4096)
                if type(result.get('version')) is not int or result['version'] != 3:
                    raise ValueError('control_version')
                return result
            raw.extend(byte)
        raise ValueError('control_response_limit')


def read_lease(source):
    response = request({'version': 3, 'command': 'lease'})
    keys(response, 'version result source scope')
    if response['result'] != 'lease' or response['source'] != source:
        raise ValueError('inactive_source')
    scope = response['scope']
    keys(scope, 'activation generation lease')
    if not all(uuid_valid(value) for value in scope.values()):
        raise ValueError('invalid_lease')
    return scope


def main():
    parser = argparse.ArgumentParser(description='HIDS root-only M3 activation control')
    parser.add_argument('command', choices=('status', 'activate', 'deactivate', 'diagnostics'))
    parser.add_argument('--config', default='/etc/hids/m3.json')
    parser.add_argument('--activation-id',help='For activate/deactivate only')
    args = parser.parse_args()
    try:
        if os.getuid() != 0 or os.geteuid() != 0:
            raise PermissionError('root_control_required')
        if args.command in ('status','diagnostics') and args.activation_id is not None:
            raise ValueError('activation filter not supported for this command')
        config = load_config(args.config)
        command = {'version': 3, 'command': args.command}
        if args.command not in ('status','diagnostics'):
            activation = args.activation_id
            if activation is None and args.command == 'activate':
                activation = str(uuid.uuid4())
            if not uuid_valid(activation):
                raise ValueError('activation_identity_required')
            command.update(source=config['source_id'], activation=activation)
        result = request(command)
        if result.get('result') in ('activated', 'deactivated'):
            keys(result, 'version result activation')
            if result['result'] != args.command + 'd' or result['activation'] != command['activation']:
                raise ValueError('control_activation_mismatch')
        elif result.get('result') == 'diagnostics':
            keys(result, 'version result source activation available items truncated')
            if result['source']!=config['source_id'] or result['activation'] is not None and not uuid_valid(result['activation']):
                raise ValueError('diagnostic scope')
            m3_event.validate_diagnostics({key:result[key] for key in ('available','items','truncated')})
        elif result.get('result') == 'status':
            keys(result, 'version result source interval source_ready possible_gap failure reader_connected upstream_loss upstream_health event_health health_reporting_error storage')
            if result['health_reporting_error'] not in (None, 'health_storage_failure', 'health_endpoint_unavailable'):
                raise ValueError('control_health_error')
            m3_storage.validate_status(result['storage'])
            keys(result['upstream_loss'], 'kernel dispatcher')
            if (result['upstream_loss']['kernel'] not in ('unknown', 'sampled') or
                    result['upstream_loss']['dispatcher'] not in ('unknown', 'sampled', 'inactive')):
                raise ValueError('control_upstream_evidence')
            m3_health.validate_status(result['upstream_health'])
            if result['upstream_health'] is not None and any(result['upstream_loss'][key] != result['upstream_health'][key]
                                                           for key in ('kernel', 'dispatcher')):
                raise ValueError('control_health_availability_mismatch')
            if result['event_health'] is not None:
                keys(result['event_health'], 'timeouts late_records resource_incidents discarding rejected_groups rejection_details observed_executions')
                if any((value is None and key not in ('resource_incidents', 'discarding', 'rejection_details', 'observed_executions')) or
                       (value is not None and (type(value) is not int or value < 0))
                       for key, value in result['event_health'].items()):
                    raise ValueError('control_event_evidence')
            if args.command != 'status' or result['source'] != config['source_id']:
                raise ValueError('control_status_scope')
        elif result.get('result') == 'rejected':
            keys(result, 'version result code')
        else:
            raise ValueError('control_response')
        print(frame(result, 4096).decode('ascii'), end='')
        return 1 if result['result'] == 'rejected' else 0
    except Exception:
        print('m3_control_failure_or_unconfirmed_outcome', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
