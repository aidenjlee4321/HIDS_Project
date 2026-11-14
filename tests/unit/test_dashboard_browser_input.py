import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api.browser_prerequisite import validate,inventory,install,Denied

class BrowserInputTests(unittest.TestCase):
    def setUp(self):self.value=json.loads((Path(__file__).resolve().parents[2]/'packaging/browser-inputs.json').read_text())
    def test_named_image_pin_and_no_vendor_binary_packaged(self):
        self.assertEqual(validate(self.value)['version'],'Chrome/158.0.8127.18');self.assertEqual(len(self.value['files']),301)
    def test_bad_paths_hash_modes_versions_and_links_refused(self):
        for change in ('path','hash','mode','version','links'):
            v=copy.deepcopy(self.value)
            if change=='path':v['files']['../escape']=v['files']['chrome']
            elif change=='hash':v['files']['chrome']['sha256']='0'*64
            elif change=='mode':v['files']['chrome']['mode']=0o4755
            elif change=='version':v['version']='other'
            else:v['links']={'chrome':'/usr/bin/anything'}
            with self.subTest(change=change),self.assertRaises(Denied):validate(v)
    def test_unrecognized_or_symlink_source_inventory_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();(root/'unexpected').write_text('x')
            with self.assertRaises(Denied):inventory(root,self.value['files'])
            (root/'unexpected').unlink();(root/'chrome').symlink_to('/usr/bin/true')
            with self.assertRaises(Denied):inventory(root,self.value['files'])
    def test_unprivileged_install_never_opens_input_or_destination(self):
        with patch('api.browser_prerequisite.os.getuid',return_value=1000),patch('api.browser_prerequisite.trusted') as check:
            with self.assertRaises(Denied):install(Path('/never-read'))
            check.assert_not_called()
if __name__=='__main__':unittest.main()
