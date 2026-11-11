"""Workflow controls use isolated files/processes; no SSH/systemd/native sources."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import dev, m3_workflow as workflow


class M3WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hids-workflow-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.out=io.StringIO()
        self.redirect=contextlib.redirect_stdout(self.out);self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__,None,None,None)

    def test_snapshot_includes_timer_and_only_explicit_sanitized_log(self):
        repo=self.root/'repo';repo.mkdir()
        for name in ('packaging/systemd/hids-m3-health.timer','packaging/hids-audit-launcher',
                     'tests/fixtures/audit/structural-exec.log','tests/fixtures/audit/private.log',
                     'tests/unrelated.log'):
            path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic\n')
        path,sha,_=dev.create_snapshot(repo,self.root/'state','complete')
        manifest,_=dev.verify(path,sha)
        self.assertEqual(set(manifest['files']),{'packaging/systemd/hids-m3-health.timer','packaging/hids-audit-launcher',
                                              'tests/fixtures/audit/structural-exec.log'})

    def test_archive_omits_host_clock_and_identity_metadata(self):
        import tarfile
        info=tarfile.TarInfo('synthetic');info.mtime=2**32;info.uid=501;info.uname='host-user'
        actual=workflow.archive_metadata(info)
        self.assertEqual((actual.mtime,actual.uid,actual.uname,actual.pax_headers),(0,0,'',{}))

    def test_nonzero_and_skipped_results_never_pass(self):
        for text,code in (('failure',7),('Ran 3 tests in 0.1s\nOK (skipped=1)',0)):
            run=workflow.Run(self.root/'results','test','source')
            with self.assertRaises(dev.WorkflowError):
                run.phase('fixture',[sys.executable,'-c',f'print({text!r});raise SystemExit({code})'])
            run.finish('expected failure')
            report=json.loads((run.path/'report.json').read_text())
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['phases'][0]['exit_code'],code)
            self.assertEqual(os.stat(run.path/'fixture.stdout').st_mode&0o777,0o600)

    def test_dispatch_report_does_not_claim_acceptance_pass(self):
        run=workflow.Run(self.root/'results','host_orchestration','source')
        run.finish(dispatched=True)
        self.assertEqual(dev.read_json(run.path/'report.json')['status'],'dispatched')

    def test_zero_test_suite_is_not_a_pass(self):
        run=workflow.Run(self.root/'results','test','source')
        with self.assertRaises(dev.WorkflowError):
            run.phase('python',[sys.executable,'-c','print("Ran 0 tests in 0.1s")'])

    def test_phase_timeout_retains_logs_and_failure(self):
        run=workflow.Run(self.root/'results','test','source')
        with self.assertRaises(dev.WorkflowError):
            run.phase('timeout',[sys.executable,'-c','import time;print("started",flush=True);time.sleep(10)'],timeout=.2)
        self.assertEqual(run.report['phases'][0]['exit_code'],124)
        self.assertIn('started',(run.path/'timeout.stdout').read_text())

    def test_success_report_has_bounded_summary_and_hashes(self):
        run=workflow.Run(self.root/'results','test','source')
        run.phase('fixture',[sys.executable,'-c','print("synthetic output")'])
        run.finish()
        report=dev.read_json(run.path/'report.json')
        self.assertEqual(report['status'],'passed')
        self.assertEqual(report['phases'][0]['stdout_sha256'],dev.sha(run.path/'fixture.stdout'))
        self.assertNotIn('synthetic output',json.dumps(report))
        self.assertEqual((run.path/'report.json').stat().st_mode&0o777,0o600)

    def test_dependency_identity_survives_new_snapshot_path_but_not_changed_headers(self):
        maps=[]
        external=self.root/'system-header.h';external.write_text('system')
        for name in ('snapshot-one','snapshot-two'):
            root=self.root/name;root.mkdir();source=root/'source.cpp';source.write_text('identical')
            maps.append(workflow.dependency_inputs([source,external],root))
        self.assertEqual(maps[0],maps[1])
        external.write_text('changed system header')
        self.assertNotEqual(maps[0],workflow.dependency_inputs([source,external],root))

    def test_cache_requires_key_and_all_artifact_hashes(self):
        build=self.root/'cache';build.mkdir(mode=0o700)
        for name in workflow.ARTIFACTS:
            path=build/name;path.write_text('synthetic binary');path.chmod(0o700)
        metadata=dict(key='key',artifacts={n:dev.sha(build/n) for n in workflow.ARTIFACTS})
        (build/'build.json').write_text(json.dumps(metadata))
        self.assertTrue(workflow.build_valid(build,'key'))
        self.assertFalse(workflow.build_valid(build,'different-dependency-key'))
        (build/workflow.ARTIFACTS[0]).write_text('tampered')
        self.assertFalse(workflow.build_valid(build,'key'))
        (build/workflow.ARTIFACTS[0]).unlink()
        self.assertFalse(workflow.build_valid(build,'key'))

    def test_tiers_do_not_silently_add_live_policy_or_reboot(self):
        for tier in ('focused','component','checkpoint'):
            self.out.seek(0);self.out.truncate()
            self.assertEqual(workflow.main(['plan','--tier',tier]),0)
            plan=json.loads(self.out.getvalue())
            self.assertTrue(plan['live_audit_opt_in'])
            self.assertIn('never automatic',plan['reboot'])
            if tier=='focused':self.assertEqual(plan['installed'],[])
            else:self.assertIn('storage',plan['installed'])

    def test_preflight_rejects_active_services_before_config_write(self):
        args=type('Args',(),dict(tier='checkpoint',lab_activation_budget=None))()
        with patch.object(workflow.sys,'platform','linux'),patch.object(workflow.os,'getuid',return_value=0), \
             patch.object(workflow.os,'geteuid',return_value=0),patch.object(workflow.platform,'machine',return_value='aarch64'), \
             patch.object(Path,'read_text',return_value='VERSION_ID="26.04"'),patch.object(workflow,'stopped',return_value=False):
            with self.assertRaisesRegex(dev.WorkflowError,'stop M3'):
                workflow.preflight(args)

    def test_temporary_probe_removed_or_restored_after_fault(self):
        binary=self.root/'binary';binary.write_bytes(b'new');binary.chmod(0o755)
        target=self.root/'installed'
        with patch.object(workflow,'stop'):
            with self.assertRaises(RuntimeError):
                with workflow.temporary_binary(binary,target):raise RuntimeError('test fault')
            self.assertFalse(target.exists())
            target.write_bytes(b'previous');target.chmod(0o700)
            # Root ownership is the production prerequisite, mocked for ordinary local tests.
            with patch.object(workflow.dev,'regular',return_value=type('Info',(),dict(st_uid=0,st_mode=0o100700))()):
                with workflow.temporary_binary(binary,target):self.assertEqual(target.read_bytes(),b'new')
            self.assertEqual(target.read_bytes(),b'previous')
            self.assertEqual(target.stat().st_mode&0o777,0o700)

    def test_baseline_export_keeps_managed_state_private_and_verified(self):
        import tarfile
        def archive(*args,**kwargs):
            with tarfile.open(fileobj=kwargs['stdout'],mode='w') as stream:
                for name in ('collector/example.cpp','packaging/systemd/hids-m3-health.timer'):
                    value=b'synthetic';entry=tarfile.TarInfo(name);entry.size=len(value)
                    stream.addfile(entry,io.BytesIO(value))
        state=self.root/'baseline-state';state.mkdir(mode=0o700)
        with patch.object(workflow.subprocess,'check_output',return_value='a'*40+'\n'), \
             patch.object(workflow.subprocess,'run',side_effect=archive):
            snapshot,sha,commit=workflow.baseline_snapshot('reviewed-ref',state)
        self.assertEqual(commit,'a'*40)
        dev.verify(snapshot,sha);dev.private_state(state)

    def test_detached_driver_finishes_with_dispatched_report(self):
        repo=self.root/'driver-repo';(repo/'collector').mkdir(parents=True)
        (repo/'collector/example.cpp').write_text('synthetic')
        known=self.root/'known';known.write_text('pinned')
        args=type('Args',(),dict(state_dir=self.root/'driver-state',experiment='soak',
            host='ivy@192.168.64.7',known_hosts=known,headers='/existing/headers',tier='component',
            guest_output='/var/tmp/hids-test',live_audit=False,lab_activation_budget=None,
            duration_seconds=10,events=512,history_files=0,detach=True))()
        result=type('Completed',(),dict(returncode=0))()
        commands=[]
        def capture(command,**kwargs):
            commands.append(command);return result
        with patch.object(workflow,'ROOT',repo), \
             patch.object(workflow.subprocess,'check_output',return_value='/tmp/hids-m3-source.fixture\n'), \
             patch.object(workflow.subprocess,'run',side_effect=capture):
            self.assertEqual(workflow.remote(args),0)
        reports=list((args.state_dir/'runs').glob('*/report.json'));self.assertEqual(len(reports),1)
        report=dev.read_json(reports[0]);self.assertEqual(report['status'],'dispatched')
        self.assertTrue(report['job'].startswith('hids-m3-lab-'))
        self.assertIn('--cache-root /var/tmp/hids-test/builds',commands[-1][-1])

    def test_compact_watcher_generates_valid_read_only_python(self):
        import ast,shlex
        known=self.root/'watch-known';known.write_text('pinned')
        args=type('Args',(),dict(host='ivy@192.168.64.7',known_hosts=known,
            job='hids-m3-lab-012345abcdef',guest_output='/var/tmp/hids-test',compact=True,watch_seconds=60))()
        def run(command):
            remote=shlex.split(command[-1]);ast.parse(remote[6])
            self.assertIn('while True:',remote[6]);self.assertNotIn('systemctl stop',remote[6])
            return type('Completed',(),dict(returncode=0))()
        with patch.object(workflow.subprocess,'run',side_effect=run):
            self.assertEqual(workflow.vm_status(args),0)

    def test_status_waits_for_job_exit_even_when_success_report_exists(self):
        import shlex
        known=self.root/'status-known';known.write_text('pinned')
        args=type('Args',(),dict(host='ivy@192.168.64.7',known_hosts=known,
            job='hids-m3-lab-012345abcdef',guest_output=str(self.root/'status'),compact=False,watch_seconds=0))()
        report=Path(args.guest_output)/'jobs'/args.job/'run-one'/'report.json'
        report.parent.mkdir(parents=True);report.write_text(json.dumps(dict(status='passed',error=None)))
        for unit_state,expected in (('active','running'),('inactive','passed'),('failed','failed')):
            output=io.StringIO()
            def run(command,**kwargs):
                if command[0]=='systemctl':
                    return type('Completed',(),dict(stdout=f'ActiveState={unit_state}\nResult=success\nExecMainStatus=0\n'))()
                remote=shlex.split(command[-1])
                with patch.object(sys,'argv',['-c',remote[7],remote[8]]),contextlib.redirect_stdout(output):
                    exec(compile(remote[6],'<generated-status>','exec'),{})
                return type('Completed',(),dict(returncode=0))()
            with patch.object(workflow.subprocess,'run',side_effect=run):self.assertEqual(workflow.vm_status(args),0)
            self.assertEqual(json.loads(output.getvalue())['status'],expected)

    def test_cleanup_resets_only_loaded_failed_hids_units(self):
        calls=[]
        def command(*args):
            calls.append(args)
            if args[1]=='show':return b'failed' if args[2]=='hids-m3-health.service' else b'inactive'
            return b''
        with patch.object(workflow,'command',side_effect=command):workflow.stop()
        resets=[c for c in calls if c[1]=='reset-failed']
        self.assertEqual(resets,[('systemctl','reset-failed','hids-m3-health.service')])

    def test_ssh_uses_existing_host_keys_and_rejects_option_injection(self):
        known=self.root/'known_hosts';known.write_text('fixture')
        args=type('Args',(),dict(host='ivy@192.168.64.7',known_hosts=known))()
        command=workflow.ssh_options(args)
        self.assertIn('StrictHostKeyChecking=yes',command)
        self.assertNotIn('StrictHostKeyChecking=no',command)
        args.host='-oProxyCommand=untrusted'
        with self.assertRaises(dev.WorkflowError):workflow.ssh_options(args)


if __name__=='__main__':unittest.main()
