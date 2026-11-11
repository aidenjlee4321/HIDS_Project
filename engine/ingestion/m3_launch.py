"""Trusted auditd launcher. Authorization and privilege drop precede input reads."""

import argparse
import os
from pathlib import Path
import resource
import stat
import sys

from engine.ingestion.m3_control import read_lease
from engine.ingestion.m3_service import identities, load_config


def main():
    parser = argparse.ArgumentParser(description='Launch the authorized non-root Audit reader')
    parser.add_argument('--config', default='/etc/hids/m3.json')
    parser.add_argument('--plugin', default='/usr/lib/hids/hids-audit-plugin')
    args = parser.parse_args()
    try:
        if sys.platform != 'linux' or os.getuid() != 0 or os.geteuid() != 0:
            raise PermissionError('root_launcher_required')
        plugin = Path(args.plugin)
        if not plugin.is_absolute() or plugin.resolve() != plugin:
            raise PermissionError('trusted_plugin_path')
        for directory in plugin.parents:
            info = directory.stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise PermissionError('trusted_plugin_parent')
        info = plugin.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o6022:
            raise PermissionError('trusted_plugin_binary')
        config = load_config(args.config)
        scope = read_lease(config['source_id'])
        reader, ingest, ipc = identities()
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.closerange(3, os.sysconf('SC_OPEN_MAX'))
        arguments = ['/usr/bin/setpriv', '--no-new-privs', '--bounding-set=-all',
                     '--inh-caps=-all', '--ambient-caps=-all',
                     '--reuid', str(reader.pw_uid), '--regid', str(reader.pw_gid),
                     '--groups', str(ipc), str(plugin), '/run/hids/m3/ingest/audit.sock',
                     scope['activation'], scope['generation'], scope['lease'],
                     str(reader.pw_uid), str(reader.pw_gid), str(ingest.pw_uid),
                     str(ingest.pw_gid), str(ipc), '--current-tail']
        os.execve(arguments[0], arguments, {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
    except Exception:
        print('m3_launch_denied_or_failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
