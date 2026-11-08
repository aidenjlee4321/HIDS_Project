"""Ordinary-user archive regressions; no systemd, root or live journal access."""
import copy
import errno
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[2]/'docs/validation/m2-runtime-acceptance/resources.py'
SPEC = importlib.util.spec_from_file_location('m2_acceptance_resources', FILE)
resources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resources)


class FakeInventory:
    def __init__(self, runtime, database, evidence):
        self.base, self.evidence = runtime, evidence
        self.data = dict(entries=[], cleanup_complete=False)
        for root in (runtime, database):
            for name, value in resources.tree_manifest(root).items():
                entry = {k: value[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode', 'directory')}
                entry['path'] = str(root if name == '.' else root/name)
                if not value['directory']: entry['sha256'] = value['sha256']
                self.data['entries'].append(entry)
        self.writes = 0

    def check(self):
        # Exercise the actual inventory checker, without the root-only loader.
        resources.Inventory.check(self)

    def write(self):
        self.writes += 1
        (self.evidence/'test-inventory.json').write_text(json.dumps(self.data))


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hids-archive-unit-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.runtime = self.root/'runtime-source'; self.runtime.mkdir(mode=0o755)
        (self.runtime/'code').mkdir(mode=0o750)
        (self.runtime/'code/data').write_bytes(b'controlled bytes\0\xff\n')
        (self.runtime/'code/data').chmod(0o640)
        (self.runtime/'empty').mkdir(mode=0o700)
        self.database = self.root/'db-source'; self.database.mkdir(mode=0o700)
        for name in ('journal.sqlite', 'journal.sqlite-wal', 'journal.sqlite-shm'):
            (self.database/name).write_bytes((name+' evidence').encode())
            (self.database/name).chmod(0o600)
        self.evidence = self.root/'evidence'; self.evidence.mkdir(mode=0o700)
        self.target = self.evidence/'runtime'
        self.manifest = resources.tree_manifest(self.runtime)
        self.inv = FakeInventory(self.runtime, self.database, self.evidence)
        self.ingest = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())

    def assert_original(self):
        self.assertEqual(resources.tree_manifest(self.runtime), self.manifest)
        self.assertFalse(self.inv.data['cleanup_complete'])

    def prepare(self):
        return resources.prepare_archives(self.inv, self.database, self.ingest)

    def test_same_filesystem_copy_finalize_metadata_and_source_preservation(self):
        receipt = resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original()
        resources.verify_archive(receipt)
        self.assertTrue(resources._equivalent(resources.tree_manifest(self.target), self.manifest))
        self.assertNotEqual(self.runtime.stat().st_ino, self.target.stat().st_ino)
        self.assertEqual((self.target/'code/data').stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.target/'code').stat().st_mode & 0o777, 0o750)
        self.assertEqual((self.target/'code/data').stat().st_uid, os.getuid())
        self.assertEqual((self.target/'code/data').stat().st_gid, os.getgid())
        self.assertEqual(list(self.evidence.glob('.runtime.staging-*')), [])

    def test_source_rename_exdev_barrier_never_used(self):
        # Simulate a boundary where any pathname source rename raises EXDEV.
        # Only a native no-replace rename between destination siblings is legal.
        finalize = resources._finalize_archive
        calls = []
        def checked_finalize(stage, target):
            self.assertEqual(stage.parent, self.evidence)
            self.assertEqual(target.parent, self.evidence)
            self.assertEqual(stage.stat().st_dev, target.parent.stat().st_dev)
            calls.append((stage, target))
            return finalize(stage, target)
        with patch.object(resources.os, 'rename', side_effect=OSError(errno.EXDEV, 'simulated boundary')) as rename, \
                patch.object(resources, '_finalize_archive', side_effect=checked_finalize):
            receipts = self.prepare()
        rename.assert_not_called()
        self.assertEqual(len(calls), 2)
        self.assert_original(); self.assertTrue(self.database.exists())
        for receipt in receipts: resources.verify_archive(receipt)

    def test_real_cross_filesystem_when_available(self):
        alternate = Path('/dev/shm')
        if not (os.sys.platform.startswith('linux') and alternate.is_dir() and
                os.access(alternate, os.W_OK) and alternate.stat().st_dev != self.runtime.stat().st_dev):
            self.skipTest('requires writable Linux /dev/shm on another filesystem; no mounts created')
        with tempfile.TemporaryDirectory(prefix='hids-archive-cross-', dir=alternate) as tmp:
            evidence = Path(tmp)
            self.assertNotEqual(evidence.stat().st_dev, self.runtime.stat().st_dev)
            inv = FakeInventory(self.runtime, self.database, evidence)
            receipts = resources.prepare_archives(inv, self.database, self.ingest)
            for receipt in receipts:
                resources.verify_archive(receipt)
            self.assert_original()
            self.assertTrue(self.database.exists())

    def test_copy_failure_leaves_partial_stage_and_original(self):
        def partial(source, stage, manifest):
            (stage/'partial').write_bytes(b'partial')
            raise OSError(errno.ENOSPC, 'injected copy failure')
        with patch.object(resources, '_copy_tree', side_effect=partial), self.assertRaises(OSError):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original(); self.assertFalse(self.target.exists())
        self.assertEqual(len(list(self.evidence.glob('.runtime.staging-*'))), 1)

    def test_interrupted_copy_preserves_complete_original(self):
        with patch.object(resources, '_copy_tree', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original(); self.assertFalse(self.target.exists())

    def test_file_sync_failure_preserves_original(self):
        with patch.object(resources.os, 'fsync', side_effect=OSError(errno.EIO, 'sync failed')), self.assertRaises(OSError):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original(); self.assertFalse(self.target.exists())

    def test_inventory_bound_fails_before_creating_bookkeeping(self):
        inv = object.__new__(resources.Inventory)
        inv.evidence = self.evidence; inv.path = self.evidence/'inventory.json'
        inv.data = {'oversized': 'x'*(1024*1024)}
        with self.assertRaisesRegex(RuntimeError, 'inventory metadata bound'): inv.write(initial=True)
        self.assertFalse(inv.path.exists()); self.assert_original()

    def test_corrupt_missing_extra_or_permission_mismatch_fails_verification(self):
        original = resources._copy_tree
        for change in ('corrupt', 'missing', 'extra', 'mode'):
            with self.subTest(change=change):
                target = self.evidence/change
                def damaged(source, stage, manifest):
                    original(source, stage, manifest)
                    if change == 'corrupt': (stage/'code/data').write_bytes(b'wrong')
                    elif change == 'missing': (stage/'code/data').unlink()
                    elif change == 'extra': (stage/'untracked').write_bytes(b'extra')
                    else: (stage/'code/data').chmod(0o600)
                with patch.object(resources, '_copy_tree', side_effect=damaged), self.assertRaises(RuntimeError):
                    resources.archive_tree(self.runtime, target, self.manifest)
                self.assert_original(); self.assertFalse(target.exists())

    def test_ownership_and_structure_comparison(self):
        for key, value in (('uid', os.getuid()+1), ('gid', os.getgid()+1), ('mode', 0o600),
                           ('sha256', '0'*64), ('size', 999)):
            damaged = copy.deepcopy(self.manifest); damaged['code/data'][key] = value
            self.assertFalse(resources._equivalent(damaged, self.manifest), key)
        damaged = copy.deepcopy(self.manifest); del damaged['empty']
        self.assertFalse(resources._equivalent(damaged, self.manifest))

    def test_existing_archive_or_dangling_link_never_merged(self):
        for name, link in (('existing', False), ('dangling', True)):
            target = self.evidence/name
            if link: target.symlink_to(self.evidence/'missing')
            else: target.mkdir()
            with self.assertRaises(RuntimeError): resources.archive_tree(self.runtime, target, self.manifest)
            self.assertTrue(target.is_symlink() if link else not list(target.iterdir()))
            self.assert_original()

    def test_nested_destination_rejected_before_source_changes(self):
        with self.assertRaisesRegex(RuntimeError, 'overlap'):
            resources.archive_tree(self.runtime, self.runtime/'empty/archive', self.manifest)
        self.assert_original()

    def test_atomic_finalize_refuses_racing_empty_destination(self):
        original = resources._finalize_archive
        def collision(stage, target):
            target.mkdir(mode=0o700)
            return original(stage, target)
        with patch.object(resources, '_finalize_archive', side_effect=collision), self.assertRaises(FileExistsError):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original(); self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(len(list(self.evidence.glob('.runtime.staging-*'))), 1)

    def test_finalize_or_directory_sync_failure_preserves_original(self):
        for code in (errno.EXDEV, errno.EIO):
            with self.subTest(code=code), patch.object(resources, '_finalize_archive',
                    side_effect=OSError(code, 'injected finalization failure')), self.assertRaises(OSError):
                resources.archive_tree(self.runtime, self.evidence/str(code), self.manifest)
            self.assert_original()

    def test_post_finalize_verification_failure_keeps_source_and_archive(self):
        original = resources._finalize_archive
        def damage(stage, target):
            original(stage, target)
            (target/'code/data').write_bytes(b'bad finalized archive')
        with patch.object(resources, '_finalize_archive', side_effect=damage), self.assertRaises(RuntimeError):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original(); self.assertTrue(self.target.exists())

    def test_source_change_during_copy_stops_without_removal(self):
        original = resources._copy_tree
        def changing(source, stage, manifest):
            original(source, stage, manifest)
            (source/'code/data').write_bytes(b'external change')
        with patch.object(resources, '_copy_tree', side_effect=changing), self.assertRaises(RuntimeError):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assertTrue(self.runtime.exists()); self.assertFalse(self.target.exists())

    def test_symlinks_hardlinks_and_special_files_rejected(self):
        for kind in ('symlink', 'directory-link', 'hardlink', 'fifo'):
            with self.subTest(kind=kind):
                p = self.runtime/'unsafe'
                if kind == 'symlink': p.symlink_to(self.root/'outside')
                elif kind == 'directory-link': p.symlink_to(self.evidence, target_is_directory=True)
                elif kind == 'hardlink': os.link(self.runtime/'code/data', p)
                else: os.mkfifo(p)
                try:
                    with self.assertRaises(RuntimeError): resources.tree_manifest(self.runtime)
                finally: p.unlink()
        link = self.root/'source-link'; link.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaises(RuntimeError): resources.tree_manifest(link)

    def test_linux_extended_metadata_fails_closed(self):
        with patch.object(resources.sys, 'platform', 'linux'), \
                patch.object(resources.os, 'listxattr', return_value=['system.posix_acl_access'], create=True), \
                self.assertRaisesRegex(RuntimeError, 'extended metadata'):
            resources.tree_manifest(self.runtime)
        self.assert_original()

    def test_both_archives_verified_before_either_source_removed(self):
        receipts = self.prepare()
        self.assert_original(); self.assertTrue(self.database.exists())
        self.assertEqual(self.inv.data['cleanup_phase'], 'archives_verified')
        self.assertEqual(self.inv.writes, 1)
        resources.remove_archived_sources(receipts)
        self.assertFalse(self.database.exists()); self.assertFalse(self.runtime.exists())
        for receipt in receipts: resources.verify_archive(receipt)

    def test_second_archive_failure_preserves_both_sources(self):
        original = resources.archive_tree
        def fail_runtime(source, target, manifest):
            if source == self.runtime: raise OSError(errno.ENOSPC, 'runtime archive failed')
            return original(source, target, manifest)
        with patch.object(resources, 'archive_tree', side_effect=fail_runtime), self.assertRaises(OSError): self.prepare()
        self.assert_original(); self.assertTrue(self.database.exists())
        self.assertTrue((self.evidence/'database').exists())
        self.assertEqual(self.inv.writes, 0)

    def test_receipt_persistence_failure_prevents_source_removal(self):
        with patch.object(self.inv, 'write', side_effect=OSError('inventory write failed')), self.assertRaises(OSError): self.prepare()
        self.assert_original(); self.assertTrue(self.database.exists())
        self.assertTrue((self.evidence/'database').exists() and self.target.exists())

    def test_bad_second_archive_prevents_first_source_removal(self):
        receipts = self.prepare()
        (self.target/'code/data').write_bytes(b'corrupted archive')
        with self.assertRaises(RuntimeError): resources.remove_archived_sources(receipts)
        self.assert_original(); self.assertTrue(self.database.exists())

    def test_untracked_runtime_or_late_source_entry_prevents_removal(self):
        extra = self.runtime/'untracked'; extra.write_bytes(b'do not remove')
        with self.assertRaisesRegex(RuntimeError, 'created-resource inventory'): self.prepare()
        extra.unlink()
        receipts = self.prepare()
        extra.write_bytes(b'late untracked file')
        with self.assertRaises(RuntimeError): resources.remove_archived_sources(receipts)
        self.assertTrue(extra.exists() and self.database.exists() and self.runtime.exists())

    def test_interrupted_deletion_keeps_verified_archives_and_incomplete_flag(self):
        receipts = self.prepare()
        with patch.object(resources.os, 'unlink', side_effect=OSError(errno.EIO, 'delete failed')), self.assertRaises(OSError):
            resources.remove_archived_sources(receipts)
        self.assertFalse(self.inv.data['cleanup_complete'])
        for receipt in receipts: resources.verify_archive(receipt)

    def test_interrupted_directory_traversal_preserves_source(self):
        listing = resources.os.listdir
        calls = []
        def interrupted(fd):
            calls.append(fd)
            if len(calls) == 2: raise KeyboardInterrupt()
            return listing(fd)
        with patch.object(resources.os, 'listdir', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            resources.tree_manifest(self.runtime)
        self.assert_original()

    def test_existing_staging_directory_is_not_reused(self):
        stage = self.evidence/'.runtime.staging-existing'; stage.mkdir(mode=0o700)
        sentinel = stage/'sentinel'; sentinel.write_bytes(b'preexisting')
        with patch.object(resources.tempfile, 'mkdtemp', side_effect=FileExistsError()), self.assertRaises(FileExistsError):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assertEqual(sentinel.read_bytes(), b'preexisting'); self.assert_original()

    def test_exclusive_rename_unavailable_or_unsupported_preserves_sources(self):
        class Unsupported:
            def __call__(self, *args):
                resources.ctypes.set_errno(errno.ENOSYS)
                return -1
        for library in (SimpleNamespace(), SimpleNamespace(renameat2=Unsupported())):
            with patch.object(resources.sys, 'platform', 'linux'), \
                    patch.object(resources.ctypes, 'CDLL', return_value=library), self.assertRaises(OSError):
                # Exercise the real primitive-selection path, not a mocked EXDEV.
                stage = self.evidence/('native-stage-'+str(len(list(self.evidence.iterdir()))))
                stage.mkdir(mode=0o700)
                resources._finalize_archive(stage, self.target)
            self.assertTrue(stage.exists()); self.assert_original()

    def test_nested_device_rejected(self):
        original = resources._metadata
        root_inode = self.runtime.stat().st_ino
        def nested(info):
            result = original(info)
            if info.st_ino != root_inode: result['dev'] += 1
            return result
        with patch.object(resources, '_metadata', side_effect=nested), self.assertRaisesRegex(RuntimeError, 'nested mount'):
            resources.tree_manifest(self.runtime)
        self.assert_original()

    def test_mtime_mismatch_prevents_publication(self):
        original = resources._copy_tree
        def changed(source, stage, manifest):
            original(source, stage, manifest)
            os.utime(stage/'code/data', ns=(1, 1))
        with patch.object(resources, '_copy_tree', side_effect=changed), self.assertRaises(RuntimeError):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original(); self.assertFalse(self.target.exists())

    def test_file_and_directory_sync_precede_publication_and_receipt(self):
        import stat
        events = []; sync = os.fsync; publish = resources._finalize_archive
        def tracked(fd):
            events.append('directory_sync' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file_sync')
            return sync(fd)
        def finalize(stage, target):
            self.assertIn('file_sync', events); self.assertIn('directory_sync', events)
            events.append('publish')
            return publish(stage, target)
        write = self.inv.write
        def receipt():
            self.assertEqual(events.count('publish'), 2)
            self.assertEqual(events[-1], 'directory_sync')
            events.append('receipt'); return write()
        with patch.object(resources.os, 'fsync', side_effect=tracked), \
                patch.object(resources, '_finalize_archive', side_effect=finalize), \
                patch.object(self.inv, 'write', side_effect=receipt):
            self.prepare()
        self.assertEqual(events[-1], 'receipt'); self.assert_original()

    def test_partial_original_removal_keeps_archives_and_incomplete_flag(self):
        receipts = self.prepare(); unlink = os.unlink; calls = []
        def fail_second(*args, **kwargs):
            calls.append(args)
            if len(calls) == 2: raise OSError(errno.EIO, 'partial removal')
            return unlink(*args, **kwargs)
        with patch.object(resources.os, 'unlink', side_effect=fail_second), self.assertRaises(OSError):
            resources.remove_archived_sources(receipts)
        self.assertEqual(len(calls), 2); self.assertFalse(self.inv.data['cleanup_complete'])
        for receipt in receipts: resources.verify_archive(receipt)

    def test_final_bookkeeping_failure_leaves_uncertainty_marker(self):
        receipts = self.prepare()
        resources.remove_archived_sources(receipts)
        with patch.object(self.inv, 'write', side_effect=OSError(errno.EIO, 'completion failed')), self.assertRaises(OSError):
            resources.finish_cleanup(self.inv, receipts)
        self.assertFalse(self.inv.data['cleanup_complete'])
        self.assertTrue((self.evidence/'completion-unconfirmed').is_file())
        for receipt in receipts: resources.verify_archive(receipt)

    def test_successful_final_bookkeeping(self):
        receipts = self.prepare(); resources.remove_archived_sources(receipts)
        resources.finish_cleanup(self.inv, receipts)
        self.assertTrue(self.inv.data['cleanup_complete'])
        self.assertFalse((self.evidence/'completion-unconfirmed').exists())

    def test_shutdown_waits_for_stop_hook(self):
        spec = importlib.util.spec_from_file_location('m2_acceptance_probe', FILE.with_name('probe.py'))
        probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
        def status(state):
            return SimpleNamespace(stdout='MainPID=0\nActiveState='+state+'\nResult=success\nExecMainStatus=0\nExecMainCode=1\n')
        with patch.object(probe.subprocess, 'run', side_effect=[status('deactivating'), status('inactive')]), \
                patch.object(probe.time, 'sleep') as sleep, \
                patch.object(probe, 'latest_exit', return_value=dict(result='success', exit_code='exited', exit_status='0')) as marker:
            probe.wait_exit()
        sleep.assert_called_once(); marker.assert_called_once_with('reader')

    def test_actual_stream_copy_interruption_preserves_source(self):
        write = os.write
        def interrupted(fd, data):
            write(fd, bytes(data[:1]))
            raise KeyboardInterrupt()
        with patch.object(resources.os, 'write', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            resources.archive_tree(self.runtime, self.target, self.manifest)
        self.assert_original(); self.assertFalse(self.target.exists())

    def test_completion_inventory_directory_fsync_failure(self):
        receipts = self.prepare(); resources.remove_archived_sources(receipts)
        inv = object.__new__(resources.Inventory)
        inv.evidence = self.evidence; inv.path = self.evidence/'inventory.json'
        inv.data = dict(self.inv.data)
        inv.write(initial=True)
        sync = os.fsync; calls = []
        def interrupted(fd):
            calls.append(fd)
            if len(calls) == 4: raise OSError(errno.EIO, 'final inventory parent sync')
            return sync(fd)
        with patch.object(resources.os, 'fsync', side_effect=interrupted), self.assertRaises(OSError):
            resources.finish_cleanup(inv, receipts)
        # A replacement may be visible; the independently durable marker is
        # authoritative. Neither return status nor memory claims completion.
        self.assertFalse(inv.data['cleanup_complete'])
        self.assertTrue((self.evidence/'completion-unconfirmed').is_file())
        for receipt in receipts: resources.verify_archive(receipt)

    def test_completion_marker_removal_failure_is_not_success(self):
        receipts = self.prepare(); resources.remove_archived_sources(receipts)
        with patch.object(resources.os, 'unlink', side_effect=OSError(errno.EIO, 'marker removal failed')), self.assertRaises(OSError):
            resources.finish_cleanup(self.inv, receipts)
        self.assertFalse(self.inv.data['cleanup_complete'])
        self.assertTrue((self.evidence/'completion-unconfirmed').exists())

    def test_completion_marker_reservation_never_overwrites_existing(self):
        marker = self.evidence/'completion-unconfirmed'; marker.write_bytes(b'previous uncertainty')
        with self.assertRaises(FileExistsError): resources.finish_cleanup(self.inv, [])
        self.assertEqual(marker.read_bytes(), b'previous uncertainty')
        self.assertFalse(self.inv.data['cleanup_complete'])

    def test_real_cross_filesystem_interruption_and_collision(self):
        alternate = Path('/dev/shm')
        if not (os.sys.platform.startswith('linux') and alternate.is_dir() and
                os.access(alternate, os.W_OK) and alternate.stat().st_dev != self.runtime.stat().st_dev):
            self.skipTest('requires real writable Linux cross-device /dev/shm; no mounts created')
        with tempfile.TemporaryDirectory(prefix='hids-archive-cross-fail-', dir=alternate) as tmp:
            target = Path(tmp)/'runtime'
            self.assertNotEqual(target.parent.stat().st_dev, self.runtime.stat().st_dev)
            def interrupted(fd, data):
                raise KeyboardInterrupt()
            with patch.object(resources.os, 'write', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
                resources.archive_tree(self.runtime, target, self.manifest)
            self.assert_original(); self.assertFalse(target.exists())
            finalize = resources._finalize_archive
            def collide(stage, destination):
                destination.mkdir(mode=0o700)
                return finalize(stage, destination)
            with patch.object(resources, '_finalize_archive', side_effect=collide), self.assertRaises(FileExistsError):
                resources.archive_tree(self.runtime, target, self.manifest)
            self.assert_original(); self.assertEqual(list(target.iterdir()), [])

    def test_real_linux_extended_metadata_rejection(self):
        if not os.sys.platform.startswith('linux'):
            self.skipTest('Linux native xattr handling requires Linux')
        path = self.runtime/'code/data'
        try: os.setxattr(path, 'user.hids_archival_test', b'synthetic')
        except OSError as exc:
            if exc.errno in (errno.ENOTSUP, errno.EOPNOTSUPP): self.skipTest('test filesystem lacks xattr support')
            raise
        try:
            with self.assertRaisesRegex(RuntimeError, 'extended metadata'):
                resources.archive_tree(self.runtime, self.target, self.manifest)
            self.assertFalse(self.target.exists())
        finally: os.removexattr(path, 'user.hids_archival_test')
        # xattr operations legitimately change ctime, so refreeze only after the
        # source-preservation assertion specific to this metadata-only fixture.
        self.assertEqual(path.read_bytes(), b'controlled bytes\0\xff\n')
        self.assertFalse(self.inv.data['cleanup_complete'])


if __name__ == '__main__':
    unittest.main()
