#!/usr/bin/env python3
"""Small source-snapshot/offline-validation workflow. Python standard library only."""
import argparse
import ctypes.util
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

MANIFEST = 'SOURCE_MANIFEST.json'
DIGEST = 'SOURCE_MANIFEST.sha256'
METADATA = {MANIFEST, DIGEST}
ROOTS = ('collector', 'engine', 'shared', 'tests', 'scripts', 'packaging', 'docs', 'rules', 'api', 'frontend')
SUFFIXES = {'.cpp', '.hpp', '.h', '.py', '.sh', '.md', '.json', '.service', '.socket', '.timer', '.conf', '.MIT', '.tsx', '.ts', '.css', '.html', '.txt', '.in'}
PACKAGING_ARTIFACTS = {'packaging/hids-audit-launcher', 'packaging/hids-dashboard-access', 'packaging/hids-dashboard', 'packaging/hids-sources', 'packaging/hids-browser-prepare'}
SANITIZED_FIXTURES = {'tests/fixtures/audit/structural-exec.log'}
ROOT_FILES = {'AGENTS.md', 'todo.md', 'README.md', 'LICENSE', 'LICENSE.MIT'}
EXCLUDED_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'build', 'dist', 'dist-history', 'dist-setup', 'dist-dashboard'}
HEX = re.compile('[0-9a-f]{64}')
NAME = re.compile('[A-Za-z0-9][A-Za-z0-9._-]{0,95}')


class WorkflowError(RuntimeError):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def unique(prefix):
    return prefix + '-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]


def safe_name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value) or value in ('.', '..'):
        raise WorkflowError('unsafe snapshot/run name')
    return value


def regular(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise WorkflowError('not an independent regular file: ' + str(path))
    return info


def sha(path):
    regular(path)
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path, data, private=False):
    # Creation modes only. Never chmod/chown an existing file or replace it.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                 0o600 if private else 0o644)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


def json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise WorkflowError('duplicate JSON key')
        result[key] = value
    return result


def read_json(path):
    if regular(path).st_size > 8 * 1024 * 1024:
        raise WorkflowError('metadata exceeds 8 MiB bound')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_pairs)


def tree(root):
    """Exact inventory, rejecting links and special files before reading bytes."""
    if Path(root).is_symlink() or not Path(root).is_dir():
        raise WorkflowError('unsafe tree root')
    files, dirs = set(), set()
    for parent, names, leaves in os.walk(root, followlinks=False):
        for name in names:
            path = Path(parent) / name
            if path.is_symlink() or not path.is_dir():
                raise WorkflowError('symlink/special directory: ' + str(path))
            dirs.add(path.relative_to(root).as_posix())
        for name in leaves:
            path = Path(parent) / name
            regular(path)
            files.add(path.relative_to(root).as_posix())
    return files, dirs


def source_files(repo):
    files = []
    for folder in ROOTS:
        start = repo / folder
        if not start.exists() and not start.is_symlink():
            continue
        if start.is_symlink() or not start.is_dir():
            raise WorkflowError('unsafe source directory: ' + folder)
        for parent, dirs, leaves in os.walk(start, followlinks=False):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for name in dirs:
                if (Path(parent) / name).is_symlink():
                    raise WorkflowError('source directory symlink')
            for name in leaves:
                path = Path(parent) / name
                if path.is_symlink():
                    raise WorkflowError('source file symlink')
                if name.startswith('.') or (path.suffix not in SUFFIXES and path.relative_to(repo).as_posix() not in SANITIZED_FIXTURES | PACKAGING_ARTIFACTS):
                    continue
                if regular(path).st_size > 32 * 1024 * 1024:
                    raise WorkflowError('source file exceeds 32 MiB bound: ' + str(path))
                files.append(path.relative_to(repo).as_posix())
    for name in ROOT_FILES:
        path = repo / name
        if path.exists() or path.is_symlink():
            regular(path)
            files.append(name)
    if not files:
        raise WorkflowError('no source files selected')
    return sorted(files)


