# M2 temporary runtime acceptance — definitive console runbook

Historical preparation/component record: the pending/unauthorized statements
below describe that checkpoint. Later [owner-reported Ubuntu runtime acceptance](ubuntu-runtime-acceptance.md)
supersedes its pending-execution status within that report's explicit limits.
Preserve the original evidence; later live negative-control authorization remains
unverified rather than being inferred from the runbook.

**Prepared from repository inspection; not executed on Ubuntu.** This is a new
runbook, not a recovered earlier artifact. Owner reports offline acceptance of
`hids-src-20261108T012355Z-e520e3a020ed`: three phases, zero skips. Live acceptance
remains unperformed. Existing specification/validation files retain their historical
wording; the owner's subsequent temporary-runtime authorization governs this run.

Run the numbered stages in order in **one ordinary-user Bash session on Ubuntu**.
Root commands are explicitly `sudo`, including the `admin`, `root_probe`, `ctl`,
`as_ingest` and `as_reader` functions. Only systemd runs the actual components;
reader and ingestion are never root. No installation, enablement, journal/PAM/Audit
configuration, package operation or Git command is included. Do not run this on
macOS. Do not modify the source snapshot or save security records to the share.

## Approval gate and limits

The owner has approved both limits below for the **current runtime acceptance
only**. They are not permanent production defaults or a finalized retention policy.
The persistent lowercase source UUIDv4 must be supplied privately in protected
runtime configuration and private evidence; never record it in tracked documents.
There are **no executable defaults** below and no source UUID is created. See the
[configuration specification](../../implementation/m2-journald-spec.md#8-runtime-acceptance-configuration).

- `max_records=100`: total stored **dispositions** (events AND native rejection
  records), cumulative across activations in this DB. Duplicate lookup precedes
  this limit. It does not bound gaps/activations, journal reads, duration or bytes.
- `max_pages=4096`: SQLite writer `max_page_count`, all main-DB tables/indexes.
  At an observed 4096-byte page size this is 16 MiB. It is not a filesystem quota;
  WAL, SHM, diagnostics and exports are additional. Read-only connections do not
  establish the writer's configured cap. The writer applies/verifies it at startup.

`Store.put()` raises a storage error at disposition capacity; page exhaustion can
fail any write. Startup failures precede readiness; per-event failures remain
unconfirmed and stop source acceptance. Already committed data is not evicted.
There is no durable producer outbox: later journal retention/rotation can prevent
recovery. Do not increase limits or clear state to hide a failure. Record actual
page size/count and filesystem free space; these acceptance limits are not production
retention policy, performance guarantees or permission for unattended operation.

The helper bounds retrieval to min(approved max_records, 1000) dispositions,
100 activations, one source checkpoint, 1000 gap records and 32 MiB evidence/state
frames. Exceeding a helper bound fails acceptance; it does not truncate data.

## 0. Mandatory standalone Linux archival gate (offline only)

The separately supplied [validate_archival_linux.py](validate_archival_linux.py)
is self-contained: it embeds the exact resources/probe/test bytes with individual
SHA-256 checks. Keep it outside the immutable source snapshot. Supplying this one
reviewed file is a manual preparation step; no additional snapshot is needed.
First run these commands in the ordinary Ubuntu console, before Stage 1. The
explicit root invocation only creates/chowns disposable fixtures in newly created
private temporary directories; it does not touch HIDS paths, units or journals.
No account is created. Existing `hids-journal` (UID 997) and `hids-ingest` must
already exist. The root test verifies real mixed ownership across a real device
boundary. Neither invocation installs anything or starts services.

```bash
set -euo pipefail
test "$(id -u)" != 0
read -r -p 'Absolute path to the reviewed standalone archival gate: ' ARCHIVAL_GATE
test "${ARCHIVAL_GATE#/}" != "$ARCHIVAL_GATE"
test -f "$ARCHIVAL_GATE" && test ! -L "$ARCHIVAL_GATE"
printf '%s  %s\n' '3c5ae72a36ad3d4fd73e0354c15f9ba5af7fe837fb2cb7a4651252f0eb3f6f8b' "$ARCHIVAL_GATE" | sha256sum -c -
python3 -I -B "$ARCHIVAL_GATE"
sudo /usr/bin/python3 -I -B "$ARCHIVAL_GATE" --ownership
```

**Expected:** ordinary-user suite: 39 tests, zero skips/errors/failures; explicit
root suite: one cross-account preservation test, zero skips/errors/failures.
Writable `/dev/shm` on a different device and Linux native no-replace rename are
mandatory; absent prerequisites fail closed. Extended metadata is rejected, not
silently stripped. Output includes embedded artifact digests and test counts.
**Stop:** any failure or skip. Do not change permissions, mount filesystems,
create accounts or install packages to bypass this gate. Native checks have not
been executed by the macOS author; their results must be recorded independently.

## 1. Read-only preflight and failure handler

Start a fresh Bash session. Expected failures later are explicitly handled. Any
other failing command stops the session. The failure handler attempts revocation
and stops only inventoried, unchanged units; it never deletes evidence or repairs
permissions. Closing this shell also triggers that handler until final cleanup.

First execute `bash` **by itself** and wait for its prompt. Then paste this block:

```bash
set -Eeuo pipefail
set -C
umask 077
SNAP=/mnt/ccdc-transfer/collector-validation/snapshots/hids-src-20261108T012355Z-e520e3a020ed
PIN=9c2d2df75cfd7989b5427ed578c96b1fe45ed90a18f70e6245e7d7f692234aea
PREPARED=0
ACTIVATION_ID=
BASE=
EVIDENCE=
BUILD=
failstop() {
    code=${1:-1}
    trap - ERR EXIT INT TERM HUP
    set +e
    if [[ $PREPARED == 1 ]]; then
        if [[ -n $ACTIVATION_ID ]]; then
            ctl deactivate --activation-id "$ACTIVATION_ID"
        fi
        admin stop
    fi
    printf 'STOP: acceptance incomplete (exit %s). Preserve %s and %s.\n' \
        "$code" "${EVIDENCE:-not-created}" "${BASE:-not-created}" >&2
    [[ $code != 0 ]] || code=1
    exit "$code"
}
trap 'failstop "$?"' ERR EXIT
trap 'failstop 130' INT
trap 'failstop 143' TERM
trap 'failstop 129' HUP

test "$(id -u)" != 0
cd "$SNAP"
uname -rm
g++ --version
systemctl --version
pkg-config --modversion libsystemd
command -v g++ python3 systemctl systemd-run systemd-analyze pkg-config ssh ss
python3 -B - <<'PY'
import ctypes.util,hashlib,json,os,platform,sqlite3,stat,sys
from pathlib import Path,PurePosixPath
assert os.getuid()==os.geteuid()!=0 and os.getgid()==os.getegid()!=0
assert platform.machine()=='aarch64'
release={k:v.strip('"') for line in Path('/etc/os-release').read_text().splitlines()
         if '=' in line for k,v in [line.split('=',1)]}
assert release['ID']=='ubuntu' and release['VERSION_ID']=='26.04'
assert platform.release()=='7.0.0-42-generic'
assert sys.version_info>=(3,10) and sqlite3.sqlite_version_info>=(3,22,0)
assert ctypes.util.find_library('systemd') and Path('/usr/include/systemd/sd-journal.h').is_file()
root=Path.cwd()
assert root.name=='hids-src-20261108T012355Z-e520e3a020ed' and root.resolve()==root
pin='9c2d2df75cfd7989b5427ed578c96b1fe45ed90a18f70e6245e7d7f692234aea'
raw=(root/'SOURCE_MANIFEST.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()==pin
assert (root/'SOURCE_MANIFEST.sha256').read_text()==pin+'\n'
m=json.loads(raw)
expected=set(m['files'])|{'SOURCE_MANIFEST.json','SOURCE_MANIFEST.sha256'}
actual=set(); dirs=set(); expected_dirs=set()
for name,wanted in m['files'].items():
    rel=PurePosixPath(name)
    assert not rel.is_absolute() and '..' not in rel.parts and str(rel)==name
    expected_dirs.update(str(p) for p in rel.parents if str(p)!='.')
    p=root/name; s=p.lstat()
    assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=32*1024*1024
    assert hashlib.sha256(p.read_bytes()).hexdigest()==wanted
for parent,names,files in os.walk(root,followlinks=False):
    for name in names:
        p=Path(parent)/name
        assert not p.is_symlink() and p.is_dir()
        dirs.add(p.relative_to(root).as_posix())
    for name in files:
        p=Path(parent)/name
        assert not p.is_symlink()
        actual.add(p.relative_to(root).as_posix())
assert actual==expected and dirs==expected_dirs
for name in ('/usr/sbin/sshd','/usr/lib/openssh/sshd-session'):
    p=Path(name); s=p.lstat()
    assert p.resolve()==p and stat.S_ISREG(s.st_mode) and s.st_uid==0
    assert not s.st_mode & 0o022 and os.access(p,os.X_OK)
print('PASS: platform, dependencies, complete source inventory/hashes and SSH executable identities')
print(release.get('PRETTY_NAME'),sys.version.split()[0],sqlite3.sqlite_version)
PY
sudo -v
df -h /run /var/lib /tmp
```

**Expected:** all checks pass; no source file changed. **Stop:** any mismatch,
missing tool, insufficient space, or platform update needing review. Install nothing.

## 2. Identity and existing-resource gates

This runbook requires the approved accounts/groups to exist. Missing or conflicting
identities are a precondition failure: report them rather than provisioning or
repairing them inside this acceptance sequence. No GID is inferred from a UID.

```bash
python3 -B - <<'PY'
import grp,os,pwd,subprocess
from pathlib import Path
r=pwd.getpwnam('hids-journal'); i=pwd.getpwnam('hids-ingest')
ipc=grp.getgrnam('hids-ipc').gr_gid; journal=grp.getgrnam('systemd-journal').gr_gid
assert r.pw_uid==997 and i.pw_uid not in (0,997)
assert r.pw_gid==grp.getgrnam('hids-journal').gr_gid!=0
assert i.pw_gid==grp.getgrnam('hids-ingest').gr_gid!=0
assert len({r.pw_gid,i.pw_gid,ipc,journal})==4
assert os.getuid() not in (r.pw_uid,i.pw_uid)
for a in (r,i):
    groups=set(os.getgrouplist(a.pw_name,a.pw_gid))
    assert journal not in groups and groups<={a.pw_gid,ipc}
    assert a.pw_shell in ('/usr/sbin/nologin','/sbin/nologin','/bin/false')
    print(a.pw_name,'UID',a.pw_uid,'primary GID',a.pw_gid,'permanent groups',sorted(groups))
assert ipc not in os.getgroups(), 'console user must not have HIDS IPC membership'
for unit in ('hids-ingest.socket','hids-ingest.service','hids-journal.service'):
    p=subprocess.run(['systemctl','show',unit,'-p','LoadState','--value'],capture_output=True,text=True)
    assert p.stdout.strip()=='not-found', (unit,p.stdout,p.stderr)
    for folder in ('/run/systemd/system','/etc/systemd/system','/usr/lib/systemd/system','/lib/systemd/system'):
        for name in (unit,unit+'.d'):
            assert not os.path.lexists(Path(folder)/name), str(Path(folder)/name)
for name in ('/run/hids','/var/lib/hids'):
    assert not os.path.lexists(name), 'existing resource: '+name
print('PASS: service identities, membership policy, no conflicting HIDS resources')
PY
verify_ssh_listener() {
    systemctl is-active --quiet ssh.service
    sudo python3 -I -B - <<'PY'
from pathlib import Path
import re,subprocess
output=subprocess.run(['ss','-H','-4','-ltnp','sport = :22'],capture_output=True,text=True,check=True).stdout
matched=[]
for line in output.splitlines():
    fields=line.split()
    if len(fields)<5 or fields[3] not in ('127.0.0.1:22','0.0.0.0:22','*:22'):
        continue
    for pid in re.findall(r'"sshd",pid=([0-9]+),fd=',line):
        if Path('/proc/'+pid+'/exe').resolve(strict=True)==Path('/usr/sbin/sshd'):
            matched.append(int(pid))
assert matched, 'no existing IPv4 loopback/wildcard sshd listener on port 22'
print('PASS: existing sshd listener PIDs',sorted(set(matched)))
PY
}
verify_ssh_listener
```

**Expected:** reader UID 997, separate primary GIDs; no permanent journal membership;
all HIDS resources absent. The listener gate requires a running SSH service and verifies an existing IPv4
loopback/wildcard port-22 listener belongs to a process executing /usr/sbin/sshd.
A socket-only inactive server,
other port, absent listener or unrelated listener is a stop condition. Do not
start/reconfigure SSH. If no suitable listener exists, report live-event acceptance
blocked; do not provision one.

## 3. Journal permission assessment — no journal open

The following reads only machine-ID/path metadata and assesses DAC/ACL access.
It does not invoke journalctl, libsystemd or inspect any journal payload. It also
verifies the actual credentials of these transient permission-probe processes.

```bash
JFILES=$(sudo python3 -I -B - <<'PY'
import json
from pathlib import Path
machine=Path('/etc/machine-id').read_text().strip()
files=[]
for parent in (Path('/var/log/journal')/machine,Path('/run/log/journal')/machine):
    if parent.is_dir():
        files.extend(str(p) for p in parent.glob('*.journal') if p.is_file() and not p.is_symlink())
assert 0<len(files)<=1000
print(json.dumps(sorted(set(files))))
PY
)
for role in hids-journal hids-ingest; do
    if [[ $role == hids-journal ]]; then extra='systemd-journal hids-ipc'; else extra=hids-ipc; fi
    sudo systemd-run --quiet --wait --pipe --collect --expand-environment=no \
        -p "User=$role" -p "Group=$role" -p "SupplementaryGroups=$extra" \
        -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' -p 'AmbientCapabilities=' \
        /usr/bin/python3 -I -B -c '
import grp,json,os,pwd,sys
role=sys.argv[1]; paths=json.loads(sys.argv[2]); who=pwd.getpwnam(role)
expected={who.pw_gid,grp.getgrnam("hids-ipc").gr_gid}
if role=="hids-journal": expected.add(grp.getgrnam("systemd-journal").gr_gid)
assert os.getresuid()==(who.pw_uid,)*3 and os.getresgid()==(who.pw_gid,)*3
assert set(os.getgroups())|{who.pw_gid}==expected
access=[os.access(p,os.R_OK) for p in paths]
assert any(access) if role=="hids-journal" else not any(access)
print(role,"permission assessment passed; journal not opened")
' "$role" "$JFILES"
done
```

**Expected:** both pass; reader can access at least one assessed file, ingestion
none. This does not prove namespace completeness or functioning collection.
**Stop:** any access/group mismatch or absent journal metadata. Change no permissions.

## 4. Owner values, ordinary-user build and complete helper sources

The storage values are owner-approved: enter exactly 100 and 4096 for this run.
Supply the source UUID privately before continuing. The prompts neither generate
a source identity nor establish production defaults.
The random TAG names temporary resources and is **not** the persistent source ID.

```bash
read -r -p 'Approved persistent lowercase source UUIDv4: ' SOURCE_ID
read -r -p 'Owner-approved acceptance max_records (enter 100): ' MAX_RECORDS
read -r -p 'Owner-approved acceptance max_pages (enter 4096): ' MAX_PAGES
test "$MAX_RECORDS" = 100
test "$MAX_PAGES" = 4096
read -r -p 'Type APPROVED to confirm the privately supplied source UUID and approved acceptance limits: ' APPROVAL
test "$APPROVAL" = APPROVED
TAG=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
BUILD=$(mktemp -d /tmp/hids-m2-acceptance.XXXXXXXX)
BASE=/run/hids-m2-acceptance-$TAG
EVIDENCE=/var/lib/hids-m2-acceptance-$TAG
python3 -I -B - "$SOURCE_ID" "$MAX_RECORDS" "$MAX_PAGES" "$BUILD/m2.json" <<'PY'
import json,sys,uuid
source,records,pages,target=sys.argv[1:]
u=uuid.UUID(source)
assert u.version==4 and str(u)==source
assert records==str(int(records)) and 1<=int(records)<=2**63-1
assert pages==str(int(pages)) and 16<=int(pages)<=2147483646
with open(target,'x') as f:
    json.dump(dict(source_id=source,max_records=int(records),max_pages=int(pages)),f)
    f.write('\n')
PY
g++ -std=c++20 -Wall -Wextra -Wpedantic -Werror \
    -I "$SNAP/collector/include" -I "$SNAP/collector/third_party" \
    "$SNAP/collector/src/pilot/contract.cpp" \
    "$SNAP/collector/src/pilot/transport.cpp" \
    "$SNAP/collector/src/journal/contract.cpp" \
    "$SNAP/collector/src/journal/transport.cpp" \
    "$SNAP/collector/src/journal_collector.cpp" \
    "$SNAP/collector/src/journal/runtime.cpp" \
    "$SNAP/collector/src/journal/linux_journal_io.cpp" \
    "$SNAP/collector/src/journal/reader_main.cpp" \
    -lsystemd -o "$BUILD/m2-reader"
"$BUILD/m2-reader" --help
```

Paste both following blocks in full. They create new private helper files, not
production changes. The resource helper rejects existing resources, records their
identities/hashes, preserves evidence, and never opens the journal or writes SQL.
The probe uses the existing production validators, peer policy, SQLite read-only
connection profile and `get_event()`. Its proxy forwards one TCP stream without
recording contents; the port/boot/monotonic metadata establishes event provenance.

```bash
cat > "$BUILD/resources.py" <<'PY'
"""Temporary acceptance resource inventory. Root only; no journal API or SQL writes.

Invoked manually by the runbook. Never installed or enabled permanently.
"""
import hashlib
import ctypes
import errno
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import stat
import subprocess
import sys
import uuid
import tempfile

UNITS = ('hids-ingest.socket', 'hids-ingest.service', 'hids-journal.service')
PIN = '9c2d2df75cfd7989b5427ed578c96b1fe45ed90a18f70e6245e7d7f692234aea'
LIMIT = 32 * 1024 * 1024


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def read(path, maximum=LIMIT):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'unsafe input file')
        data = f.read(maximum + 1)
    require(len(data) <= maximum, 'input too large')
    return data


def protected(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, 'unsafe path')
    for p in (path, *path.parents):
        s = p.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
                'unprotected directory: ' + str(p))


def digest(path):
    return hashlib.sha256(read(path)).hexdigest()


def _metadata(s):
    require(stat.S_ISDIR(s.st_mode) or (stat.S_ISREG(s.st_mode) and s.st_nlink == 1),
            'archive rejects links/special files')
    require(not stat.S_IMODE(s.st_mode) & ~0o777, 'archive rejects special permission bits')
    return dict(dev=s.st_dev, ino=s.st_ino, uid=s.st_uid, gid=s.st_gid,
                mode=stat.S_IMODE(s.st_mode), directory=stat.S_ISDIR(s.st_mode),
                size=s.st_size, mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def _directory_fd(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, 'archive path contains a symlink')
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _plain_metadata(fd):
    # These resources are created with plain POSIX ownership/modes. Refuse Linux
    # ACLs, capabilities or other xattrs rather than silently dropping metadata.
    # Darwin is supported solely for ordinary-user offline filesystem regressions.
    if sys.platform.startswith('linux'):
        require(hasattr(os, 'listxattr'), 'extended-metadata inspection unavailable')
        try: names = os.listxattr(fd)
        except OSError as exc:
            if exc.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP): raise
            names = []  # Filesystem explicitly does not support xattrs.
        require(not names, 'extended metadata requires operator review; source retained')


def _hash_fd(fd, metadata):
    require(_metadata(os.fstat(fd)) == metadata and not metadata['directory'], 'archive input changed')
    digest = hashlib.sha256(); size = 0
    while True:
        block = os.read(fd, 1024*1024)
        if not block: break
        size += len(block)
        require(size <= metadata['size'], 'archive input grew')
        digest.update(block)
    require(size == metadata['size'] and _metadata(os.fstat(fd)) == metadata, 'archive input changed')
    return digest.hexdigest()


def tree_manifest(root):
    """Frozen source identities and streamed hashes; every traversal is no-follow."""
    result = {}
    root_fd = _directory_fd(root)
    device = os.fstat(root_fd).st_dev
    def visit(fd, relative):
        require(len(result) < 20000, 'archive inventory bound')
        _plain_metadata(fd)
        before = _metadata(os.fstat(fd)); result[relative] = before
        require(before['dev'] == device, 'nested mount in archive source')
        for name in sorted(os.listdir(fd)):
            rel = name if relative == '.' else relative+'/'+name
            require(len(result) < 20000, 'archive inventory bound')
            info = _metadata(os.stat(name, dir_fd=fd, follow_symlinks=False))
            require(info['dev'] == device, 'nested mount in archive source')
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if info['directory']: flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=fd)
            try:
                require(_metadata(os.fstat(child)) == info, 'archive entry replaced')
                if info['directory']: visit(child, rel)
                else:
                    _plain_metadata(child)
                    info['sha256'] = _hash_fd(child, info)
                    result[rel] = info
            finally: os.close(child)
        require(_metadata(os.fstat(fd)) == before, 'archive directory changed')
    try: visit(root_fd, '.')
    finally: os.close(root_fd)
    return result


def _equivalent(actual, expected):
    if set(actual) != set(expected): return False
    for name, wanted in expected.items():
        keys = ('directory', 'uid', 'gid', 'mode', 'mtime_ns')
        if not wanted['directory']: keys += ('size', 'sha256')
        if any(actual[name][key] != wanted[key] for key in keys): return False
    return True


def _copy_tree(source, stage, manifest):
    source_fd = _directory_fd(source)
    try: output_fd = _directory_fd(stage)
    except BaseException:
        os.close(source_fd); raise
    def copy_dir(src, dst, relative):
        wanted = manifest[relative]
        require(_metadata(os.fstat(src)) == wanted, 'source directory changed before copy')
        for name in sorted(os.listdir(src)):
            rel = name if relative == '.' else relative+'/'+name
            require(rel in manifest, 'unplanned source entry')
            item = manifest[rel]
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if item['directory']: flags |= os.O_DIRECTORY
            original = os.open(name, flags, dir_fd=src)
            copied = None
            try:
                expected = {k: v for k, v in item.items() if k != 'sha256'}
                require(_metadata(os.fstat(original)) == expected, 'copy input replaced')
                if item['directory']:
                    os.mkdir(name, mode=0o700, dir_fd=dst)
                    copied = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dst)
                    copy_dir(original, copied, rel)
                else:
                    copied = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     0o600, dir_fd=dst)
                    size = 0; hashed = hashlib.sha256()
                    while True:
                        block = os.read(original, 1024*1024)
                        if not block: break
                        size += len(block); require(size <= item['size'], 'copy input grew')
                        hashed.update(block)
                        view = memoryview(block)
                        while view:
                            n = os.write(copied, view); require(n > 0, 'archive short write')
                            view = view[n:]
                    require(size == item['size'] and hashed.hexdigest() == item['sha256'] and
                            _metadata(os.fstat(original)) == expected, 'copy input changed')
                    _copy_metadata(copied, item)
            finally:
                os.close(original)
                if copied is not None: os.close(copied)
        _copy_metadata(dst, wanted)
    try: copy_dir(source_fd, output_fd, '.')
    finally: os.close(source_fd); os.close(output_fd)


def _copy_metadata(fd, item):
    # Metadata is applied only to freshly created archive objects, never sources.
    s = os.fstat(fd)
    if (s.st_uid, s.st_gid) != (item['uid'], item['gid']):
        os.fchown(fd, item['uid'], item['gid'])
    os.fchmod(fd, item['mode'])
    os.utime(fd, ns=(s.st_atime_ns, item['mtime_ns']))
    os.fsync(fd)


def _finalize_archive(stage, target):
    """Atomic same-parent, no-replace rename. Never rename a source tree."""
    require(stage.parent == target.parent, 'archive finalization must stay on destination filesystem')
    parent = _directory_fd(target.parent)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform.startswith('linux'):
            function = getattr(libc, 'renameat2', None); flags = 1  # RENAME_NOREPLACE
        elif sys.platform == 'darwin':
            function = getattr(libc, 'renameatx_np', None); flags = 4  # RENAME_EXCL
        else: function = None
        if function is None: raise OSError(errno.ENOTSUP, 'exclusive archive rename unavailable')
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        if function(parent, os.fsencode(stage.name), parent, os.fsencode(target.name), flags):
            code = ctypes.get_errno(); raise OSError(code, os.strerror(code), str(target))
        os.fsync(parent)
    finally: os.close(parent)


def archive_tree(source, target, manifest):
    """Copy/verify/finalize on the destination FS; preserve the source on all failures."""
    source, target = Path(source), Path(target)
    require(source != target and source not in target.parents and target not in source.parents,
            'archive source/destination overlap')
    parent = _directory_fd(target.parent)
    try:
        s = os.fstat(parent)
        require(s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o700, 'private archive parent required')
    finally: os.close(parent)
    require(not os.path.lexists(target), 'archive already exists: '+str(target))
    require(tree_manifest(source) == manifest, 'source changed before archival')
    stage = Path(tempfile.mkdtemp(prefix='.'+target.name+'.staging-', dir=target.parent))
    # On failure leave the clearly named private stage for operator inspection.
    _copy_tree(source, stage, manifest)
    require(tree_manifest(source) == manifest, 'source changed during archival')
    require(_equivalent(tree_manifest(stage), manifest), 'archive copy verification failed')
    _finalize_archive(stage, target)
    actual = tree_manifest(target)
    require(_equivalent(actual, manifest), 'final archive verification failed')
    return dict(source=str(source), destination=str(target), manifest=manifest,
                destination_identity=[actual['.']['dev'], actual['.']['ino']])


def verify_archive(receipt):
    manifest = tree_manifest(Path(receipt['destination']))
    require([manifest['.']['dev'], manifest['.']['ino']] == receipt['destination_identity'] and
            _equivalent(manifest, receipt['manifest']), 'final archive changed')


def _inventory_tree(inv, root, manifest):
    """The runtime tree must contain exactly this run's inventoried objects."""
    entries = {str(Path(e['path']).relative_to(root)): e for e in inv.data['entries']
               if Path(e['path']) == root or root in Path(e['path']).parents}
    require(set(entries) == set(manifest), 'runtime tree differs from created-resource inventory')
    for name, original in entries.items():
        item = manifest[name]
        require(all(item[k] == original[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode', 'directory')),
                'runtime object differs from inventory')
        if original.get('sha256') is not None:
            require(item['sha256'] == original['sha256'], 'runtime content differs from inventory')


def prepare_archives(inv, db, ingest):
    """Both sources survive until BOTH finalized archives have passed verification."""
    inv.check()
    runtime = tree_manifest(inv.base); _inventory_tree(inv, inv.base, runtime)
    database = tree_manifest(db)
    root_entries = [e for e in inv.data['entries'] if e['path'] == str(db)]
    require(len(root_entries) == 1, 'database root was not created by this run')
    original = root_entries[0]
    require(all(database['.'][k] == original[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode', 'directory')),
            'database root replaced')
    for name, item in database.items():
        if name == '.': continue
        require(not item['directory'] and item['uid'] == ingest.pw_uid and
                item['gid'] == ingest.pw_gid and not item['mode'] & ~0o600,
                'unexpected database evidence object')
    targets = [inv.evidence/'database', inv.evidence/'runtime']
    require(all(not os.path.lexists(p) for p in targets), 'archive target exists; no merge/retry')
    receipts = [archive_tree(db, targets[0], database), archive_tree(inv.base, targets[1], runtime)]
    for receipt in receipts:
        verify_archive(receipt)
        require(tree_manifest(Path(receipt['source'])) == receipt['manifest'], 'source changed before cleanup')
    inv.data['archive_receipts'] = receipts
    inv.data['cleanup_phase'] = 'archives_verified'
    inv.write()  # Persist source identities/hashes and verified destinations before removal.
    return receipts


def remove_archived_sources(receipts):
    """Complete ALL archive/source verification before the first unlink."""
    for receipt in receipts:
        verify_archive(receipt)
        require(tree_manifest(Path(receipt['source'])) == receipt['manifest'], 'source changed before removal')
        require(not os.path.ismount(receipt['source']), 'refuse source mount-point removal')
    for receipt in receipts:
        _remove_frozen_source(receipt)


def _remove_frozen_source(receipt):
    """Delete only frozen, individually checked entries; never use rmtree."""
    source = Path(receipt['source']); manifest = receipt['manifest']
    root = _directory_fd(source)
    try:
        for name in sorted((n for n in manifest if n != '.'), key=lambda n: (n.count('/'), n), reverse=True):
            parts = PurePosixPath(name).parts; parent = os.dup(root)
            try:
                prefix = []
                for part in parts[:-1]:
                    prefix.append(part)
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
                    expected = manifest['/'.join(prefix)]
                    current = _metadata(os.fstat(child))
                    try:
                        require(all(current[k] == expected[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode')), 'removal parent replaced')
                    except BaseException:
                        os.close(child); raise
                    os.close(parent); parent = child
                expected = manifest[name]
                current = _metadata(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False))
                require(all(current[k] == expected[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode', 'directory')),
                        'removal object replaced')
                if expected['directory']: os.rmdir(parts[-1], dir_fd=parent)
                else:
                    require(current == {k: v for k, v in expected.items() if k != 'sha256'},
                            'removal file metadata changed')
                    fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
                    try: require(_hash_fd(fd, current) == expected['sha256'], 'removal content changed')
                    finally: os.close(fd)
                    require(_metadata(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)) == current,
                            'removal input changed')
                    os.unlink(parts[-1], dir_fd=parent)
            finally: os.close(parent)
        current = _metadata(source.lstat()); expected = manifest['.']
        require(all(current[k] == expected[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode')), 'removal root replaced')
        os.fsync(root)
        parent = _directory_fd(source.parent)
        try:
            os.rmdir(source.name, dir_fd=parent)  # Fails on unplanned remaining objects.
            os.fsync(parent)
        finally: os.close(parent)
    finally: os.close(root)


def finish_cleanup(inv, receipts):
    """Publish completion only after removal; failures remain explicitly unconfirmed.

    A failed final directory fsync can leave replaced metadata visible. The
    durably reserved uncertainty marker therefore overrides the inventory flag
    until the entire completion write and marker removal have succeeded.
    """
    marker = inv.evidence/'completion-unconfirmed'
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(b'Completion is not confirmed while this marker exists.\n')
        f.flush(); os.fsync(f.fileno())
    parent = _directory_fd(inv.evidence)
    try:
        os.fsync(parent)
        inv.data['cleanup_complete'] = True
        inv.data['cleanup_phase'] = 'complete'
        inv.data['archives'] = [r['destination'] for r in receipts]
        try:
            inv.write()
            os.unlink(marker)
            os.fsync(parent)
        except BaseException:
            inv.data['cleanup_complete'] = False
            inv.data['cleanup_phase'] = 'completion_unconfirmed'
            # Never retry the ambiguous inventory write or report completion.
            # Marker may have been unlinked before its parent fsync failed;
            # in that case return failure, with durability explicitly unknown.
            raise
    finally:
        os.close(parent)


def snapshot(root, staged_copy=False):
    root = Path(root)
    require(root.is_dir() and root.resolve() == root, 'unsafe snapshot root')
    raw = read(root/'SOURCE_MANIFEST.json', 8*1024*1024)
    require(hashlib.sha256(raw).hexdigest() == PIN, 'manifest pin mismatch')
    require(read(root/'SOURCE_MANIFEST.sha256') == (PIN+'\n').encode(), 'digest file mismatch')
    m = json.loads(raw)
    require(m['snapshot_id'] == 'hids-src-20261108T012355Z-e520e3a020ed' and
            (staged_copy or root.name == m['snapshot_id']) and m['manifest_version'] == 1,
            'manifest shape')
    files, dirs = set(), set()
    for parent, children, leaves in os.walk(root, followlinks=False):
        for name in children:
            p = Path(parent)/name
            require(not p.is_symlink() and p.is_dir(), 'snapshot directory link')
            dirs.add(p.relative_to(root).as_posix())
        for name in leaves:
            p = Path(parent)/name
            require(not p.is_symlink(), 'snapshot file link')
            files.add(p.relative_to(root).as_posix())
    expected_dirs = set()
    for name, wanted in m['files'].items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name, 'manifest path')
        expected_dirs.update(str(p) for p in rel.parents if str(p) != '.')
        require(digest(root/name) == wanted, 'source hash mismatch: '+name)
    require(files == set(m['files']) | {'SOURCE_MANIFEST.json', 'SOURCE_MANIFEST.sha256'}, 'file inventory')
    require(dirs == expected_dirs, 'directory inventory')
    return m


class Inventory:
    def __init__(self, evidence, initial=None):
        self.evidence = Path(evidence)
        self.path = self.evidence/'inventory.json'
        if initial is not None:
            self.data = initial
            self.write(initial=True)
        else:
            protected(self.evidence)
            s = self.path.lstat()
            require(s.st_uid == s.st_gid == 0 and stat.S_IMODE(s.st_mode) == 0o600,
                    'inventory ownership')
            self.data = json.loads(read(self.path, 1024*1024))
            s = self.evidence.lstat()
            require((s.st_dev, s.st_ino, s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) ==
                    tuple(self.data['evidence_identity']), 'evidence directory replaced')
        if os.path.lexists(self.evidence/'completion-unconfirmed'):
            self.data['cleanup_complete'] = False
            self.data['cleanup_phase'] = 'completion_unconfirmed'
        self.base = Path(self.data['base'])

    def write(self, initial=False):
        raw = (json.dumps(self.data, sort_keys=True, indent=2)+'\n').encode()
        require(len(raw) <= 1024*1024, 'inventory metadata bound')
        target = self.path if initial else self.evidence/'.inventory-next'
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        if not initial:
            os.replace(target, self.path)  # Only this run's mutable inventory.
        parent = _directory_fd(self.evidence)
        try: os.fsync(parent)
        finally: os.close(parent)

    def remember(self, path, mutable=False):
        p = Path(path); s = p.lstat()
        item = dict(path=str(p), dev=s.st_dev, ino=s.st_ino, uid=s.st_uid,
                    gid=s.st_gid, mode=stat.S_IMODE(s.st_mode), directory=p.is_dir())
        if not item['directory']:
            require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'unsafe created file')
            item['sha256'] = None if mutable else digest(p)
        self.data['entries'].append(item); self.write()

    def check(self):
        for item in self.data['entries']:
            p = Path(item['path']); s = p.lstat()
            require(not p.is_symlink() and
                    (s.st_dev, s.st_ino, s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) ==
                    (item['dev'], item['ino'], item['uid'], item['gid'], item['mode']),
                    'created resource replaced/changed: '+str(p))
            require(stat.S_ISDIR(s.st_mode) if item['directory'] else stat.S_ISREG(s.st_mode), 'resource type')
            if not item['directory']:
                require(s.st_nlink == 1, 'created file hardlinked')
            if item.get('sha256') is not None:
                require(digest(p) == item['sha256'], 'created file content changed: '+str(p))

    def directory(self, path, mode=0o755, uid=0, gid=0):
        p = Path(path); protected(p.parent)
        p.mkdir(mode=mode)  # No parents/exist_ok; reservation is exclusive.
        os.chown(p, uid, gid)  # Only the directory just created by this call.
        require(stat.S_IMODE(p.stat().st_mode) == mode, 'creation mode')
        self.remember(p)

    def file(self, path, data, mode=0o644, gid=0, mutable=False):
        p = Path(path); protected(p.parent)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(fd, 'wb') as f:
            os.fchown(f.fileno(), 0, gid)
            f.write(data); f.flush(); os.fsync(f.fileno())
        require(stat.S_IMODE(p.stat().st_mode) == mode, 'creation mode')
        self.remember(p, mutable)

    def units_owned(self):
        self.check()
        recorded = {e['path'] for e in self.data['entries']}
        owned = [u for u in UNITS if '/run/systemd/system/'+u in recorded]
        for u in owned:
            p = subprocess.run(['systemctl', 'show', u, '-p', 'FragmentPath', '--value'],
                               capture_output=True, text=True, timeout=5)
            require(p.stdout.strip() in ('', '/run/systemd/system/'+u), 'unit shadowed: '+u)
            if p.stdout.strip():
                dropins = subprocess.run(['systemctl', 'show', u, '-p', 'DropInPaths', '--value'],
                                         capture_output=True, text=True, timeout=5, check=True).stdout.split()
                wanted = [] if u.endswith('.socket') else ['/run/systemd/system/'+u+'.d/m2-acceptance.conf']
                require(dropins == wanted, 'unexpected effective drop-ins: '+u)
        return owned

    def stop(self):
        owned = self.units_owned()
        if owned:
            subprocess.run(['systemctl', 'stop', *reversed(owned)], check=True, timeout=30)
            for u in owned:
                p = subprocess.run(['systemctl', 'show', u, '-p', 'ActiveState', '--value'],
                                   capture_output=True, text=True, timeout=5, check=True)
                require(p.stdout.strip() in ('inactive', 'failed'), 'unit still active: '+u)
        return owned


def config(raw):
    j = json.loads(raw)
    require(set(j) == {'source_id', 'max_records', 'max_pages'}, 'config shape')
    u = uuid.UUID(j['source_id'])
    require(u.version == 4 and str(u) == j['source_id'], 'source UUIDv4')
    require(type(j['max_records']) is int and 1 <= j['max_records'] <= 2**63-1, 'max_records')
    require(type(j['max_pages']) is int and 16 <= j['max_pages'] <= 2147483646, 'max_pages')
    return j


def main():
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'root resource helper required')
    os.umask(0o022)
    evidence, action, *args = sys.argv[1:]
    if action == 'init':
        base, source, cfg, binary, probe = map(Path, args)
        require(re.fullmatch(r'/run/hids-m2-acceptance-[0-9a-f]{32}', str(base)), 'base name')
        require(evidence == '/var/lib/'+base.name, 'evidence name')
        m = snapshot(source); settings = config(read(cfg, 4096))
        for u in UNITS:
            p = subprocess.run(['systemctl', 'show', u, '-p', 'LoadState', '--value'],
                               capture_output=True, text=True, timeout=5)
            require(p.stdout.strip() == 'not-found', 'existing unit: '+u)
        required_absent = [base, Path(evidence), Path('/run/hids'), Path('/var/lib/hids')]
        required_absent += [Path('/run/systemd/system')/u for u in UNITS]
        required_absent += [Path('/run/systemd/system')/(u+'.d') for u in UNITS]
        for folder in ('/etc/systemd/system', '/usr/lib/systemd/system', '/lib/systemd/system'):
            required_absent += [Path(folder)/name for u in UNITS for name in (u, u+'.d')]
        for p in required_absent:
            require(not os.path.lexists(p), 'existing resource: '+str(p))
        protected(base.parent); protected(Path(evidence).parent)
        Path(evidence).mkdir(mode=0o700)
        e = Path(evidence).lstat()
        inv = Inventory(evidence, dict(base=str(base), entries=[], source_id=settings['source_id'],
                                       manifest=PIN, cleanup_complete=False,
                                       evidence_identity=[e.st_dev,e.st_ino,e.st_uid,e.st_gid,stat.S_IMODE(e.st_mode)],
                                       mutable_bookkeeping=str(Path(evidence)/'inventory.json'),
                                       service_managed_paths=['/run/hids/control.sock',
                                           '/run/hids/ingest/journal.sock', '/var/lib/hids/m2/journal.sqlite',
                                           '/var/lib/hids/m2/journal.sqlite-wal', '/var/lib/hids/m2/journal.sqlite-shm']))
        inv.directory(base)
        inv.file(base/'resources.py', read(__file__))
        inv.file(base/'probe.py', read(probe))
        inv.file(base/'m2.json', read(cfg, 4096))
        inv.file(Path(evidence)/'m2.json', read(cfg, 4096), 0o600)
        inv.file(Path(evidence)/'SOURCE_MANIFEST.json', read(source/'SOURCE_MANIFEST.json'), 0o600)
        inv.directory(base/'code')
        dirs = sorted({p for name in m['files'] for p in PurePosixPath(name).parents if str(p) != '.'},
                      key=lambda p: (len(p.parts), str(p)))
        for p in dirs: inv.directory(base/'code'/str(p))
        for name, wanted in m['files'].items():
            data = read(source/name)
            require(hashlib.sha256(data).hexdigest() == wanted, 'source changed during copy')
            inv.file(base/'code'/name, data)
        for name in ('SOURCE_MANIFEST.json', 'SOURCE_MANIFEST.sha256'):
            inv.file(base/'code'/name, read(source/name))
        snapshot(base/'code', staged_copy=True)
        executable = read(binary)
        require(executable[:4] == b'\x7fELF' and executable[4:6] == b'\x02\x01' and
                int.from_bytes(executable[18:20], 'little') == 183, 'expected ARM64 ELF reader')
        inv.file(base/'m2-reader', executable, 0o755)
        import grp
        ingest = pwd.getpwnam('hids-ingest'); ipc = grp.getgrnam('hids-ipc').gr_gid
        inv.directory('/run/hids')
        inv.directory('/run/hids/ingest', 0o750, ingest.pw_uid, ipc)
        inv.directory('/var/lib/hids')
        inv.directory('/var/lib/hids/m2', 0o700, ingest.pw_uid, ingest.pw_gid)
        for label in ('reader.stderr', 'ingest.stderr'):
            inv.file(Path(evidence)/label, b'', 0o600, mutable=True)
        for u in UNITS:
            inv.file(Path('/run/systemd/system')/u, read(base/'code/packaging/systemd'/u))
        for u, body in (
            ('hids-ingest.service', f'[Service]\nWorkingDirectory={base}/code\nExecStart=\n'
             f'ExecStart=/usr/bin/python3 -B -m engine.ingestion.m2_service --config {base}/m2.json\n'
             f'ExecStopPost=/usr/bin/python3 -I -B {base}/probe.py record-exit ingest\n'
             f'StandardError=append:{evidence}/ingest.stderr\n'),
            ('hids-journal.service', f'[Service]\nExecStart=\n'
             f'ExecStart={base}/m2-reader --config {base}/m2.json\n'
             f'ExecStopPost=/usr/bin/python3 -I -B {base}/probe.py record-exit reader\n'
             f'StandardError=append:{evidence}/reader.stderr\n')):
            folder = Path('/run/systemd/system')/(u+'.d')
            inv.directory(folder)
            inv.file(folder/'m2-acceptance.conf', body.encode())
        inv.check()
        print('Prepared exclusively; no unit started. Evidence:', evidence)
        return
    inv = Inventory(evidence)
    require(not inv.data['cleanup_complete'], 'this run has already been cleaned up')
    inv.check()
    if action == 'verify':
        require(set(inv.units_owned()) == set(UNITS), 'incomplete unit set')
        for u in UNITS:
            actual = subprocess.run(['systemctl', 'show', u, '-p', 'FragmentPath', '--value'],
                                    capture_output=True, text=True, timeout=5, check=True).stdout.strip()
            require(actual == '/run/systemd/system/'+u, 'unit not loaded from this run')
        print('Loaded unit fragments, drop-ins and created-resource inventory verified')
    elif action == 'save':
        name, audience = args
        require(re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', name), 'evidence filename')
        raw = sys.stdin.buffer.read(LIMIT+1)
        require(len(raw) <= LIMIT, 'evidence bound')
        if audience == 'private': inv.file(Path(evidence)/name, raw, 0o600)
        elif audience == 'reader':
            inv.file(inv.base/name, raw, 0o640, pwd.getpwnam('hids-journal').pw_gid)
        elif audience == 'ingest':
            inv.file(inv.base/name, raw, 0o640, pwd.getpwnam('hids-ingest').pw_gid)
        else: raise RuntimeError('unknown audience')
    elif action == 'stop':
        inv.stop(); print('Owned units stopped; evidence retained')
    elif action == 'cleanup':
        owned = inv.stop()
        for endpoint in ('/run/hids/control.sock', '/run/hids/ingest/journal.sock'):
            require(not os.path.lexists(endpoint), 'stale socket; preserve and investigate: '+endpoint)
        db = Path('/var/lib/hids/m2'); ingest = pwd.getpwnam('hids-ingest')
        receipts = prepare_archives(inv, db, ingest)
        for item in list(inv.data['entries']):
            p = Path(item['path'])
            if str(p).startswith('/run/systemd/system/') and not item['directory']:
                inv.file(Path(evidence)/('unit-'+p.parent.name+'-'+p.name), read(p), 0o600)
        # Last non-destructive gate: all archives and both original trees must
        # still match before removing ANY source object or unit definition.
        inv.check()
        for receipt in receipts:
            verify_archive(receipt)
            require(tree_manifest(Path(receipt['source'])) == receipt['manifest'], 'source changed before deletion')
        inv.data['cleanup_phase'] = 'removing_verified_sources'; inv.write()
        remove_archived_sources(receipts)
        # Verify again before unlinking only recorded unit files/directories.
        for item in reversed(inv.data['entries']):
            p = Path(item['path'])
            if str(p).startswith('/run/systemd/system/'):
                s = p.lstat()
                require((s.st_dev, s.st_ino, s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) ==
                        (item['dev'], item['ino'], item['uid'], item['gid'], item['mode']),
                        'unit resource changed during cleanup')
                if not item['directory']:
                    require(digest(p) == item['sha256'], 'unit content changed during cleanup')
                p.rmdir() if item['directory'] else p.unlink()
        for name in ('/run/hids/ingest', '/run/hids', '/var/lib/hids'):
            item = next(e for e in inv.data['entries'] if e['path'] == name)
            s = Path(name).lstat()
            require((s.st_dev, s.st_ino, s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) ==
                    (item['dev'], item['ino'], item['uid'], item['gid'], item['mode']), 'cleanup directory replaced')
            Path(name).rmdir()  # Only these initially absent, inventoried directories.
        subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=15)
        finish_cleanup(inv, receipts)
        print('Runtime units removed; private evidence preserved:', evidence)
    else:
        raise RuntimeError('unknown resource operation')


if __name__ == '__main__':
    main()
PY
```

```bash
cat > "$BUILD/probe.py" <<'PY'
"""Temporary acceptance probes: no journal API and no SQLite writer.

The proxy forwards one SSH TCP stream without retaining its contents. All DB
operations use production read-only connections. Replay uses one stored envelope.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
DB = Path('/var/lib/hids/m2/journal.sqlite')


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def proxy(target):
    require(os.getuid() == os.geteuid() != 0, 'ordinary-user SSH proxy required')
    started = time.monotonic_ns() // 1000
    with socket.create_connection(('127.0.0.1', 22), timeout=5) as sock:
        metadata = dict(address='127.0.0.1', server_port=22, port=sock.getsockname()[1],
                        started_monotonic_us=started,
                        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-', ''))
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(metadata, f); f.write('\n')
        deadline = time.monotonic()+15
        inputs = [0, sock]
        while time.monotonic() < deadline:
            ready, _, _ = select.select(inputs, [], [], max(0, min(1, deadline-time.monotonic())))
            for item in ready:
                data = os.read(0, 32768) if item == 0 else sock.recv(32768)
                if not data:
                    if item != 0:
                        return
                    inputs.remove(0); sock.shutdown(socket.SHUT_WR)
                elif item == 0:
                    sock.sendall(data)
                else:
                    view = memoryview(data)
                    while view:
                        n = os.write(1, view)
                        require(n > 0, 'SSH stdout closed')
                        view = view[n:]
        raise RuntimeError('SSH proxy deadline exceeded')


def initialize():
    # Trusted, root-owned code copy supplied by the acceptance resource helper.
    sys.path.insert(0, str(BASE/'code'))
    global CFG, contract, receiver, store_module, m1_store, m1_security, m1_contract
    from engine.ingestion import m2_contract as contract, m2_receiver as receiver
    from engine.ingestion import m1_security, m1_contract
    from engine.ingestion.m2_service import load_config
    from engine.database import m2_store as store_module, m1_store
    CFG = load_config(BASE/'m2.json')


def identity(role):
    policy = receiver.service_policy(role)
    fields = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('Uid', 'Gid', 'Groups', 'CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd', 'NoNewPrivs'):
            fields[key] = value.split()
    require(list(map(int, fields['Uid'])) == [os.getuid()]*4, 'UID mismatch')
    require(list(map(int, fields['Gid'])) == [os.getgid()]*4, 'GID mismatch')
    require(all(int(fields[k][0], 16) == 0 for k in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd')),
            'unexpected service capabilities')
    require(fields['NoNewPrivs'] == ['1'], 'NoNewPrivs required')
    return policy


def root_control(*args, timeout=6):
    require(os.getuid() == os.geteuid() == 0, 'root control probe required')
    p = subprocess.run(['/usr/bin/python3', '-B', '-m', 'engine.ingestion.m2_control',
                        *args, '--config', str(BASE/'m2.json')], cwd=BASE/'code',
                       env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'},
                       capture_output=True, timeout=timeout)
    require(p.returncode == 0 and len(p.stdout) <= 2049 and p.stdout.endswith(b'\n'),
            'production root control failed/unconfirmed')
    return contract.decode(p.stdout[:-1], 2048)


def unit_pid(unit):
    require(unit in ('hids-ingest.service', 'hids-journal.service'), 'unexpected unit')
    p = subprocess.run(['systemctl', 'show', unit, '-p', 'MainPID', '--value'],
                       capture_output=True, text=True, timeout=3, check=True)
    return int(p.stdout.strip())


def wait_status(state, reader):
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        value = root_control('status', timeout=min(6, max(.1, deadline-time.monotonic())))
        require(value['failure'] is None, 'ingestion reports failure')
        require(value['source_id'] == CFG['source_id'], 'status source')
        states = ('anchored', 'empty_unanchored') if state == 'running' else (state,)
        pid = unit_pid('hids-journal.service')
        ready = (value['state'] in states and
                 ((reader == 'none' and not value['reader_connected'] and pid == 0) or
                  (reader == 'unit' and pid > 0 and value['reader_connected'] and value['reader_pid'] == pid)))
        if ready:
            print(json.dumps(value, sort_keys=True)); return
        time.sleep(.1)
    raise RuntimeError('status readiness deadline exceeded')


def wait_exit():
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        p = subprocess.run(['systemctl', 'show', 'hids-journal.service',
                            '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus',
                            '-p', 'ExecMainCode'], capture_output=True, text=True, timeout=3, check=True)
        info = dict(line.split('=', 1) for line in p.stdout.splitlines())
        # MainPID can become zero while ExecStopPost is still running.
        require(info['ActiveState'] != 'failed', 'reader unit failed')
        if info['MainPID'] == '0' and info['ActiveState'] == 'inactive':
            require(info['ActiveState'] == 'inactive' and info['Result'] == 'success' and
                    info['ExecMainStatus'] == '0', 'reader did not exit cleanly')
            marker = latest_exit('reader')
            require((marker['result'], marker['exit_code'], marker['exit_status']) ==
                    ('success', 'exited', '0'), 'reader stop hook did not record exit 0')
            print(json.dumps(dict(unit=info, exit_marker=marker))); return
        time.sleep(.1)
    raise RuntimeError('reader exit deadline exceeded')


def latest_exit(role):
    require(os.getuid() == 0 and role in ('reader', 'ingest'), 'root exit evidence reader required')
    path = Path('/var/lib')/BASE.name/(role+'.stderr')
    with path.open('rb') as f:
        raw = f.read(1024*1024+1)
    require(len(raw) <= 1024*1024, 'exit diagnostic bound')
    prefix = b'M2_ACCEPTANCE_EXIT '
    markers = [json.loads(line[len(prefix):]) for line in raw.splitlines() if line.startswith(prefix)]
    require(markers and markers[-1]['role'] == role, 'missing exit marker')
    return markers[-1]


def record_exit(role):
    import pwd
    require(role in ('reader', 'ingest'), 'exit role')
    who = pwd.getpwnam('hids-journal' if role == 'reader' else 'hids-ingest')
    require(os.getuid() == os.geteuid() == who.pw_uid and os.getgid() == os.getegid() == who.pw_gid,
            'exit recorder service identity')
    marker = dict(role=role, uid=os.getuid(), gid=os.getgid(),
                  result=os.environ.get('SERVICE_RESULT'), exit_code=os.environ.get('EXIT_CODE'),
                  exit_status=os.environ.get('EXIT_STATUS'), invocation=os.environ.get('INVOCATION_ID'),
                  observed_monotonic_ns=time.monotonic_ns())
    require(all(marker[k] is not None for k in ('result', 'exit_code', 'exit_status', 'invocation')),
            'missing manager exit metadata')
    print('M2_ACCEPTANCE_EXIT '+json.dumps(marker, sort_keys=True), file=sys.stderr, flush=True)


def runtime_credentials(include_reader=True):
    import grp
    import pwd
    identities = (
        ('hids-ingest.service', 'hids-ingest', ('hids-ipc',)),
        ('hids-journal.service', 'hids-journal', ('hids-ipc', 'systemd-journal')))
    for unit, account, extra in identities if include_reader else identities[:1]:
        pid = unit_pid(unit); require(pid > 0, 'missing service process')
        who = pwd.getpwnam(account); values = {}
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            key, _, value = line.partition(':'); values[key] = value.split()
        require(list(map(int, values['Uid'])) == [who.pw_uid]*4, 'runtime UID')
        require(list(map(int, values['Gid'])) == [who.pw_gid]*4, 'runtime GID')
        expected = {who.pw_gid} | {grp.getgrnam(g).gr_gid for g in extra}
        require(set(map(int, values['Groups'])) | {who.pw_gid} == expected, 'runtime groups')
        require(all(int(values[k][0], 16) == 0 for k in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd')), 'runtime capabilities')
        require(values['NoNewPrivs'] == ['1'], 'runtime NoNewPrivs')
        print(json.dumps(dict(unit=unit, pid=pid, uid=who.pw_uid, gid=who.pw_gid, groups=sorted(expected))))
        if account == 'hids-ingest':
            env = dict(x.split(b'=', 1) for x in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in x)
            require(env.get(b'LISTEN_PID') == str(pid).encode() and env.get(b'LISTEN_FDS') == b'1', 'actual socket activation environment')
            require(os.readlink(f'/proc/{pid}/fd/3').startswith('socket:['), 'FD 3 missing')
    for name, uid, gid, mode in (
        ('/run/hids', 0, 0, 0o755),
        ('/run/hids/control.sock', 0, 0, 0o600),
        ('/run/hids/ingest', pwd.getpwnam('hids-ingest').pw_uid, grp.getgrnam('hids-ipc').gr_gid, 0o750),
        ('/var/lib/hids/m2', pwd.getpwnam('hids-ingest').pw_uid, pwd.getpwnam('hids-ingest').pw_gid, 0o700),
        ('/run/hids/ingest/journal.sock', pwd.getpwnam('hids-ingest').pw_uid, grp.getgrnam('hids-ipc').gr_gid, 0o660)):
        p = Path(name); s = p.lstat()
        require(p.resolve() == p and (s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) == (uid, gid, mode), 'runtime path metadata')
        require(stat.S_ISSOCK(s.st_mode) if name.endswith('.sock') else stat.S_ISDIR(s.st_mode), 'runtime path type')
        print(json.dumps(dict(path=name, uid=s.st_uid, gid=s.st_gid, mode=oct(stat.S_IMODE(s.st_mode)))))
    print('Runtime identities, socket metadata, and actual FD-3 inheritance verified')


def bounded(db, sql, cap):
    rows = db.execute(sql).fetchmany(cap+1)
    require(len(rows) <= cap, 'acceptance retrieval bound exceeded')
    return rows


def snapshot():
    identity('ingest')
    m1_security.private_directory(DB.parent)
    m1_security.private_file(DB)
    m1_store.check_sidecars(DB)
    for path in (DB, Path(str(DB)+'-wal'), Path(str(DB)+'-shm')):
        if path.exists():
            info = path.lstat()
            require(info.st_gid == os.getgid() and stat.S_IMODE(info.st_mode) == 0o600,
                    'database/sidecar group or mode')
    with contextlib.closing(m1_store.connect(DB, reader=True)) as db:
        m1_store.profile(db, reader=True)
        db.execute('BEGIN')
        try:
            store_module.Store.schema(db)
            tables = {
                'dispositions': bounded(db, 'SELECT * FROM dispositions ORDER BY revision', min(CFG['max_records'], 1000)),
                'progress': bounded(db, 'SELECT * FROM progress ORDER BY source', 1),
                'activations': bounded(db, 'SELECT * FROM activations ORDER BY activation', 100),
            }
            gaps = bounded(db, 'SELECT * FROM gaps ORDER BY id', 1000)
            page_size = db.execute('PRAGMA page_size').fetchone()[0]
            page_count = db.execute('PRAGMA page_count').fetchone()[0]
        finally:
            db.execute('ROLLBACK')
    events = []
    for row in tables['dispositions']:
        identifier, source, cursor, kind, stable, envelope, revision, received, stored = row
        event = contract.validate_event(contract.decode(envelope.encode('ascii')))
        require(source == CFG['source_id'] == event['source_id'] and cursor == event['cursor'], 'stored provenance')
        require(identifier == event['event_id'] == contract.event_id(source, cursor), 'cursor identity')
        require(kind == event['message_type'] and stable == contract.canonical(event), 'stored native content')
        require(type(revision) is int and revision == event['expected_revision']+1, 'stored revision')
        m1_contract.timestamp(received); m1_contract.timestamp(stored)
        if kind == 'journal_event':
            require(store_module.get_event(DB, identifier) == event, 'independent fresh read-only retrieval')
            events.append((row, event))
    p = tables['progress']
    if p:
        require(p[0][0] == CFG['source_id'], 'checkpoint source')
        if tables['dispositions']:
            last = tables['dispositions'][-1]
            require((p[0][4], p[0][5]) == (last[6], last[2]), 'checkpoint/record alignment')
    else:
        require(not tables['dispositions'], 'events without checkpoint')
    return tables, gaps, events, page_size, page_count


def correlate(baseline, connection):
    require(type(baseline) is int and baseline >= 0, 'baseline')
    meta = json.loads(connection)
    require(set(meta) == {'address', 'server_port', 'port', 'started_monotonic_us', 'boot_id'} and
            meta['address'] == '127.0.0.1' and meta['server_port'] == 22 and
            type(meta['port']) is int and 1 <= meta['port'] <= 65535 and
            type(meta['started_monotonic_us']) is int and meta['started_monotonic_us'] > 0 and
            re.fullmatch('[0-9a-f]{32}', meta['boot_id']), 'connection metadata')
    tables, gaps, events, size, pages = snapshot()
    require(len(tables['progress']) == 1, 'missing activation')
    activation = tables['progress'][0][1]
    pattern = re.compile(r'(?<![0-9.])127\.0\.0\.1 port '+str(meta['port'])+r'\b')
    selected = [(row, event) for row, event in events if row[6] > baseline and
                event['activation_id'] == activation and event['journal']['boot_id'] == meta['boot_id'] and
                meta['started_monotonic_us'] <= int(event['journal']['monotonic_us']) <= time.monotonic_ns()//1000 and
                pattern.search(event['fields']['MESSAGE'])]
    return selected


def receive(sock):
    raw = bytearray()
    while True:
        byte = sock.recv(1)
        if not byte: raise EOFError('peer closed before complete response')
        if byte == b'\n': return contract.decode(bytes(raw), 2048)
        require(len(raw) < 2048, 'response accumulator bound')
        raw.extend(byte)


def reader_channel():
    peer, ipc = identity('reader')
    path = Path('/run/hids/ingest/journal.sock')
    s = path.lstat()
    require(stat.S_ISSOCK(s.st_mode) and path.resolve() == path and
            (s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) == (peer.uid, ipc, 0o660), 'data socket')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sock.settimeout(5)
    try:
        sock.connect(str(path)); pid = peer.check(sock)
        return sock, pid
    except BaseException:
        sock.close(); raise


def reconcile(value, event):
    m1_contract.keys(value, 'protocol_version message_type source_id activation_id state revision cursor boundary_start boundary_end')
    m1_contract.integer(value['protocol_version'], 2, 2)
    require(value['message_type'] == 'progress' and value['source_id'] == event['source_id'] and
            value['activation_id'] == event['activation_id'] and value['state'] == 'anchored', 'reconcile identity/state')
    require(m1_contract.uuid_valid(value['source_id']) and m1_contract.uuid_valid(value['activation_id']), 'reconcile UUIDs')
    m1_contract.integer(value['revision'], 1, contract.MAX_REVISION)
    require(value['revision'] >= event['expected_revision']+1, 'reconcile revision')
    contract.event_id(value['source_id'], value['cursor'])
    m1_contract.timestamp(value['boundary_start']); m1_contract.timestamp(value['boundary_end'])


def replay(path):
    identity('reader')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == 0 and
                s.st_gid == os.getgid() and stat.S_IMODE(s.st_mode) == 0o640, 'replay file policy')
        raw = f.read(65538)
    require(len(raw) <= 65537 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'immutable replay frame')
    event = contract.validate_event(contract.decode(raw[:-1]))
    require(event['source_id'] == CFG['source_id'] and event['message_type'] == 'journal_event', 'replay source')
    sock, pid = reader_channel()
    with sock:
        sock.sendall(contract.frame({'protocol_version': 2, 'message_type': 'reconcile'}, 2048))
        reconcile(receive(sock), event)
        sock.sendall(raw)
        ack = contract.validate_response(receive(sock), event['event_id'])
        require(ack['message_type'] == 'ack' and ack['result'] == 'duplicate' and
                ack['checkpoint_revision'] == event['expected_revision']+1, 'duplicate receipt')
        print(json.dumps(dict(result='duplicate', checkpoint_revision=ack['checkpoint_revision'],
                              server_pid=pid, replay_pid=os.getpid())))


def main():
    action, *args = sys.argv[1:]
    if action == 'proxy':
        proxy(*args); return
    if action == 'record-exit':
        record_exit(*args); return
    initialize()
    if action == 'wait': wait_status(*args)
    elif action == 'exit-ok': wait_exit()
    elif action == 'crash-ok':
        require(os.getuid() == 0, 'root crash evidence probe')
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            state = subprocess.run(['systemctl', 'show', 'hids-journal.service', '-p', 'ActiveState', '--value'],
                                   capture_output=True, text=True, timeout=3, check=True).stdout.strip()
            if state == 'failed':
                value = latest_exit('reader')
                require((value['result'], value['exit_code'], value['exit_status']) ==
                        ('signal', 'killed', 'KILL'), 'unexpected crash outcome')
                print(json.dumps(value)); return
            time.sleep(.1)
        raise RuntimeError('reader crash exit evidence missing')
    elif action in ('runtime', 'runtime-ingest'):
        require(os.getuid() == 0, 'root metadata probe'); runtime_credentials(action == 'runtime')
    elif action == 'stopped':
        require(os.getuid() == 0, 'root metadata probe')
        for unit in ('hids-journal.service', 'hids-ingest.service'):
            require(unit_pid(unit) == 0, 'service still running')
            p = subprocess.run(['systemctl', 'show', unit, '-p', 'Result', '-p', 'ExecMainStatus',
                                '-p', 'ActiveState', '-p', 'ExecMainCode'], capture_output=True, text=True, timeout=3, check=True)
            info = dict(x.split('=', 1) for x in p.stdout.splitlines())
            require(info['Result'] == 'success' and info['ExecMainStatus'] == '0' and
                    info['ActiveState'] == 'inactive', 'unclean stop')
            role = 'reader' if unit == 'hids-journal.service' else 'ingest'
            value = latest_exit(role)
            require((value['result'], value['exit_code'], value['exit_status']) ==
                    ('success', 'exited', '0'), 'missing successful exit evidence')
        require(not os.path.lexists('/run/hids/control.sock') and
                not os.path.lexists('/run/hids/ingest/journal.sock'), 'stale endpoint')
        print('Both services exited cleanly; both sockets removed')
    elif action == 'isolation':
        role, paths = args; identity(role)
        names = json.loads(paths)
        require(names and len(names) <= 1000, 'journal metadata bound')
        access = [os.access(p, os.R_OK) for p in names]
        if role == 'reader':
            require(any(access) and not os.access(DB.parent, os.R_OK | os.X_OK), 'reader storage/journal isolation')
        else:
            require(not any(access), 'ingestion can read assessed journal files')
            m1_security.private_directory(DB.parent)
        print(json.dumps(dict(role=role, assessed_files=len(names), isolation=True)))
    elif action == 'journal-denied':
        # Post-activation only: test open permission, never read a record/byte.
        identity('ingest')
        names = json.loads(args[0])
        require(names and len(names) <= 1000, 'journal metadata bound')
        for name in names:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except PermissionError:
                continue
            else:
                os.close(fd)
                raise RuntimeError('ingestion unexpectedly opened assessed journal file')
        print(json.dumps(dict(ingestion_journal_opens_denied=len(names), payload_bytes_read=0)))
    elif action == 'replay': replay(*args)
    elif action == 'compete':
        sock, pid = reader_channel()
        with sock:
            try:
                sock.sendall(contract.frame({'protocol_version': 2, 'message_type': 'reconcile'}, 2048))
                receive(sock)
            except (EOFError, BrokenPipeError, ConnectionResetError):
                print(json.dumps(dict(second_reader_rejected=True, server_pid=pid))); return
        raise RuntimeError('second reader was not rejected')
    elif action in ('match', 'export'):
        deadline = time.monotonic()+30
        while True:
            matches = correlate(int(args[0]), args[1])
            if matches:
                row, event = matches[-1]
                if action == 'export': sys.stdout.write(row[5]+'\n')
                else: print(json.dumps(dict(event_id=row[0], revision=row[6], controlled_port_matched=True,
                                           boot_monotonic_time_matched=True, fresh_readonly_retrieval=True)))
                return
            require(action == 'match' and time.monotonic() < deadline, 'no correlated SSH event; do not broaden scope')
            time.sleep(.1)
    else:
        tables, gaps, events, size, pages = snapshot()
        p = tables['progress']
        if action == 'fingerprint':
            print(hashlib.sha256(json.dumps(tables, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        elif action == 'revision': print(p[0][4] if p else 0)
        elif action == 'state': print(json.dumps(tables, sort_keys=True, separators=(',', ':')))
        elif action == 'check-prefix':
            fd = os.open(args[0], os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as f:
                info = os.fstat(f.fileno())
                require(info.st_uid == 0 and info.st_gid == os.getgid() and
                        stat.S_IMODE(info.st_mode) == 0o640 and info.st_nlink == 1,
                        'baseline file metadata')
                raw = f.read(32*1024*1024+1)
            require(len(raw) <= 32*1024*1024, 'baseline bound')
            old = json.loads(raw)
            require(set(old) == set(tables) and old['activations'] == [list(x) for x in tables['activations']],
                    'activation changed during recovery')
            previous = {x[0]: x for x in old['dispositions']}
            current = {x[0]: list(x) for x in tables['dispositions']}
            require(all(current.get(k) == v for k, v in previous.items()), 'stored event changed/lost')
            require(len(old['progress']) == len(p) == 1, 'checkpoint cardinality')
            a, b = old['progress'][0], p[0]
            require(a[:4] == list(b[:4]) and a[6:] == list(b[6:]), 'activation/boundary changed')
            require(b[3] == 'anchored' and b[4]-a[4] == len(current)-len(previous) >= 0,
                    'checkpoint rewind or invalid advance')
            print(json.dumps(dict(recovered_same_interval=True, original_records_unchanged=True,
                                  new_dispositions=len(current)-len(previous))))
        elif action == 'summary':
            print(json.dumps(dict(dispositions=len(tables['dispositions']), events=len(events),
                                  state=p[0][3] if p else 'inactive', revision=p[0][4] if p else 0,
                                  gaps=[g[5] for g in gaps], page_size=size, page_count=pages,
                                  activity_wall_time='not_established')))
        else: raise RuntimeError('unknown probe operation')


if __name__ == '__main__':
    main()
PY
```

Validate the pasted helper bytes before executing either with privileges:

```bash
printf '%s  %s\n' \
    'f7a241c6bdfe47ca50a556c01a642b47dd32129d2071ae8bf848d322983022bb' "$BUILD/resources.py" \
    '2c7a22c6ea0c7d2143536c5af90c60b6bda3965f43f1a877181f2a54ad9a4a5e' "$BUILD/probe.py" | sha256sum -c -
```

**Expected:** strict compilation, reader help and both checksums pass. No reader
journal handle has been opened. **Stop:** missing approvals, bad values, compiler
failure or altered pasted code. No sanitizer/runtime claim is made by compilation.

## 5. Protected preparation and exact systemd configuration

```bash
sudo /usr/bin/python3 -I -B "$BUILD/resources.py" "$EVIDENCE" init \
    "$BASE" "$SNAP" "$BUILD/m2.json" "$BUILD/m2-reader" "$BUILD/probe.py"
admin() { sudo /usr/bin/python3 -I -B "$BASE/resources.py" "$EVIDENCE" "$@"; }
root_probe() { sudo /usr/bin/python3 -I -B "$BASE/probe.py" "$@"; }
ctl() {
    sudo /bin/sh -c 'cd "$1" || exit 1; shift; exec /usr/bin/python3 -B -m engine.ingestion.m2_control "$@"' \
        sh "$BASE/code" "$@" --config "$BASE/m2.json"
}
as_ingest() {
    sudo systemd-run --quiet --wait --pipe --collect --expand-environment=no \
        -p User=hids-ingest -p Group=hids-ingest -p SupplementaryGroups=hids-ipc \
        -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' -p 'AmbientCapabilities=' \
        /usr/bin/python3 -I -B "$BASE/probe.py" "$@"
}
as_reader() {
    sudo systemd-run --quiet --wait --pipe --collect --expand-environment=no \
        -p User=hids-journal -p Group=hids-journal \
        -p 'SupplementaryGroups=systemd-journal hids-ipc' \
        -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' -p 'AmbientCapabilities=' \
        /usr/bin/python3 -I -B "$BASE/probe.py" "$@"
}
PREPARED=1
sudo systemctl daemon-reload
admin verify
sudo systemd-analyze verify /run/systemd/system/hids-ingest.socket \
    /run/systemd/system/hids-ingest.service /run/systemd/system/hids-journal.service
sudo systemctl cat hids-ingest.socket hids-ingest.service hids-journal.service | \
    admin save effective-units.txt private
as_reader isolation reader "$JFILES"
as_ingest isolation ingest "$JFILES"
```

The resource helper copies the **unchanged packaging units** reproduced at the end
of this document, exclusively into `/run/systemd/system`. No `enable`, `link`,
installation under `/etc`, or tmpfiles operation is used. Only these exact drop-ins
are generated (shell variables denote this run's concrete absolute paths):

`/run/systemd/system/hids-ingest.service.d/m2-acceptance.conf`:

```ini
[Service]
WorkingDirectory=$BASE/code
ExecStart=
ExecStart=/usr/bin/python3 -B -m engine.ingestion.m2_service --config $BASE/m2.json
ExecStopPost=/usr/bin/python3 -I -B $BASE/probe.py record-exit ingest
StandardError=append:$EVIDENCE/ingest.stderr
```

`/run/systemd/system/hids-journal.service.d/m2-acceptance.conf`:

```ini
[Service]
ExecStart=
ExecStart=$BASE/m2-reader --config $BASE/m2.json
ExecStopPost=/usr/bin/python3 -I -B $BASE/probe.py record-exit reader
StandardError=append:$EVIDENCE/reader.stderr
```

The temporary stop hooks record systemd's actual SERVICE_RESULT/EXIT_CODE/
EXIT_STATUS in the pre-opened private stderr files, under the same service identity.
They do not open the journal, communicate with the main process, read SQLite or
change its behavior. This retains exit evidence even if systemd unloads a completed
unit. The exit-readiness probe waits through `deactivating` while the stop hook runs.
Clean exits require an observed `success/exited/0` marker; intentional crash
requires `signal/killed/KILL`. Missing metadata fails acceptance. The hooks add
small test-only shutdown overhead; this is not a performance benchmark.
See [systemd exit metadata](https://www.freedesktop.org/software/systemd/man/259/systemd.exec.html#%24EXIT_CODE).

No environment socket-activation values are fabricated. `admin verify` checks the
loaded fragment paths, exact effective drop-in lists and all created-file hashes/
inodes/owners/modes, including detection of inherited/global drop-ins. The config
has exactly three keys, root ownership, mode 0644, protected ancestry and a private
0600 archive in `$EVIDENCE/m2.json` **before any collection starts**.

**Expected:** exclusive preparation and both isolation probes pass. Reader cannot
traverse the database directory; ingestion cannot read assessed journal files.
**Stop:** any unexpected file/unit/drop-in, identity, ownership, permission or unit
syntax failure. Partial preparation is retained, not repaired/retried automatically.

## 6. Genuine socket activation and inactive reader authentication

```bash
sudo systemctl start hids-ingest.socket hids-ingest.service
root_probe wait inactive none | admin save initial-status.json private
root_probe runtime-ingest | admin save initial-credentials.txt private
INITIAL=$(as_ingest summary)
python3 -I -B - "$INITIAL" <<'PY'
import json,sys
j=json.loads(sys.argv[1]); assert j['dispositions']==0 and j['state']=='inactive' and j['revision']==0
print('PASS: no pre-activation records')
PY
sudo systemctl start hids-journal.service
root_probe exit-ok
root_probe wait inactive none | admin save inactive-reader-status.json private
as_ingest summary | admin save inactive-database-summary.json private
```

**Expected:** ingestion has the actual systemd FD 3; the helper verifies actual
`LISTEN_PID`, `LISTEN_FDS=1`, service UID/GIDs/groups, empty capability sets including
bounding, NoNewPrivs and exact socket metadata. The inactive reader exits 0 after
its authenticated reconcile is rejected for absent activation. This exercises its
production IPC checks. Code inspection/offline tests establish the journal-open
gate; these observations alone are not syscall tracing proving absence of opens.

Unauthorized activation and DAC checks, as the ordinary console user:

```bash
if (cd "$BASE/code"; python3 -B -m engine.ingestion.m2_control status --config "$BASE/m2.json"); then
    echo 'FAIL: non-root control succeeded' >&2
    false
fi
python3 -I -B - <<'PY'
import socket
for path in ('/run/hids/control.sock','/run/hids/ingest/journal.sock'):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        try: s.connect(path)
        except PermissionError: print('PASS: ordinary-user DAC denial',path)
        else: raise RuntimeError('ordinary user unexpectedly connected')
PY
```

The CLI's own root rejection and kernel DAC denial are separate evidence; neither
alone proves that a non-root peer reached the backend's SO_PEERCRED control check.
Do not loosen permissions to force that negative test.

**Stop:** unexpected access, nonzero inactive-reader exit, pre-activation records,
wrong socket type/ownership/mode or startup failure. Diagnostic logs are root-only
files in `$EVIDENCE`; do not dump the system journal for troubleshooting.

## 7. Explicit authorization, active reader and concurrent lease denial

The interval UUID below is ephemeral authorization identity, **not** the source
UUID. It is generated only when the operator reaches the explicit activation step.

```bash
ACTIVATION_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
printf '%s\n' "$ACTIVATION_ID" | admin save activation-id.txt private
ctl activate --activation-id "$ACTIVATION_ID" | admin save activation-receipt.json private
sudo systemctl start hids-journal.service
root_probe wait running unit | admin save active-status.json private
root_probe runtime | admin save active-credentials.txt private
as_ingest journal-denied "$JFILES" | admin save ingestion-journal-denial.json private
READER_PID=$(systemctl show hids-journal.service -p MainPID --value)
as_reader compete | admin save concurrent-reader-denial.json private
test "$(systemctl show hids-journal.service -p MainPID --value)" = "$READER_PID"
root_probe wait running unit | admin save retained-lease-status.json private
as_ingest summary | admin save initial-boundary-summary.json private
```

**Expected:** state `anchored` or `empty_unanchored`, matching live reader PID,
correct cross-account credentials and no failure. The authenticated second reader
connection must be closed without a progress response; timeout is not accepted as
denial. The first reader retains its PID/lease. Production C++ and ingestion have
both passed their genuine SO_PEERCRED checks; the separate probe also authenticates
the backend. The post-activation ingestion denial probe attempts O_RDONLY opens
of the assessed files, closes any unexpectedly successful FD and fails; it never
reads a byte or invokes the journal API. A rotation/missing path fails the probe
rather than being counted as permission denial. Native journal readability is conclusively demonstrated only by the
subsequent real record. No prior entry is emitted to establish the boundary.

**Stop:** concurrent reader accepted, wrong PID, terminal failure/gap, or readiness
deadline. The failure handler attempts deactivation and owned-unit stop. Do not
reset a cursor or replace the authorized interval to disguise a failure.

## 8. One credential-free localhost SSH connection and correlated retrieval

Only one connection is attempted. `ssh -F /dev/null` excludes user/system client
configuration. A temporary forwarding proxy records its actual source port, boot
ID and monotonic start time; it stores no SSH stream contents. No key/password/
agent authentication is attempted. The server's existing public host key is used
only for this client's temporary trust file. Do not change server configuration.

```bash
verify_ssh_listener
test -r /etc/ssh/ssh_host_ed25519_key.pub
python3 -I -B - "$BUILD/known_hosts" <<'PY'
from pathlib import Path
import stat,sys
p=Path('/etc/ssh/ssh_host_ed25519_key.pub'); info=p.lstat()
assert p.resolve()==p and stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o022
parts=p.read_text().split()
assert len(parts)>=2 and parts[0]=='ssh-ed25519'
with open(sys.argv[1],'x') as f: f.write('127.0.0.1 '+parts[0]+' '+parts[1]+'\n')
PY
BASELINE=$(as_ingest revision)
SSH_RC=0
LC_ALL=C ssh -F /dev/null -p 22 \
    -o "ProxyCommand=/usr/bin/python3 -I -B $BASE/probe.py proxy $BUILD/connection.json" \
    -o "UserKnownHostsFile=$BUILD/known_hosts" -o GlobalKnownHostsFile=/dev/null \
    -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 \
    -o BatchMode=yes -o PreferredAuthentications=none -o IdentityAgent=none \
    -o PubkeyAuthentication=no -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no -o NumberOfPasswordPrompts=0 \
    -o ConnectionAttempts=1 -o ConnectTimeout=5 \
    "$(id -un)"@127.0.0.1 true > "$BUILD/ssh.stdout" 2> "$BUILD/ssh.stderr" || SSH_RC=$?
test "$SSH_RC" = 255
grep -Fq 'Permission denied' "$BUILD/ssh.stderr"
CONNECTION=$(cat "$BUILD/connection.json")
printf '%s\n' "$CONNECTION" | admin save controlled-connection.json private
as_ingest match "$BASELINE" "$CONNECTION" | admin save controlled-event.json private
root_probe wait anchored unit | admin save event-persisted-status.json private
as_ingest summary | admin save event-database-summary.json private
```

**Expected:** expected authentication denial and a retrieved `journal_event` from
the approved emitter pair, current activation, revision after the saved baseline,
same boot, receipt monotonic time after this connection started, and a MESSAGE
containing this exact `127.0.0.1 port <captured source port>`. A table merely being
nonempty does not pass. The helper independently uses production `get_event()` on
a fresh URI read-only connection, validates native cursor identity/contract and
checks event/checkpoint alignment in a consistent read transaction. It prints
identifiers/assertions, not message text. Journal receipt times remain receipt
metadata; activity wall time remains explicitly unestablished.

**Stop:** host-key mismatch, absent listener, unexpected authentication success,
proxy/client error, no correlated SSH message within the bounded observation,
storage rejection/failure or inconsistent checkpoint. Do not retry SSH automatically,
start a server, broaden filters or substitute an older event. The test remains
incomplete if this OpenSSH configuration emits no suitable port-bearing record.

## 9. Immutable duplicate replay and complete state comparison

```bash
sudo systemctl stop hids-journal.service
root_probe exit-ok
root_probe wait anchored none | admin save before-replay-status.json private
as_ingest export "$BASELINE" "$CONNECTION" | admin save replay.jsonl reader
as_ingest fingerprint | admin save before-replay.sha256 private
as_reader replay "$BASE/replay.jsonl" | admin save replay-receipt.json private
root_probe wait anchored none | admin save after-replay-status.json private
as_ingest fingerprint | admin save after-replay.sha256 private
sudo cmp "$EVIDENCE/before-replay.sha256" "$EVIDENCE/after-replay.sha256"
as_ingest state | admin save recovery-baseline.json ingest
```

**Expected:** one authenticated replacement reader lease; completely validated
reconcile response; production `validate_response()` accepts `ack/duplicate` with
the original stored revision. The raw saved envelope is sent unchanged. Fingerprints
cover **all columns** of dispositions, progress (including boundary times), and
activations from explicit read transactions. Gap/interruption rows are excluded
from unchanged comparison because closing the temporary reader lease legitimately
adds an interruption; they remain bounded and reported separately. No journal API
is used by replay, and no historical source entry is requested.

The replay file is root:hids-journal 0640, allowing only the already-authorized
reader role to replay one of its own previously observed records. It receives no
access to ingestion storage. The recovery baseline is root:hids-ingest 0640.

**Stop:** non-duplicate result, failed peer/lease verification, changed stored
content/observation/receipt/checkpoint, conflict, timeout or retrieval bound. Never
edit the event, allocate a new ID or submit a different cursor to make replay pass.

## 10. Reader restart, crash/replacement and ingestion restart

No additional SSH connection is generated. Legitimate later selected records may
arrive; recovery checks append-only preservation rather than assuming a quiet VM.

```bash
sudo systemctl start hids-journal.service
root_probe wait anchored unit | admin save reader-resumed-status.json private
as_ingest check-prefix "$BASE/recovery-baseline.json" | admin save reader-resumed-check.json private
sudo systemctl kill --signal=SIGKILL --kill-whom=main hids-journal.service
root_probe wait anchored none | admin save reader-disconnected-status.json private
root_probe crash-ok | admin save intentional-reader-crash-marker.json private
sudo systemctl show hids-journal.service -p MainPID -p Result -p ExecMainCode -p ExecMainStatus | \
    admin save intentional-reader-crash.txt private
sudo systemctl reset-failed hids-journal.service
sudo systemctl start hids-journal.service
root_probe wait anchored unit | admin save replacement-reader-status.json private
as_ingest check-prefix "$BASE/recovery-baseline.json" | admin save replacement-reader-check.json private
admin stop
root_probe stopped | admin save ingestion-shutdown-check.txt private
sudo systemctl start hids-ingest.socket hids-ingest.service
root_probe wait anchored none | admin save ingestion-restarted-status.json private
sudo systemctl start hids-journal.service
root_probe wait anchored unit | admin save full-restart-status.json private
root_probe runtime | admin save restarted-credentials.txt private
as_ingest check-prefix "$BASE/recovery-baseline.json" | admin save full-restart-check.json private
```

**Expected:** crash is the one intentionally unclean reader exit; status shows its
lease released. Replacement authenticates as a new PID. All original records remain
byte-for-byte identical, activation and boundary fields are unchanged, numeric
revision advances equal the number of new dispositions, and the last cursor aligns.
Restart seeks the saved cursor inside the still-authorized interval; it does not
establish a new tail. Clean ingestion shutdown removes its socket; systemd removes
the control socket. Starting neither auto-starts the reader. Do not call root
control while testing stopped ingestion: a live control socket can activate it.

**Stop:** unexpected gap, reset boundary, changed/lost record, lease displacement,
stale socket, unclean ordinary stop or recovery failure. No automatic socket unlink,
DB repair, checkpoint reset, backfill or background restart is authorized. The crash
exercise requires an anchored event; never restart an empty-unanchored interval.

## 11. Deactivate and verify clean shutdown

```bash
ctl deactivate --activation-id "$ACTIVATION_ID" | admin save deactivation-receipt.json private
root_probe wait revoked none | admin save revoked-status.json private
root_probe exit-ok
sudo systemctl start hids-journal.service
root_probe exit-ok
root_probe wait revoked none | admin save denied-resume-status.json private
as_ingest summary | admin save final-database-summary.json private
admin stop
root_probe stopped | admin save final-shutdown-check.txt private
```

**Expected:** authorization revoked durably; reader cancels and exits 0; a new reader
also exits 0 without resuming collection; both normal service stops exit cleanly,
and both sockets disappear. Cancellation evidence is bounded by the observation
checks, not a hard real-time guarantee under blocked disk/kernel calls.

**Stop:** source still authorized/connected, reader resumes, nonzero normal exit,
lingering endpoint or shutdown deadline. Preserve everything and report incomplete.

## 12. Exact cleanup and failure recovery

Only after the previous checks passed:

```bash
admin verify
admin cleanup
PREPARED=0
trap - ERR EXIT INT TERM HUP
printf 'Runtime exercise finished; review private evidence at %s\n' "$EVIDENCE"
```

`cleanup` first verifies the inventory and loaded unit/drop-in identities, stops
only those owned units, and refuses stale sockets. It then freezes no-follow tree
manifests with source inode/device identities, ownership, POSIX modes, modification
times, sizes and streamed SHA-256 hashes. The runtime tree must match exactly the
created-resource inventory. The database root must be its inventoried original;
its children must be independent private ingestion-owned regular files.

Both archives use the same strategy, regardless of source device numbers:

1. Create an exclusive `.database.staging-*` or `.runtime.staging-*` directory
   **inside `$EVIDENCE`**, on the destination filesystem, without merging anything.
2. Stream-copy into exclusive no-follow files/directories. Apply original ownership,
   modes and modification times only to these newly created copies; never repair
   source permissions. Flush copied files and directories with fsync.
3. Recheck that the entire source is unchanged. Verify the copy's exact directory
   and file inventory, hashes, sizes, ownership, modes and modification times.
4. Atomically publish the verified stage as `database` or `runtime` with native
   no-replace rename between **siblings on the destination filesystem**. Linux uses
   `renameat2(RENAME_NOREPLACE)`; Darwin `renameatx_np(RENAME_EXCL)` exists solely
   for host filesystem regressions. An unavailable/unsupported primitive fails
   closed; no plain replacement-rename fallback is permitted. Sync the parent.
5. Verify both finalized archives again and persist their receipts/manifests in the
   private, bounded, fsynced inventory. **Both complete archives must pass before
   any original file or runtime unit definition is removed.** Copying/verification/
   finalization/receipt failures leave both source trees and unit files intact.
6. Archive the exact owned unit definitions, then perform one last global source/
   archive verification. Remove only individually checked, frozen manifest entries
   using descriptor-relative no-follow operations; never call unrestricted rmtree.
   `rmdir` refuses unexpected remaining objects. Remove only unchanged inventoried
   unit files/directories and the initially absent fixed directories. Reload
   systemd; only then attempt final completion bookkeeping. A private, fsynced
   `completion-unconfirmed` marker is reserved exclusively before setting
   `cleanup_complete=true`; it overrides that flag if a subsequent write fails.
   Completion requires successful inventory write, marker removal, parent fsync
   and a successful helper return. Existing markers are never overwritten/retried.

This also fixes database archival: `/var/lib/hids/m2` is **not assumed** to share a
filesystem with `$EVIDENCE`. Neither original source tree is renamed. Only the
new destination-side stage is renamed. Symlinks, hardlinks, special files, nested
filesystems and source/destination overlap are rejected. Linux extended metadata
(ACLs, capabilities or other xattrs) is refused rather than silently discarded;
these helper-created resources are expected to have plain POSIX metadata. Source
mount points are not removed.

Final copies reside at `$EVIDENCE/database` and `$EVIDENCE/runtime`; the source
runtime tree is removed only after both verified archives exist. Archive file
ownership/modes are preserved, while `$EVIDENCE` remains root:root 0700. Device/
inode/creation-time identities naturally differ in copies; original identities are
retained in receipts. Verification reads may update access times. There is no
merging, recursive wildcard deletion, permission repair or permanent enablement.
`$BUILD` remains private ordinary-user build/client evidence with no journal payload.

Archival is not a transaction spanning filesystems. On failure, clearly named
partial stages or an already-finalized archive may remain for inspection; no
automatic overwrite, stage deletion or retry occurs. If removal itself fails
**after** all archival gates passed, complete verified copies remain and cleanup
stays incomplete; some originals may already have been removed. Preserve remaining
originals, receipts and archives for operator review. A later daemon-reload failure leaves cleanup incomplete. A failure syncing the
final inventory replacement makes completion metadata unconfirmed: the durable
`completion-unconfirmed` marker overrides a possibly visible new flag. The
inventory loader treats an existing marker as incomplete. If the final marker
unlink succeeded but its directory fsync failed, durability is still unconfirmed:
absence of the marker or a visible flag alone never substitutes for successful
helper return. No ambiguous operation is retried. Do not rerun the
numbered sequence blindly or delete an existing target to force a retry.

The private evidence directory remains root:root 0700. Config/source UUID, manifest,
helper/binary identities, complete replay envelope, baseline, status, diagnostics
and database remain available. Do not copy this raw evidence to the shared folder.

**Failure recovery:** do not continue the numbered stages after a failure. The
shell handler attempts revocation and inventory-guarded stop but does not clean up.
If helper initialization failed before `PREPARED=1`, no component was started;
retain the printed BASE/EVIDENCE paths and inspect partial preparation manually.
If a unit/inode/hash changed, the helper refuses to touch it. Copy, verification,
atomic publication or receipt-persistence failures preserve both originals and
leave `cleanup_complete` false. Destination files/stages may be present; they are
never merged or automatically reused. Once the verified-removal phase has begun,
any failure preserves complete archives and remaining originals, without pretending
all original paths still exist. In that case `$BASE/resources.py` may already be
removed, so the shell's best-effort failure handler can itself report a missing
path; owned services were stopped before archival. Inspect the private inventory
and archived helper rather than recreating paths or bypassing its guards.

If cleanup partially fails, retain current paths for operator review; do not run
unrestricted recursive removal or silently repair state. If storage is full,
revocation may remain unconfirmed; stopping owned components prevents further
reads, but is not proof that durable revocation or a gap record committed. No
power-loss or multi-filesystem all-or-nothing deletion guarantee is asserted.

For diagnostics, use only `sudo cat "$EVIDENCE/reader.stderr"`,
`sudo cat "$EVIDENCE/ingest.stderr"` and the captured unit/status files. If stop
itself times out, report that shutdown is unverified; do not claim success or
silently escalate to destructive cleanup. No package/account/logging changes are
part of failure recovery.

## Archival preparation regressions (not live acceptance)

From the canonical repository, as an ordinary host user:

```bash
python3 -B -m unittest discover -s tests/unit -p 'test_m2_runtime_archival.py' -v
```

These use disposable synthetic files, not systemd or journal records. They cover
same-filesystem copies, a simulated EXDEV source-rename barrier, exclusive native
publication collisions, partial/interrupted copies, metadata/content/inventory
mismatches, fsync/finalization/receipt failures, both-source preservation, and
bounded manifest-based removal. A separate real cross-filesystem case uses Linux
`/dev/shm` only if already writable and on a different device; it skips on macOS.
No filesystem is mounted for tests. Native Linux checks are a prerequisite below,
not a macOS pass. Do not modify the validated snapshot to add preparation tests.

## Acceptance report

Record the actual Ubuntu/compiler/libsystemd versions; service UIDs/primary GIDs/
groups/capabilities; socket owners/modes; actual FD-3 inheritance; inactive behavior;
concurrent lease denial; controlled source-port/boot/monotonic match; fresh read-only
retrieval; complete replay fingerprint equality; anchored reader and ingestion
recovery; revocation and clean normal shutdown. Report every failure or unverified
branch. This run does not force rotation/vacuum, empty-journal restart, disk-full or
ACK-loss cases on the live VM; existing offline coverage is distinct from live
observations. No comprehensive/lossless-monitoring or long-running reliability
claim follows. Passing this document's commands is evidence for review, not an
automatic declaration that all M2 acceptance requirements have been met.

## Exact existing base units copied by preparation

These bodies are read from the validated snapshot, not invented replacement units.
The drop-ins above are the only generated changes. No tmpfiles artifact is run.

### hids-ingest.socket

```ini
# Source artifact only; setup/deployment/live use require separate authorization.
[Unit]
Description=HIDS root-only M2 activation control socket

[Socket]
ListenStream=/run/hids/control.sock
SocketUser=root
SocketGroup=root
SocketMode=0600
DirectoryMode=0755
Accept=no
Service=hids-ingest.service
RemoveOnStop=yes
# No Install section: do not enable implicitly.
```

### hids-ingest.service

```ini
# SOURCE ARTIFACT ONLY: not deployed or authorized for live execution.
[Unit]
Description=HIDS M2 isolated event ingestion
Requires=hids-ingest.socket
After=hids-ingest.socket

[Service]
Type=simple
User=hids-ingest
Group=hids-ingest
DynamicUser=no
SupplementaryGroups=hids-ipc
WorkingDirectory=/usr/lib/hids
ExecStart=/usr/bin/python3 -B -m engine.ingestion.m2_service --config /etc/hids/m2.json
Sockets=hids-ingest.socket
Restart=no
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/run/hids/ingest /var/lib/hids/m2
StandardOutput=null
# No journal read grants; protected resources require separate setup approval.
```

### hids-journal.service

```ini
# SOURCE ARTIFACT ONLY: root must activate source before starting this unit.
[Unit]
Description=HIDS M2 authorized journal reader
After=hids-ingest.service
Requires=hids-ingest.service

[Service]
Type=simple
User=hids-journal
Group=hids-journal
DynamicUser=no
SupplementaryGroups=systemd-journal hids-ipc
ExecStart=/usr/lib/hids/m2-reader --config /etc/hids/m2.json
Restart=no
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictAddressFamilies=AF_UNIX
StandardOutput=null
# No Install section: deployment/activation is separately authorized.
```
