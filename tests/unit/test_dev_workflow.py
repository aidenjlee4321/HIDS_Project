"""Workflow tests use private synthetic repositories, never the VM/live sources."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import dev


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hids-dev-unit-')
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name).resolve()
        self.repo=root/'repo';self.repo.mkdir()
        (self.repo/'collector').mkdir();(self.repo/'collector/example.cpp').write_text('int main(){return 0;}\n')
        integration=self.repo/'tests/integration';integration.mkdir(parents=True)
        self.runner=integration/'validate_m2_offline.sh'
        self.runner.write_text('set -eu\nprintf "fixture stdout\\n"\nprintf "fixture stderr\\n" >&2\ntrue\n')
        self.state=root/'state';self.share=root/'CCDC-Transfer';self.share.mkdir()
        self.output=root/'results'

    def snapshot(self,name='fixture-one'):
        return dev.create_snapshot(self.repo,self.state,name)

    def validate(self,root,**kwargs):
        return dev.validate_run(root,self.output,ubuntu=True,
            preflight=lambda:(shutil.which('true'),[]),**kwargs)

    def test_fresh_intermediate_directories_are_private(self):
        nested=self.state/'intermediate'/'runs'
        dev.private_dir(nested)
        for path in (self.state,self.state/'intermediate',nested):
            self.assertEqual(path.stat().st_mode & 0o777,0o700)
        self.assertEqual(dev.private_state(self.state),self.state)

    def test_incorrect_existing_state_is_not_repaired(self):
        self.state.mkdir(mode=0o755)
        marker=self.state/'keep';marker.write_text('unchanged')
        before=(self.state.stat().st_mode,self.state.stat().st_mtime_ns,marker.read_bytes())
        self.assertEqual(dev.main(['test','--repo',str(self.repo),'--state-dir',str(self.state)]),1)
        self.assertFalse((self.state/'runs').exists())
        self.assertEqual(before,(self.state.stat().st_mode,self.state.stat().st_mtime_ns,marker.read_bytes()))

    def test_private_state_symlinks_rejected(self):
        outside=self.state.parent/'outside';outside.mkdir(mode=0o700)
        self.state.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(dev.WorkflowError):dev.private_state(self.state/'runs')
        self.assertFalse((outside/'runs').exists())
        self.state.unlink();dev.private_state(self.state)
        (self.state/'runs').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(dev.WorkflowError):dev.private_state(self.state)

    def test_partial_initialization_retry_and_bad_child(self):
        dev.private_dir(self.state)
        original=Path.mkdir
        def fail_runs(path,*args,**kwargs):
            if path.name=='runs':raise OSError('injected initialization interruption')
            return original(path,*args,**kwargs)
        with patch.object(Path,'mkdir',fail_runs):
            with self.assertRaises(OSError):dev.private_dir(self.state/'nested'/'runs')
        dev.private_dir(self.state/'nested'/'runs')
        self.assertEqual((self.state/'nested').stat().st_mode & 0o777,0o700)
        bad=self.state/'bad';bad.mkdir(mode=0o755)
        with self.assertRaises(dev.WorkflowError):dev.private_state(self.state)
        self.assertEqual(bad.stat().st_mode & 0o777,0o755)

    def test_fresh_cli_test_snapshot_transfer(self):
        self.state=self.state/'nested'/'private'
        common=['--repo',str(self.repo),'--state-dir',str(self.state)]
        with patch('scripts.dev.shutil.which',return_value=shutil.which('true')):
            self.assertEqual(dev.main(['test']+common),0)
        self.assertEqual(dev.main(['snapshot']+common+['--name','fresh-cycle']),0)
        self.assertEqual(dev.main(['transfer']+common+['--share',str(self.share),'--name','fresh-cycle']),0)
        for path in [self.state.parent.parent,self.state.parent,self.state]+list(self.state.rglob('*')):
            if path.is_dir():self.assertEqual(path.stat().st_mode & 0o777,0o700,str(path))
        snapshot,digest=dev.pinned_snapshot(self.state,'fresh-cycle')
        dev.verify(self.share/'collector-validation/snapshots/fresh-cycle',digest)

    def test_success_inventory_independent_and_duplicate_prevention(self):
        snapshot,digest,count=self.snapshot()
        manifest,actual=dev.verify(snapshot,digest)
        self.assertEqual(digest,actual)
        self.assertEqual(count,len(manifest['files']))
        self.assertEqual(dev.tree(snapshot)[0],set(manifest['files'])|dev.METADATA)
        self.assertFalse(any(p.is_symlink() for p in snapshot.rglob('*')))
        self.assertNotEqual((snapshot/'collector/example.cpp').stat().st_ino,(self.repo/'collector/example.cpp').stat().st_ino)
        with self.assertRaises(FileExistsError):self.snapshot()
        self.assertEqual(dev.verify(snapshot,digest)[1],digest)

    def test_hash_mismatch_missing_unexpected_and_directory(self):
        for index,change in enumerate(('content','missing','extra','directory')):
            snapshot,digest,_=self.snapshot('case-'+str(index))
            path=snapshot/'collector/example.cpp'
            if change=='content':path.write_text('modified')
            elif change=='missing':path.unlink()
            elif change=='extra':(snapshot/'unexpected.txt').write_text('extra')
            else:(snapshot/'unexpected').mkdir()
            with self.subTest(change=change),self.assertRaises(dev.WorkflowError):dev.verify(snapshot,digest)

    def test_symlink_source_snapshot_manifest_and_transfer_parent(self):
        source=self.repo/'collector/link.hpp';source.symlink_to('example.cpp')
        with self.assertRaises(dev.WorkflowError):self.snapshot('bad-source')
        source.unlink()
        snapshot,digest,_=self.snapshot()
        path=snapshot/'collector/example.cpp';path.unlink();path.symlink_to(self.repo/'collector/example.cpp')
        with self.assertRaises(dev.WorkflowError):dev.verify(snapshot,digest)
        path.unlink();path.write_bytes((self.repo/'collector/example.cpp').read_bytes())
        fresh,digest,_=self.snapshot('fresh')
        raw=(fresh/dev.MANIFEST).read_bytes();(fresh/dev.MANIFEST).unlink();target=self.repo/'manifest.json';target.write_bytes(raw);(fresh/dev.MANIFEST).symlink_to(target)
        with self.assertRaises(dev.WorkflowError):dev.verify(fresh,digest)
        (fresh/dev.MANIFEST).unlink();(fresh/dev.MANIFEST).write_bytes(raw)
        self.snapshot('safe-transfer')
        outside=self.repo/'outside';outside.mkdir()
        (self.share/'collector-validation').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(dev.WorkflowError):dev.transfer(self.state,self.share,'safe-transfer')
        self.assertFalse((outside/'snapshots').exists())

    def test_transfer_verified_no_overwrite_and_canonical_can_advance(self):
        old=self.share/'research';old.mkdir();(old/'keep.txt').write_text('preserve')
        snapshot,digest,count=self.snapshot()
        (self.repo/'collector/example.cpp').write_text('new canonical revision')
        copied,got,total=dev.transfer(self.state,self.share)
        self.assertEqual((got,total),(digest,count+2))
        self.assertEqual(dev.verify(copied,digest)[1],digest)
        with self.assertRaises(FileExistsError):dev.transfer(self.state,self.share)
        self.assertEqual((old/'keep.txt').read_text(),'preserve')
        self.assertEqual(dev.verify(snapshot,digest)[1],digest)

    def test_transfer_failure_retains_partial_and_source(self):
        snapshot,digest,_=self.snapshot()
        with patch('scripts.dev.shutil.copyfileobj',side_effect=OSError('injected transfer error')):
            with self.assertRaises(OSError):dev.transfer(self.state,self.share)
        partial=self.share/'collector-validation/snapshots'/snapshot.name
        self.assertTrue(partial.is_dir())
        with self.assertRaises(Exception):dev.verify(partial,digest)
        self.assertEqual(dev.verify(snapshot,digest)[1],digest)

    def test_integrity_failure_does_not_execute_runner(self):
        self.runner.write_text('touch SHOULD_NEVER_EXIST\n')
        snapshot,digest,_=self.snapshot()
        (snapshot/'collector/example.cpp').write_text('tampered')
        report,directory,code,_=self.validate(snapshot)
        self.assertNotEqual(code,0);self.assertEqual(report['status'],'blocked')
        self.assertFalse((snapshot/'SHOULD_NEVER_EXIST').exists())
        self.assertEqual(report['phases'],[])
        self.assertTrue((directory/'validation.json').is_file())

    def test_missing_dependencies_no_runner(self):
        snapshot,_,_=self.snapshot()
        report,_,code,_=dev.validate_run(snapshot,self.output,ubuntu=True,preflight=lambda:(None,['SDK missing']))
        self.assertNotEqual(code,0);self.assertIn('SDK missing',report['error']);self.assertEqual(report['phases'],[])

    def test_compile_failure_recorded(self):
        snapshot,_,_=self.snapshot()
        report,_,code,_=dev.validate_run(snapshot,self.output,ubuntu=True,preflight=lambda:(sys.executable,[]))
        self.assertNotEqual(code,0)
        self.assertEqual(report['phases'][0]['name'],'dependency_compile')
        self.assertNotEqual(report['phases'][0]['exit_code'],0)
        self.assertEqual(len(report['phases']),1)

    def test_failed_tests_individual_exit_codes_and_separate_logs(self):
        self.runner.write_text('set -eu\nprintf "out\\n"\nprintf "err\\n" >&2\nfalse\nprintf "unreachable"\n')
        snapshot,_,_=self.snapshot()
        report,directory,code,_=self.validate(snapshot)
        self.assertNotEqual(code,0);self.assertEqual(report['status'],'failed')
        phase=report['phases'][-1]
        self.assertEqual(phase['exit_code'],1)
        self.assertIn('out', (directory/phase['stdout_file']).read_text())
        self.assertNotIn('err', (directory/phase['stdout_file']).read_text())
        self.assertIn('err', (directory/phase['stderr_file']).read_text())
        self.assertTrue(any(item['command']=='false' and item['exit_code']==1 for item in phase['commands']),phase['commands'])
        self.assertFalse(any('unreachable' in item['command'] for item in phase['commands']))

    def test_trace_conditions_and_nonexecuted_branches(self):
        self.runner.write_text("""set -eu
