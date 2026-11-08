"""Linux offline-test launcher only; never changes the parent or service policy."""
import json
import os
from pathlib import Path
import shutil
import sys
import unittest

WAKE_ALARM = 1 << 35
FIELDS = {'Uid', 'Gid', 'Groups', 'CapEff', 'CapPrm', 'CapInh', 'CapAmb',
          'CapBnd', 'NoNewPrivs'}


def credentials():
    with Path('/proc/self/status').open() as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise PermissionError('oversized_capability_status')
    result = {}
    for line in raw.splitlines():
        name, _, value = line.partition(':')
        if name not in FIELDS:
            continue
        if name in result:
            raise PermissionError('duplicate_capability_status')
        parts = value.split()
        if name in ('Uid', 'Gid', 'Groups'):
            result[name] = sorted(map(int, parts)) if name == 'Groups' else list(map(int, parts))
        else:
            if len(parts) != 1:
                raise PermissionError('invalid_capability_status')
            result[name] = int(parts[0], 16 if name.startswith('Cap') else 10)
    validate_shape(result)
    if (tuple(result['Uid'][:3]) != os.getresuid() or
            tuple(result['Gid'][:3]) != os.getresgid() or
            result['Groups'] != sorted(os.getgroups())):
        raise PermissionError('identity_status_mismatch')
    return result


def validate_shape(value):
    if type(value) is not dict or set(value) != FIELDS:
        raise PermissionError('capability_status_unavailable')
    for name in ('Uid', 'Gid', 'Groups'):
        items = value[name]
        if type(items) is not list or any(type(x) is not int or x < 0 for x in items):
            raise PermissionError('invalid_identity_status')
        if name != 'Groups' and (len(items) != 4 or items[0] == 0 or len(set(items)) != 1):
            raise PermissionError('non_root_matching_identity_required')
    if value['Groups'] != sorted(set(value['Groups'])):
        raise PermissionError('invalid_group_status')
    for name in FIELDS - {'Uid', 'Gid', 'Groups'}:
        if type(value[name]) is not int or not 0 <= value[name] < 1 << 64:
            raise PermissionError('invalid_capability_status')
    if value['NoNewPrivs'] not in (0, 1):
        raise PermissionError('invalid_no_new_privs')


def verify_before(value):
    validate_shape(value)
    if any(value[k] for k in ('CapEff', 'CapPrm', 'CapAmb')) or value['CapInh'] not in (0, WAKE_ALARM):
        raise PermissionError('unexpected_prelaunch_capabilities')


def verify_after(original, current):
    verify_before(original)
    validate_shape(current)
    if any(current[k] != original[k] for k in ('Uid', 'Gid', 'Groups', 'CapBnd')):
        raise PermissionError('launch_identity_or_bounding_set_changed')
    if any(current[k] for k in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb')) or current['NoNewPrivs'] != 1:
        raise PermissionError('launch_capability_postcondition_failed')


def run_tests():
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    sys.path.insert(0, str(root))
    # No exec/fork between postcondition verification and discovery: these tests
    # execute in the very interpreter whose credentials were just verified.
    producer = os.environ.get('HIDS_M1_PRODUCER', '')
    if not producer or not Path(producer).is_file():
        raise FileNotFoundError('compiled_m1_producer_required')
    suite = unittest.defaultTestLoader.discover(str(root/'tests/integration'),
                                              pattern='test_m1_integration.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    # A successful empty/skipped discovery is not Ubuntu acceptance.
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 12
                     and not result.skipped else 1)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if sys.platform != 'linux':
            raise PermissionError('linux_launcher_required')
        if not argv:
            before = credentials()
            verify_before(before)
            executable = shutil.which('setpriv')
            if not executable:
                raise FileNotFoundError('setpriv_required_no_fallback')
            print('M1 launch before:', json.dumps(before, sort_keys=True), flush=True)
            os.execv(executable, [executable, '--inh-caps=-all', '--no-new-privs',
                                 sys.executable, '-B', str(Path(__file__).resolve()),
                                 '--post', json.dumps(before, separators=(',', ':'))])
            raise RuntimeError('exec_returned_without_replacement')
        if len(argv) != 2 or argv[0] != '--post' or len(argv[1]) > 4096:
            raise ValueError('invalid_launcher_arguments')
        original = json.loads(argv[1])
        after = credentials()
        verify_after(original, after)
        print('M1 launch verified:', json.dumps(after, sort_keys=True), flush=True)
        run_tests()
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print('M1 capability launch failed:', str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
