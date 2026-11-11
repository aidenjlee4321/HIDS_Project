"""Source-preservation preflight and byte verification; no real Audit access."""
from pathlib import Path
import os
import tempfile
import unittest
from tests.integration import m3_rotation_ubuntu as rotation


class RotationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.active=self.root/'audit.log'
        self.active.write_bytes(b'original active\n');self.active.chmod(0o600)
        self.config=rotation.settings(b'# host policy\nnum_logs = 5\nmax_log_file = 8\nmax_log_file_action = ROTATE\n')

    def test_two_rotations_leave_spare_slot(self):
        old=self.root/'audit.log.1';old.write_bytes(b'older\n');old.chmod(0o400)
        rotation.rotation_room(self.config,rotation.inventory(self.active),2)

    def test_gapped_high_suffix_blocks_deletion(self):
        old=self.root/'audit.log.4';old.write_bytes(b'old');old.chmod(0o400)
        with self.assertRaisesRegex(ValueError,'headroom'):
            rotation.rotation_room(self.config,rotation.inventory(self.active),1)

    def test_finite_budget_and_byte_margin(self):
        files=rotation.inventory(self.active)
        for changes in ({'max_log_file_action':'KEEP_LOGS'},{'num_logs':'2'},{'max_log_file':'0'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                rotation.rotation_room(self.config|changes,files,2)

    def test_unknown_suffix_symlink_and_hardlink_refused(self):
        extra=self.root/'audit.log.gz';extra.write_bytes(b'old')
        with self.assertRaises(ValueError):rotation.inventory(self.active)
        extra.unlink();extra=self.root/'audit.log.1';extra.symlink_to(self.active)
        with self.assertRaises(ValueError):rotation.inventory(self.active)
        extra.unlink();os.link(self.active,extra)
        with self.assertRaises(ValueError):rotation.inventory(self.active)

    def test_rename_and_append_preserve_original_prefix(self):
        before=rotation.inventory(self.active)
        self.active.rename(self.root/'audit.log.1')
        with (self.root/'audit.log.1').open('ab') as stream:stream.write(b'appended\n')
        self.active.write_bytes(b'new');self.active.chmod(0o600)
        rotation.preserved(before,rotation.inventory(self.active))

    def test_truncation_overwrite_and_disappearance_fail(self):
        before=rotation.inventory(self.active)
        for replacement in (b'short',b'changed contents of same or greater length'):
            self.active.write_bytes(replacement)
            with self.assertRaises(ValueError):rotation.preserved(before,rotation.inventory(self.active))
        with self.assertRaisesRegex(ValueError,'disappeared'):rotation.preserved(before,[])

    def test_permission_broadening_fails(self):
        before=rotation.inventory(self.active)
        for mode in (0o644,0o610,0o660):
            self.active.chmod(mode)
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'permissions'):
                rotation.preserved(before,rotation.inventory(self.active))

    def test_cleanup_continues_after_failure_and_reports_it(self):
        attempted=[]
        def fail():
            attempted.append('rule');raise OSError('simulated')
        with self.assertRaisesRegex(RuntimeError,'rule'):
            rotation.restore_all([('rule',fail),('policy',lambda:attempted.append('policy')),
                                  ('stop',lambda:attempted.append('stop'))])
        self.assertEqual(attempted,['rule','policy','stop'])


if __name__=='__main__':unittest.main()
