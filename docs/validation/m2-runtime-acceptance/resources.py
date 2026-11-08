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