if [[ 1 == 0 ]]; then printf 'NEVER_EXECUTED'; fi
if [[ 1 == 1 ]]; then hids_run printf 'taken'; fi
if hids_run test 1 = 0; then printf 'NEVER_EXECUTED'; fi
if hids_run test 1 = 1; then hids_run true; fi
hids_run printf 'final'
""")
        report, directory, code, _ = self.validate(self.snapshot()[0])
        self.assertEqual(code, 0)
        phase = report['phases'][-1]
        commands = phase['commands']
        self.assertFalse(any('[[' in x['command'] or 'NEVER_EXECUTED' in x['command'] for x in commands))
        self.assertIn({'command': 'test 1 = 0', 'exit_code': 1}, commands)
        self.assertIn({'command': 'test 1 = 1', 'exit_code': 0}, commands)
        self.assertIn({'command': 'printf final', 'exit_code': 0}, commands)
        self.assertEqual(commands[-1], {'command': '[shell aggregate exit]', 'exit_code': 0})
        self.assertIn('Validation shell identity: UID=', (directory/phase['stderr_file']).read_text())

    def test_trace_final_command_failure(self):
        self.runner.write_text('set -eu\nhids_run false\n')
        report, _, code, _ = self.validate(self.snapshot()[0])
        self.assertNotEqual(code, 0)
        self.assertIn({'command': 'false', 'exit_code': 1}, report['phases'][-1]['commands'])
        self.assertEqual(report['phases'][-1]['exit_code'], 1)
        self.assertEqual(report['phases'][-1]['commands'][-1],
                         {'command': '[shell aggregate exit]', 'exit_code': 1})

    def test_success_skips_incomplete_not_passed(self):
        self.runner.write_text("""set -eu
