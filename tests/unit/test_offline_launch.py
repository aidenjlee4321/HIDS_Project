"""Offline launcher policy tests; simulated credentials never grant capabilities."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

FILE = Path(__file__).resolve().parents[1]/'integration/m1_capability_launcher.py'
SPEC = importlib.util.spec_from_file_location('m1_capability_launcher', FILE)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(Uid=[1000]*4, Gid=[1000]*4, Groups=[20, 1000],
                           CapEff=0, CapPrm=0, CapInh=launcher.WAKE_ALARM,
                           CapAmb=0, CapBnd=(1 << 41)-1, NoNewPrivs=0)
        self.after = dict(self.before, CapInh=0, NoNewPrivs=1)

    def test_observed_inheritable_and_empty_are_accepted(self):
        for inherited in (launcher.WAKE_ALARM, 0):
            before = dict(self.before, CapInh=inherited)
            launcher.verify_before(before)
            launcher.verify_after(before, self.after)

    def test_unexpected_prelaunch_capabilities_fail(self):
        for name, value in [('CapEff', 1), ('CapPrm', 1), ('CapAmb', 1),
                            ('CapInh', 1), ('CapInh', launcher.WAKE_ALARM | 1)]:
            with self.subTest(name=name, value=value), self.assertRaises(PermissionError):
                launcher.verify_before(dict(self.before, **{name: value}))

    def test_nonzero_matching_real_effective_saved_filesystem_identity(self):
        for name in ('Uid', 'Gid'):
            for index in range(4):
                bad = copy.deepcopy(self.before); bad[name][index] = 0
                with self.subTest(name=name, index=index), self.assertRaises(PermissionError):
                    launcher.verify_before(bad)
        for name in ('Uid', 'Gid'):
            with self.subTest(name=name), self.assertRaises(PermissionError):
                launcher.verify_after(self.before, dict(self.after, **{name: [1001]*4}))

    def test_supplementary_groups_must_be_preserved(self):
        with self.assertRaises(PermissionError):
            launcher.verify_after(self.before, dict(self.after, Groups=[1000]))

    def test_every_capability_postcondition_and_no_new_privs(self):
        for name in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb'):
            with self.subTest(name=name), self.assertRaises(PermissionError):
                launcher.verify_after(self.before, dict(self.after, **{name: 1}))
        with self.assertRaises(PermissionError):
            launcher.verify_after(self.before, dict(self.after, NoNewPrivs=0))

    def test_bounding_set_unchanged(self):
        with self.assertRaises(PermissionError):
            launcher.verify_after(self.before, dict(self.after, CapBnd=0))

    def test_missing_or_malformed_metadata_fails(self):
        for name in self.before:
            bad = dict(self.before); del bad[name]
            with self.subTest(name=name), self.assertRaises(PermissionError):
                launcher.verify_before(bad)
        with self.assertRaises(PermissionError):
            launcher.verify_before(dict(self.before, CapInh=True))

    def test_exec_exact_options_and_immutable_identity(self):
        class Replaced(BaseException):
            pass
        for inherited in (0, launcher.WAKE_ALARM):
            before = dict(self.before, CapInh=inherited)
            original = copy.deepcopy(before)
            with patch.object(launcher.sys, 'platform', 'linux'), \
                    patch.object(launcher, 'credentials', return_value=before), \
                    patch.object(launcher.shutil, 'which', return_value='/usr/bin/setpriv'), \
                    patch.object(launcher.os, 'execv', side_effect=Replaced) as execute, \
                    patch('sys.stdout', new_callable=io.StringIO):
                with self.assertRaises(Replaced): launcher.main([])
            path, argv = execute.call_args.args
            self.assertEqual(path, '/usr/bin/setpriv')
            self.assertEqual(argv[:3], [path, '--inh-caps=-all', '--no-new-privs'])
            self.assertEqual(json.loads(argv[-1]), original)
            self.assertEqual(before, original)
            self.assertNotIn('--bounding-set', ' '.join(argv))

    def test_missing_setpriv_and_failed_execution_do_not_run_tests(self):
        for executable in (None, '/usr/bin/setpriv'):
            with patch.object(launcher.sys, 'platform', 'linux'), \
                    patch.object(launcher, 'credentials', return_value=self.before), \
                    patch.object(launcher.shutil, 'which', return_value=executable), \
                    patch.object(launcher.os, 'execv', side_effect=OSError('exec failure')) as execute, \
                    patch.object(launcher, 'run_tests') as tests, \
                    patch('sys.stdout', new_callable=io.StringIO), \
                    patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(launcher.main([]), 1)
                self.assertEqual(execute.call_count, int(executable is not None))
                tests.assert_not_called()

    def test_post_verification_precedes_tests_in_same_process(self):
        for current, success in ((self.after, True), (self.before, False)):
            pid = os.getpid()
            with patch.object(launcher.sys, 'platform', 'linux'), \
                    patch.object(launcher, 'credentials', return_value=current), \
                    patch.object(launcher, 'run_tests', side_effect=lambda: self.assertEqual(os.getpid(), pid)) as tests, \
                    patch.object(launcher.os, 'execv') as execute, \
                    patch('sys.stdout', new_callable=io.StringIO), \
                    patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(launcher.main(['--post', json.dumps(self.before)]), 0 if success else 1)
                self.assertEqual(tests.call_count, int(success))
                execute.assert_not_called()

    def test_proc_metadata_matches_kernel_identity_calls(self):
        raw = '\n'.join(k+': '+(' '.join(map(str, v)) if isinstance(v, list)
                                else format(v, 'x') if k.startswith('Cap') else str(v))
                        for k, v in self.before.items())
        with patch.object(Path, 'open', return_value=io.StringIO(raw)), \
                patch.object(launcher.os, 'getresuid', return_value=(1000,)*3, create=True), \
                patch.object(launcher.os, 'getresgid', return_value=(1000,)*3, create=True), \
                patch.object(launcher.os, 'getgroups', return_value=[1000, 20]):
            self.assertEqual(launcher.credentials(), self.before)

    def test_production_capability_rejection_is_preserved(self):
        from engine.ingestion.m1_security import private_directory
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder).resolve()
            for name in ('CapEff', 'CapPrm', 'CapInh'):
                raw = '\n'.join(k+': '+format(launcher.WAKE_ALARM if k == name else 0, 'x')
                                for k in ('CapEff', 'CapPrm', 'CapInh'))
                with self.subTest(name=name), patch('engine.ingestion.m1_security.sys.platform', 'linux'), \
                        patch.object(Path, 'read_text', return_value=raw), \
                        self.assertRaisesRegex(PermissionError, 'special_capabilities_not_allowed'):
                    private_directory(directory, require_linux=True)

    def test_actual_test_runner_requires_all_twelve_without_skips(self):
        for count, skipped, success in ((12, [], True), (0, [], True),
                                        (12, [('test', 'reason')], True),
                                        (12, [], False)):
            result = SimpleNamespace(testsRun=count, skipped=skipped,
                                     wasSuccessful=lambda: success)
            with patch.dict(os.environ, HIDS_M1_PRODUCER=str(FILE)), \
                    patch.object(launcher.os, 'chdir'), \
                    patch.object(launcher.sys, 'path', list(sys.path)), \
                    patch.object(unittest.defaultTestLoader, 'discover', return_value=object()), \
                    patch.object(unittest, 'TextTestRunner') as runner:
                runner.return_value.run.return_value = result
                with self.assertRaises(SystemExit) as exit_result:
                    launcher.run_tests()
                self.assertEqual(exit_result.exception.code,
                                 0 if count == 12 and not skipped and success else 1)


if __name__ == '__main__':
    unittest.main()