def verify(snapshot, expected_digest=None):
    snapshot = Path(snapshot)
    # Inventory check first also catches symlinked manifest files/parents.
    actual, directories = tree(snapshot)
    manifest = read_json(snapshot / MANIFEST)
    if set(manifest) != {'manifest_version', 'snapshot_id', 'created_utc', 'files'} or manifest['manifest_version'] != 1 or type(manifest['manifest_version']) is not int:
        raise WorkflowError('unsupported manifest')
    safe_name(manifest['snapshot_id'])
    if snapshot.name != manifest['snapshot_id']:
        raise WorkflowError('snapshot directory/name mismatch')
    files = manifest['files']
    if type(files) is not dict or not files or len(files) > 10000:
        raise WorkflowError('invalid manifest inventory')
    expected_dirs = set()
    for name, digest in files.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or str(rel) != name or '\\' in name or name in METADATA or any(ord(c)<32 or ord(c)==127 for c in name) or not HEX.fullmatch(str(digest)):
            raise WorkflowError('unsafe manifest entry')
        expected_dirs.update(str(p) for p in rel.parents if str(p) != '.')
    if actual != set(files) | METADATA or directories != expected_dirs:
        raise WorkflowError('missing or unexpected snapshot inventory')
    digest = sha(snapshot / MANIFEST)
    checksum = (snapshot / DIGEST).read_text(encoding='ascii')
    if checksum != digest + '\n' or (expected_digest is not None and digest != expected_digest):
        raise WorkflowError('manifest SHA-256 mismatch')
    for name, wanted in files.items():
        if sha(snapshot / name) != wanted:
            raise WorkflowError('source SHA-256 mismatch: ' + name)
    return manifest, digest


def private_dir(path):
    """Create one level at a time; never follow links or repair permissions."""
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass  # A concurrent creator must meet the same checks.
            info = current.lstat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise WorkflowError('private output directory required: ' + str(current))
        if not stat.S_ISDIR(info.st_mode):
            raise WorkflowError('directory symlink/special path rejected: ' + str(current))
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise WorkflowError('private output directory required: ' + str(path))
    return path


def private_state(path):
    """Check existing private descendants before any state is consumed."""
    path = private_dir(path)
    for parent, dirs, files in os.walk(path, followlinks=False):
        for name in dirs:
            private_dir(Path(parent) / name)
        for name in files:
            if (Path(parent) / name).is_symlink():
                raise WorkflowError('symlink in private state: ' + str(Path(parent) / name))
    return path


def create_snapshot(repo, state, name=None):
    repo, state = Path(repo).resolve(), Path(os.path.abspath(state))
    if state == repo or repo in state.parents:
        raise WorkflowError('snapshot state must be outside canonical repository')
    private_state(state)
    parent = private_dir(state / 'snapshots')
    name = safe_name(name or unique('hids-src'))
    destination = parent / name
    destination.mkdir(mode=0o700, exist_ok=False)  # Reservation; never replace, even empty.
    files = source_files(repo)
    hashes = {name: sha(repo / name) for name in files}
    for name in files:
        target = destination / name
        private_dir(target.parent)
        # copyfile uses no metadata/permission mutation; destination is exclusive.
        with (repo / name).open('rb') as source:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, 'wb') as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
        if sha(target) != hashes[name] or sha(repo / name) != hashes[name]:
            raise WorkflowError('canonical source changed during snapshot: ' + name)
    if source_files(repo) != files or any(sha(repo / name) != hashes[name] for name in files):
        raise WorkflowError('canonical inventory/content changed during snapshot')
    manifest = {'manifest_version': 1, 'snapshot_id': destination.name, 'created_utc': utc(), 'files': hashes}
    raw = json_bytes(manifest)
    write_new(destination / MANIFEST, raw)
    digest = hashlib.sha256(raw).hexdigest()
    write_new(destination / DIGEST, (digest + '\n').encode('ascii'))
    verify(destination, digest)
    receipts = private_dir(state / 'receipts')
    write_new(receipts / (destination.name + '.json'), json_bytes({'snapshot_id': destination.name, 'manifest_sha256': digest}), private=True)
    return destination, digest, len(files)