printf '%s\\n' "test_one (fixture) ... skipped 'Linux unavailable'" "OK (skipped=1)" >&2
""")
        snapshot,_,_=self.snapshot()
        report,_,code,_=self.validate(snapshot)
        self.assertNotEqual(code,0);self.assertEqual(report['status'],'incomplete')
        self.assertEqual(report['phases'][-1]['skipped_count'],1)
        self.assertEqual(len(report['phases'][-1]['skipped_tests']),1)

    def test_reports_missing_import_binding_and_conflict(self):
        with self.assertRaises(dev.WorkflowError):dev.import_reports(self.state,self.share)
        snapshot,digest,_=self.snapshot()
        with patch('scripts.dev.environment_info',return_value={'system':'Linux','architecture':'aarch64','distribution':'ubuntu','distribution_version':'26.04'}):
            report,directory,code,_=self.validate(snapshot)
        self.assertEqual(code,0,report)
        published=dev.publish_summary(report,directory,self.share)
        imported=dev.import_reports(self.state,self.share)
        self.assertEqual(imported[0]['source_manifest_sha256'],digest)
        self.assertEqual(len(dev.import_reports(self.state,self.share)),1)
        bad=copy.deepcopy(report);bad['source_manifest_sha256']='0'*64
        (published/'validation.json').write_bytes(dev.json_bytes(bad))
        (published/'validation.sha256').write_text(dev.sha(published/'validation.json')+'\n')
        with self.assertRaises(dev.WorkflowError):dev.import_reports(self.state,self.share)

    def test_contradictory_pass_and_manifest_digest_rejected(self):
        snapshot,digest,_=self.snapshot()
        with self.assertRaises(dev.WorkflowError):dev.verify(snapshot,'0'*64)
        report,directory,_,_=self.validate(snapshot)
        report['phases'][-1]['exit_code']=9
        (directory/'validation.json').write_bytes(dev.json_bytes(report))
        (directory/'validation.sha256').write_text(dev.sha(directory/'validation.json')+'\n')
        with self.assertRaises(dev.WorkflowError):dev.validate_report(directory/'validation.json',self.state)

    def test_state_inside_repo_and_unsafe_names_denied(self):
        with self.assertRaises(dev.WorkflowError):dev.create_snapshot(self.repo,self.repo/'state')
        for name in ('../escape','/absolute','..','contains space'):
            with self.subTest(name=name),self.assertRaises(dev.WorkflowError):self.snapshot(name)

    def test_output_inside_snapshot_and_shared_folder_denied(self):
        snapshot,_,_=self.snapshot()
        with self.assertRaises(dev.WorkflowError):
            dev.validate_run(snapshot,snapshot/'logs',ubuntu=True)
        self.assertFalse((snapshot/'logs').exists())
        with self.assertRaises(dev.WorkflowError):
            dev.validate_run(snapshot,self.share/'logs',ubuntu=True,publish=self.share)
        self.assertFalse((self.share/'logs').exists())
