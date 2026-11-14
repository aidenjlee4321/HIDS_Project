import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api.setup_contract import *
from api.setup_store import _Store
from api.setup_manager import _Manager,ProcessAdapter
from test_setup import fixture

class IntegrationTests(unittest.TestCase):
    def test_old_catalog_choices_remain_readable_without_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve();p.chmod(0o750);record=dict(version=1,revision=1,selected=[],registry_sha256=LEGACY_REGISTRY_HASH)
            file=p/'selection-0001.json';file.write_text(canonical(record));file.chmod(0o440);before=file.read_bytes()
            store=_Store(p,os.getuid(),os.getgid());self.assertEqual(store.load(),record);new=store.save([],1)
            self.assertEqual(file.read_bytes(),before);self.assertEqual(new['registry_sha256'],REGISTRY_HASH)
    def test_process_eligibility_requires_installed_and_inactive_metadata(self):
        v=fixture();proc=next(s for s in v['sources'] if s['id']=='proc_lifecycle');proc['preflight']='eligible'
        with self.assertRaises(Denied):validate_view(v)
        proc['checks'].update(installed_runtime='present',hids_collection='inactive');validate_view(v)
        proc['checks']['hids_collection']='active'
        with self.assertRaises(Denied):validate_view(v)
    def test_foreign_owned_interval_never_stopped(self):
        from engine.ingestion import process_control as p
        entry=dict(source='a',activation='b',generation='c',state='intent')
        other=dict(source='a',activation='foreign',generation='c',state='initialized_delivery_unproven')
        with patch.object(p,'trusted',return_value=canonical(other).encode()),patch('api.setup_manager.subprocess.run') as call:
            with self.assertRaises(Denied):ProcessAdapter().stop(entry)
            call.assert_not_called()
    def test_initialization_waits_for_fresh_scope_after_old_terminal_status(self):
        from engine.ingestion import process_control as p
        entry=dict(source='a',activation='b',generation='c',state='intent')
        old=dict(source='a',activation='previous',generation='old',state='failed')
        fresh=dict(source='a',activation='b',generation='c',state='initialized_delivery_unproven')
        with patch('api.setup_manager.setup_preflight.unit',return_value={'ActiveState':'inactive'}),patch.object(p,'authorize') as authorize,patch.object(p,'trusted',side_effect=[canonical(old).encode(),canonical(fresh).encode()]),patch('api.setup_manager.subprocess.run') as start,patch('api.setup_manager.time.sleep'):
            self.assertEqual(ProcessAdapter().initialize(entry),'initialized_delivery_unproven');authorize.assert_called_once_with(entry);start.assert_called_once()
    def test_prepare_does_not_start_unit_or_subscribe(self):
        source='11000000-0000-4000-8000-000000000001'
        with patch('engine.ingestion.process_control.configuration',return_value={'source_id':source}),patch('api.setup_manager.subprocess.run') as call:
            entry=ProcessAdapter().prepare();self.assertEqual(entry['source'],source);self.assertEqual(entry['state'],'intent');call.assert_not_called()
    def test_metadata_probe_failure_is_not_eligibility(self):
        from api.setup_preflight import process_metadata
        units={name:{'ActiveState':'inactive','LoadState':'loaded'} for name in ('hids-process-runtime.service','hids-process-collector.service','hids-process-backend.service','hids-process-backend.socket')}
        with patch('engine.ingestion.process_control.runtime_directory',side_effect=PermissionError):
            facts,witness=process_metadata(units,{'CONFIG_PROC_EVENTS':'y','CONFIG_CONNECTOR':'y'})
        self.assertEqual(facts['preflight'],'blocked');self.assertEqual(facts['checks']['runtime_delivery'],'unknown')
    def test_ownership_journal_accepts_new_source_but_no_unknown_sources(self):
        from api import setup_manager as m
        import uuid
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve();p.chmod(0o700)
            entry=dict(source=str(uuid.uuid4()),activation=str(uuid.uuid4()),generation=str(uuid.uuid4()),state='intent')
            value=dict(version=1,revision=1,instances={'proc_lifecycle':entry});(p/'owned.json').write_text(canonical(value));(p/'owned.json').chmod(0o600)
            # Root owner checks are exercised separately on the actual VM.
            with patch.object(m,'RUNTIME',p),patch.object(m,'safe_read',side_effect=lambda path,*args:Path(path).read_bytes()):
                self.assertEqual(m.Ownership().load(),value)
                value['instances']={'foreign':entry};(p/'owned.json').write_text(canonical(value))
                with self.assertRaises(Denied):m.Ownership().load()

if __name__=='__main__':unittest.main()