def share_path(explicit=None):
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_dir() or candidate.is_symlink():
            raise WorkflowError('shared folder unavailable: ' + str(candidate))
        return candidate.resolve()
    candidates = [Path.home() / part / 'CCDC-Transfer' for part in ('Desktop', 'Downloads', 'Documents')]
    if platform.system() == 'Linux':
        candidates.append(Path('/mnt/ccdc-transfer'))
    found = [p.resolve() for p in candidates if p.is_dir() and not p.is_symlink()]
    if len(set(found)) != 1:
        raise WorkflowError('locate one existing CCDC-Transfer folder or set --share / HIDS_TRANSFER_DIR')
    return found[0]


def pinned_snapshot(state, name=None):
    state = private_state(state)
    if name:
        path = state / 'snapshots' / safe_name(name)
    else:
        parent = state / 'snapshots'
        choices = sorted(parent.iterdir()) if parent.is_dir() else []
        if not choices:
            raise WorkflowError('no local snapshot; run snapshot first')
        path = choices[-1]
    receipt = read_json(state / 'receipts' / (path.name + '.json'))
    if set(receipt) != {'snapshot_id', 'manifest_sha256'} or receipt['snapshot_id'] != path.name:
        raise WorkflowError('invalid local snapshot receipt')
    verify(path, receipt['manifest_sha256'])
    return path, receipt['manifest_sha256']


def share_subdir(root, *parts):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise WorkflowError('unsafe shared-folder root')
    current = root
    for part in parts:
        current = current / safe_name(part)
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise WorkflowError('unsafe shared-folder directory')
        else:
            current.mkdir(exist_ok=False)
    return current


def transfer(state, share, name=None):
    source, digest = pinned_snapshot(state, name)
    manifest, _ = verify(source, digest)
    parent = share_subdir(share, 'collector-validation', 'snapshots')
    destination = parent / source.name
    destination.mkdir(mode=0o755, exist_ok=False)
    for name in sorted(set(manifest['files']) | METADATA):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with (source / name).open('rb') as stream:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, 'wb') as output:
                shutil.copyfileobj(stream, output, 1024 * 1024)
    verify(destination, digest)
    verify(source, digest)
    receipts = private_dir(Path(state) / 'transfers')
    write_new(receipts / (unique('transfer') + '.json'), json_bytes({'snapshot_id': source.name, 'manifest_sha256': digest, 'destination': str(destination), 'verified_utc': utc()}), private=True)
    return destination, digest, len(manifest['files']) + 2


# Explicit external-command wrappers report their own statuses. ERR captures
# unwrapped failures; EXIT records only the aggregate shell status. DEBUG cannot
# reliably attribute statuses across control constructs, so it is not used.
TRACE_ENV = r'''if [[ -n ${HIDS_DEV_TRACE_OWNER:-} ]]; then return 0; fi
export HIDS_DEV_TRACE_OWNER=$$
exec 19>"$HIDS_DEV_TRACE"
printf 'Validation shell identity: UID=%s EUID=%s GID=%s EGID=%s\n' "$UID" "$EUID" "$(id -rg)" "$(id -g)" >&2
hids_run() {
    local code label
    printf -v label '%q ' "$@"
    if "$@"; then code=0; else code=$?; fi
    printf '%s\0%s\0' "$code" "${label% }" >&19
    return "$code"
}
trap 'printf "%s\0%s\0" "$?" "$BASH_COMMAND" >&19' ERR
trap 'printf "%s\0%s\0" "$?" "[shell aggregate exit]" >&19' EXIT
'''


def trace_records(path):
    if not Path(path).exists():
        return []
    if regular(path).st_size > 8*1024*1024:
        raise WorkflowError('command trace too large')
    parts = Path(path).read_bytes().split(b'\0')
    records = []
    for index in range(0, len(parts)-1, 2):
        try:
            code = int(parts[index])
            command = parts[index+1].decode('utf-8', errors='replace')
        except (ValueError, IndexError) as exc:
            raise WorkflowError('invalid command trace') from exc
        if command.startswith('__hids_') or command.startswith('trap '):
            continue
        records.append({'command': command, 'exit_code': code})
    return records


