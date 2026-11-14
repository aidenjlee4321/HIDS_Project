"""Approved production-shaped config/store semantics; no real paths opened."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine.detection.m4_handoff import Source, Store, Invalid
from engine.detection.m4_service import LiveSource,LiveStore,validate_config,POLICY

UUID='00000000-0000-4000-8000-000000000001'


class ServiceTests(unittest.TestCase):
    def config(self):
        return dict(version=1,enabled=True,source=UUID,activation=UUID,generation=UUID,
                    max_pages=512,storage=dict(POLICY),max_events=16,max_seconds=120)

    def test_closed_selection_and_approved_limits(self):
        self.assertEqual(validate_config(self.config()),self.config())
        variants={'version':True,'enabled':1,'source':'bad','generation':'*','max_pages':64,'max_events':17,
                  'max_seconds':121,'path':'/tmp/anything','max_events_bool':True,'storage':{}}
        for key,value in variants.items():
            c=self.config();c[key]=value
            with self.subTest(key=key),self.assertRaises((Invalid,ValueError)):validate_config(c)
        for field in ('max_events','max_seconds'):
            for value in (True,0,-1):
                c=self.config();c[field]=value
                with self.subTest(field=field,value=value),self.assertRaises(Invalid):validate_config(c)
        c=self.config();c['storage']['minimum_free_bytes']=1024**2
        with self.assertRaises(Invalid):validate_config(c)

    def test_disabled_is_explicit_valid_configuration(self):
        c=self.config();c['enabled']=False
        self.assertFalse(validate_config(c)['enabled'])

    def test_fixed_paths_and_lab_guard_stay_separate(self):
        scope=(UUID,UUID,UUID)
        source=LiveSource(Path('/var/lib/hids/m3'),*scope)
        self.assertEqual(source.ORIGIN,'audit_plugin')
        with self.assertRaises(Invalid):Source(Path('/var/lib/hids/m3'),*scope)
        with self.assertRaises(Invalid):LiveSource(Path('/tmp/elsewhere'),*scope)
        with self.assertRaises(Invalid):LiveStore(Path('/tmp/elsewhere'),create=True)

    def test_marker_separation_and_disabled_rules(self):
        # Bypass ONLY the fixed-path constructor inside this test to exercise
        # the real class schema/marker in private synthetic temporary storage.
        with tempfile.TemporaryDirectory(prefix='hids-m4-store-marker.') as temp:
            directory=Path(temp).resolve()/'store'
            live=LiveStore.__new__(LiveStore)
            with patch('engine.ingestion.m3_storage.Guard._available',return_value=8*1024**3):
                Store.__init__(live,directory,create=True,max_pages=512,storage=dict(POLICY),lab_only=False)
            try:
                self.assertEqual(live.db.execute('PRAGMA application_id').fetchone(),(0x48344c31,))
                self.assertEqual(live.db.execute('PRAGMA max_page_count').fetchone(),(512,))
                self.assertFalse(live.summary()['lab_only'])
                self.assertEqual(live.evaluate_pending(),0)
                with self.assertRaises(Invalid):live.import_page(object(),[{}])
            finally:live.close()
            with self.assertRaises(Invalid):Store(directory,max_pages=512,storage=dict(POLICY),lab_only=True)


if __name__=='__main__':unittest.main()
