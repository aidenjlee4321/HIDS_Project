"""Private-filesystem harness guards; never mounts or allocates real extents."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.integration import m3_filesystem_ubuntu as filesystem


class FilesystemHarnessTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.fd=os.open(self.root/'filler',os.O_CREAT|os.O_RDWR,0o600)
        self.addCleanup(os.close,self.fd)

    def test_host_filesystem_is_rejected_before_allocation(self):
        with patch.object(filesystem.os,'posix_fallocate',create=True) as allocate:
            with self.assertRaisesRegex(ValueError,'unsafe filler'):
                filesystem.fill(self.fd,self.root,0,self.root.stat().st_dev)
            allocate.assert_not_called()

    def test_image_bound_is_enforced_before_allocation(self):
        os.ftruncate(self.fd,filesystem.SIZE)  # sparse size only
        with patch.object(filesystem,'available',return_value=filesystem.SIZE),patch.object(filesystem.os,'posix_fallocate',create=True) as allocate:
            with self.assertRaisesRegex(ValueError,'image bound'):
                filesystem.fill(self.fd,self.root,0,self.root.stat().st_dev+1)
            allocate.assert_not_called()

    def test_peer_exit_fails_instead_of_waiting_or_passing(self):
        incoming,outgoing=os.pipe();os.close(outgoing)
        with os.fdopen(incoming) as stream:
            with self.assertRaisesRegex(RuntimeError,'peer exited'):filesystem.receive(stream)


if __name__=='__main__':unittest.main()