def run_phase(directory, label, command, repo, env=None, trace=False):
    stdout, stderr = directory / (label+'.stdout.log'), directory / (label+'.stderr.log')
    write_new(stdout, b'', private=True)
    write_new(stderr, b'', private=True)
    environment = os.environ.copy()
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    if env:
        environment.update(env)
    environment.pop('BASH_ENV', None)
    environment.pop('HIDS_DEV_TRACE_OWNER', None)
    trace_path = directory / (label+'.commands.bin')
    if trace:
        write_new(trace_path,b'',private=True)
        bootstrap = directory / (label+'.bash-env')
        write_new(bootstrap, TRACE_ENV.encode('ascii'), private=True)
        environment['BASH_ENV'] = str(bootstrap)
        environment['HIDS_DEV_TRACE'] = str(trace_path)
    try:
        with stdout.open('ab') as out, stderr.open('ab') as err:
            process = subprocess.run(command, cwd=repo, env=environment, stdout=out, stderr=err)
        code = process.returncode
    except OSError as exc:
        with stderr.open('ab') as err:
            err.write(('unable to execute: '+str(exc)+'\n').encode())
        code = 127
    if stdout.stat().st_size>32*1024*1024 or stderr.stat().st_size>32*1024*1024:
        raise WorkflowError('log exceeds 32 MiB parse bound; private files retained')
    logs = stderr.read_text(errors='replace') + '\n' + stdout.read_text(errors='replace')
    details = re.findall(r"^(test_[^\n]+?) \.\.\. skipped (.+)$", logs, re.MULTILINE)
    skips = sum(int(n) for n in re.findall(r'\bOK \(skipped=(\d+)\)', logs))
    return {'name': label, 'command': command, 'exit_code': code,
            'stdout_file': stdout.name, 'stderr_file': stderr.name,
            'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
            'skipped_count': max(skips, len(details)),
            'skipped_tests': [{'test': test, 'reason': reason} for test, reason in details],
            'commands': trace_records(trace_path) if trace else []}


def environment_info():
    import sqlite3
    release = {}
    if platform.system() == 'Linux' and Path('/etc/os-release').is_file():
        for line in Path('/etc/os-release').read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                release[key] = value.strip('"')
    return {'system': platform.system(), 'architecture': platform.machine(),
            'kernel': platform.release(), 'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
            'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid(), 'egid': os.getegid(),
            'distribution': release.get('ID'), 'distribution_version': release.get('VERSION_ID')}


def ubuntu_preflight():
    import sqlite3
    release = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            release[k] = v.strip('"')
    missing = []
    if platform.system() != 'Linux' or platform.machine() != 'aarch64' or release.get('ID') != 'ubuntu' or release.get('VERSION_ID') != '26.04':
        missing.append('requires Ubuntu 26.04 ARM64')
    if os.getuid() == 0 or os.getuid() != os.geteuid() or os.getgid() != os.getegid():
        missing.append('requires matching ordinary-user credentials')
    if sys.version_info < (3,10) or sqlite3.sqlite_version_info < (3,22,0):
        missing.append('requires Python >=3.10 and SQLite >=3.22.0')
    compiler = shutil.which(os.environ.get('CXX', 'c++'))
    if not compiler:
        missing.append('C++ compiler unavailable')
    if not Path('/usr/include/systemd/sd-journal.h').is_file() or not ctypes.util.find_library('systemd'):
        missing.append('libsystemd development header/runtime unavailable')
    if not shutil.which('bash'):
        missing.append('bash unavailable')
    return compiler, missing


def new_run(output):
    parent = private_dir(output)
    return private_dir(parent / unique('validation'))


