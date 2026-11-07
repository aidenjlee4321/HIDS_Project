"""Private synthetic-test access checks, not production service identity policy."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
import struct
import sys


def ordinary_user():
    if os.getuid() == 0 or os.getuid() != os.geteuid() or os.getgid() != os.getegid():
        raise PermissionError("non_root_matching_identity_required")


def private_directory(path, require_linux=False):
    ordinary_user()
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise PermissionError("absolute_no_symlink_directory_required")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("private_directory_required")
    if require_linux:
        if sys.platform != "linux":
            raise OSError("linux_peer_credentials_required")
        # Read only our own capability/mount metadata; never another process record.
        own = Path("/proc/self/status").read_text()
        capabilities = {}
        for line in own.splitlines():
            if line.startswith(("CapEff:", "CapPrm:", "CapInh:")):
                capabilities[line.split(':', 1)[0]] = int(line.split()[1], 16)
        if set(capabilities) != {"CapEff", "CapPrm", "CapInh"}:
            raise PermissionError("capability_status_unavailable")
        if any(capabilities.values()):
            raise PermissionError("special_capabilities_not_allowed")
        mounts = []
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            left, right = line.split(" - ", 1)
            mount = left.split()[4].replace("\\040", " ").replace("\\134", "\\")
            if path == Path(mount) or Path(mount) in path.parents:
                mounts.append((len(mount), right.split()[0]))
        if not mounts or max(mounts)[1] not in {"ext2", "ext3", "ext4", "xfs", "btrfs", "tmpfs", "overlay"}:
            raise PermissionError("verified_local_filesystem_required")
    return path


def private_file(path, socket_file=False, writable=False):
    info = Path(path).lstat()
    kind = stat.S_ISSOCK if socket_file else stat.S_ISREG
    mode = stat.S_IMODE(info.st_mode)
    bad_mode = mode != 0o600 if socket_file else bool(mode & ~0o600)
    if writable and (mode & 0o600) != 0o600:
        bad_mode = True
    if not kind(info.st_mode) or info.st_uid != os.getuid() or bad_mode:
        raise PermissionError("private_owned_file_required")
    if not socket_file and info.st_nlink != 1:
        raise PermissionError("linked_file_not_allowed")
    return info


def peer_matches(sock, pid):
    if sys.platform != "linux" or pid <= 0:
        return False
    actual = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    return actual == (pid, os.getuid(), os.getgid())
