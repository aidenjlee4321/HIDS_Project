from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from build_development_deb import audit_stage

class PayloadSafetyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
    def put(self,name,data):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p
    def test_runtime_code_and_explicit_python_link_allowed(self):
        self.put('opt/hids-dashboard/code/api/app.py',b'pass\n');p=self.root/'opt/hids-dashboard/venv/bin/python3';p.parent.mkdir(parents=True);p.symlink_to('/usr/bin/python3')
        self.assertEqual(audit_stage(self.root),1)
    def test_runtime_dependency_license_preserved(self):
        self.put('opt/hids-dashboard/venv/lib/python3.14/site-packages/example.dist-info/licenses/LICENSE.md',b'Public license notice')
        self.assertEqual(audit_stage(self.root),1)
    def test_lab_readme_in_runtime_code_rejected(self):
        self.put('opt/hids-dashboard/code/api/README.md',b'Lab-only machine reference')
        with self.assertRaises(ValueError):audit_stage(self.root)
    def test_runtime_database_and_private_key_rejected(self):
        for name,data in [('var/lib/hids/process/store.sqlite',b'fixture'),('opt/hids-dashboard/sample.pem',b'-----BEGIN PRIVATE KEY-----')]:
            path=self.put(name,data)
            with self.assertRaises(ValueError):audit_stage(self.root)
            path.unlink()
    def test_unexpected_link_rejected_without_reading_target(self):
        (self.root/'foreign').symlink_to('/etc/shadow')
        with self.assertRaises(ValueError):audit_stage(self.root)
if __name__=='__main__':unittest.main()