def publish_summary(report, directory, share):
    parent = share_subdir(share, 'collector-validation', 'reports')
    target = parent / safe_name(report['run_id'])
    target.mkdir(exist_ok=False)
    raw = (directory / 'validation.json').read_bytes()
    write_new(target / 'validation.json', raw, private=True)
    write_new(target / 'validation.sha256', (hashlib.sha256(raw).hexdigest()+'\n').encode('ascii'), private=True)
    if sha(target / 'validation.json') != hashlib.sha256(raw).hexdigest():
        raise WorkflowError('summary transfer mismatch')
    return target


def validate_run(repo, output, *, ubuntu, expected=None, sanitize=False, preflight=None, publish=None):
    """Private test seams permit fake runners; public Ubuntu CLI cannot bypass preflight."""
    repo = Path(repo).resolve()
    output = Path(os.path.abspath(output))
    if output==repo or repo in output.parents:
        raise WorkflowError('validation output must be outside source tree')
    shares = [Path(publish).resolve()] if publish else []
    if repo.parent.name=='snapshots' and repo.parent.parent.name=='collector-validation':
        shares.append(repo.parent.parent.parent)
    if any(output==share or share in output.parents for share in shares):
        raise WorkflowError('full validation logs must stay off the shared folder')
    directory = new_run(output)
    report = {'report_version': 1, 'run_id': directory.name, 'started_utc': utc(),
              'finished_utc': None, 'snapshot_id': None, 'source_manifest_sha256': None,
              'scope': 'ubuntu_offline' if ubuntu else 'local_offline',
              'status': 'blocked', 'phases': [], 'error': None, 'environment': {},
              'private_results_directory': str(directory)}
    code = 1
    try:
        if ubuntu:
            report['snapshot_id'] = safe_name(repo.name)
            report['source_manifest_sha256'] = sha(repo / MANIFEST)
            manifest, digest = verify(repo, expected)
            report['snapshot_id'] = manifest['snapshot_id']
            report['source_manifest_sha256'] = digest
        report['environment'] = environment_info()
        compiler = shutil.which(os.environ.get('CXX','c++'))
        if ubuntu:
            compiler, missing = (preflight or ubuntu_preflight)()
            if missing:
                raise WorkflowError('missing prerequisites: '+ '; '.join(missing))
            probe = directory / 'systemd_probe.cpp'
            write_new(probe, b'#include <systemd/sd-journal.h>\nint main(){auto volatile f=&sd_journal_close;return f==nullptr;}\n', private=True)
            result = run_phase(directory, 'dependency_compile', [compiler, '-std=c++20','-Wall','-Wextra','-Wpedantic','-Werror',str(probe),'-lsystemd','-o',str(directory/'dependency_probe')], repo)
            report['phases'].append(result)
            if result['exit_code']:
                report['status'] = 'failed'
                raise WorkflowError('development dependency compile/link probe failed')
        if not compiler:
            raise WorkflowError('C++ compiler unavailable')
        command = ['bash', str(repo/'tests/integration/validate_m2_offline.sh')]
        if sanitize:
            command.append('--sanitize')
        result = run_phase(directory, 'offline_regressions', command, repo, trace=True)
        report['phases'].append(result)
        if result['exit_code']:
            report['status'] = 'failed'
        else:
            automation = repo/'tests/unit/test_dev_workflow.py'
            if automation.is_file():
                report['phases'].append(run_phase(directory, 'workflow_tests', [sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test_dev_workflow.py','-v'], repo))
            failed = any(p['exit_code'] for p in report['phases'])
            skipped = sum(p['skipped_count'] for p in report['phases'])
            report['status'] = 'failed' if failed else ('incomplete' if ubuntu and skipped else 'passed_with_skips' if skipped else 'passed')
            code = 1 if failed or (ubuntu and skipped) else 0
        if ubuntu:
            verify(repo, report['source_manifest_sha256'])  # Runner must not alter source.
    except Exception as exc:
        report['error'] = str(exc)
        if report['status'] not in ('failed',):
            report['status'] = 'blocked'
        code = 1
    report['finished_utc'] = utc()
    write_new(directory/'validation.json', json_bytes(report), private=True)
    write_new(directory/'validation.sha256', (sha(directory/'validation.json')+'\n').encode('ascii'), private=True)
    published = None
    if publish:
        try:
            published = publish_summary(report, directory, publish)
        except Exception as exc:
            print('Summary publication failed; private evidence retained: '+str(exc), file=sys.stderr)
            code = code or 73
    return report, directory, code, published


def validate_report(path, state, checksum=None):
    checksum = checksum or path.parent/'validation.sha256'
    regular(checksum)
    if checksum.read_text(encoding='ascii') != sha(path)+'\n':
        raise WorkflowError('validation summary hash mismatch')
    obj = read_json(path)
    required = {'report_version','run_id','started_utc','finished_utc','snapshot_id','source_manifest_sha256','scope','status','phases','error','environment','private_results_directory'}
    if set(obj) != required or obj['report_version'] != 1 or type(obj['report_version']) is not int or obj['scope'] != 'ubuntu_offline':
        raise WorkflowError('unsupported validation summary')
    safe_name(obj['run_id'])
    safe_name(obj['snapshot_id'])
    _, wanted = pinned_snapshot(state, obj['snapshot_id'])
    if obj['source_manifest_sha256'] != wanted:
        raise WorkflowError('summary does not match trusted local snapshot')
    if type(obj['environment']) is not dict or type(obj['private_results_directory']) is not str or not obj['private_results_directory'].startswith('/') or any(ord(c)<32 or ord(c)==127 for c in obj['private_results_directory']):
        raise WorkflowError('invalid report environment/log location')
    if obj['status'] not in ('passed','incomplete','failed','blocked') or type(obj['phases']) is not list:
        raise WorkflowError('invalid validation status')
    names = set()
    for phase in obj['phases']:
        if type(phase) is not dict or type(phase.get('exit_code')) is not int or type(phase.get('skipped_count')) is not int or phase['skipped_count'] < 0:
            raise WorkflowError('invalid phase result')
        name = phase.get('name')
        if name not in ('dependency_compile','offline_regressions','workflow_tests') or name in names:
            raise WorkflowError('unknown/duplicate validation phase')
        names.add(name)
        if phase.get('stdout_file')!=name+'.stdout.log' or phase.get('stderr_file')!=name+'.stderr.log' or not HEX.fullmatch(str(phase.get('stdout_sha256'))) or not HEX.fullmatch(str(phase.get('stderr_sha256'))):
            raise WorkflowError('invalid phase log references')
    if obj['status']=='passed' and any(obj['environment'].get(k)!=v for k,v in (('system','Linux'),('architecture','aarch64'),('distribution','ubuntu'),('distribution_version','26.04'))):
        raise WorkflowError('passing report does not establish target Ubuntu environment')
    if obj['status'] == 'passed' and (obj['error'] is not None or not obj['phases'] or not {'dependency_compile','offline_regressions'}.issubset({p['name'] for p in obj['phases']}) or any(p['exit_code'] or p['skipped_count'] for p in obj['phases'])):
        raise WorkflowError('contradictory passing summary')
    return obj


def import_reports(state, share):
    folder = Path(share)
    for part in ('collector-validation','reports'):
        folder = folder/part
        if folder.is_symlink():
            raise WorkflowError('symlinked report path')
    candidates = sorted(folder.glob('*/validation.json')) if folder.is_dir() else []
    if not candidates:
        raise WorkflowError('no Ubuntu summaries available; run validate_ubuntu.sh from a transferred snapshot or copy its reviewed summary to collector-validation/reports/<run-id>/')
    destination = private_dir(Path(state)/'reports')
    reports = []
    for path in candidates:
        if path.parent.is_symlink():
            raise WorkflowError('symlinked report directory')
        report = validate_report(path, state)
        target = destination/(report['run_id']+'.json')
        if target.exists():
            if sha(target) != sha(path):
                raise WorkflowError('conflicting imported report ID')
        else:
            write_new(target, path.read_bytes(), private=True)
        checksum = target.with_suffix('.sha256')
        if checksum.exists():
            regular(checksum)
            if checksum.read_text(encoding='ascii') != sha(target)+'\n':
                raise WorkflowError('imported report checksum mismatch')
        else:
            write_new(checksum,(sha(target)+'\n').encode('ascii'),private=True)
        reports.append(report)
    return reports


def summarize(report):
    skips = sum(p['skipped_count'] for p in report['phases'])
    return '{}: {} ({} phases, {} skipped); source {}'.format(report['run_id'],report['status'],len(report['phases']),skips,report.get('snapshot_id') or 'canonical/local')


def main(argv=None):
    default_repo = Path(__file__).resolve().parents[1]
    default_state = Path(os.environ.get('HIDS_DEV_STATE', str(Path.home()/'.local/state/hids-dev'))).expanduser()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--repo', type=Path, default=default_repo)
    common.add_argument('--state-dir', type=Path, default=default_state)
    common.add_argument('--share', default=os.environ.get('HIDS_TRANSFER_DIR'))
    parser = argparse.ArgumentParser(prog='hids-dev', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('test','snapshot','transfer','status','report','_validate'):
        sub = commands.add_parser(name, parents=[common])
        if name in ('snapshot','transfer'):
            sub.add_argument('--name')
        if name in ('test','_validate'):
            sub.add_argument('--sanitize', action='store_true')
        if name == '_validate':
            sub.add_argument('--output', type=Path, default=Path('/tmp/hids-dev-results'))
            sub.add_argument('--expected-manifest')
            sub.add_argument('--no-publish', action='store_true')
    args = parser.parse_args(argv)
    try:
        if os.getuid() == 0:
            raise WorkflowError('run as an ordinary user; never sudo')
        state = Path(os.path.abspath(args.state_dir.expanduser()))
        repo = args.repo.expanduser().resolve()
        if state==repo or repo in state.parents:
            raise WorkflowError('development state must be outside canonical source')
        if args.command != '_validate':
            private_state(state)
        if args.command == 'snapshot':
            path, digest, count = create_snapshot(repo, state, args.name)
            print('Snapshot:', path, '\nSource files:', count, '\nManifest SHA-256:', digest)
        elif args.command == 'transfer':
            path, digest, count = transfer(state, share_path(args.share), args.name)
            print('Verified destination:', path, '\nFiles including manifest:', count, '\nManifest SHA-256:', digest)
        elif args.command == 'report':
            for report in import_reports(state, share_path(args.share)):
                print(summarize(report))
                if report['error'] is not None:
                    print('  Detail:',json.dumps(report['error'],ensure_ascii=True))
                for phase in report['phases']:
                    if phase['exit_code']:
                        print('  Failed phase:',phase['name'],'exit',phase['exit_code'])
                print('Full stdout/stderr remain private on Ubuntu at', report['private_results_directory'])
        elif args.command == 'status':
            parent = state/'snapshots'
            if not parent.is_dir():
                print('No snapshots.')
            else:
                for path in sorted(parent.iterdir()):
                    try:
                        _, digest = pinned_snapshot(state, path.name)
                        print(path.name, 'verified', digest)
                    except Exception as exc:
                        print(path.name, 'INVALID:', str(exc))
            for parent in (state/'reports', state/'runs'):
                pattern = '*.json' if parent.name == 'reports' else '*/validation.json'
                for path in sorted(parent.glob(pattern)):
                    report = validate_report(path,state,path.with_suffix('.sha256')) if parent.name=='reports' else read_json(path)
                    print(summarize(report))
        else:
            ubuntu = args.command == '_validate'
            publication = None
            if ubuntu and not args.no_publish:
                if args.share:
                    publication = share_path(args.share)
                elif repo.parent.name == 'snapshots' and repo.parent.parent.name == 'collector-validation':
                    publication = repo.parent.parent.parent
            report, directory, code, published = validate_run(repo, args.output if ubuntu else state/'runs', ubuntu=ubuntu,
                expected=args.expected_manifest if ubuntu else None, sanitize=args.sanitize, publish=publication)
            print(summarize(report))
            print('Private logs/report:', directory)
            if published:
                print('Published summary only:', published)
            return code
        return 0
    except (OSError, ValueError, WorkflowError) as exc:
        print('hids-dev:', str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
