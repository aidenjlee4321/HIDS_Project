import json
import unittest
from unittest.mock import patch
from api.sources_cli import process_runtime

class RuntimeMetadataTests(unittest.TestCase):
    def test_only_matching_owned_scope_and_closed_typed_status(self):
        owned=dict(instances=dict(proc_lifecycle=dict(source='a',activation='b',generation='c')))
        value=dict(version=1,source='a',activation='b',generation='c',state='initialized_delivery_unproven',backend_exit=None,collector_exit=None)
        def read(v):
            with patch('engine.ingestion.process_control.trusted',return_value=json.dumps(v).encode()):return process_runtime(owned)
        result=read(value);self.assertTrue(result['available']);self.assertEqual(result['current_monitoring'],'not_assessed');self.assertIsNone(result['forced_stop'])
        self.assertTrue(read(dict(value,state='failed',forced=True,backend_exit=1))['available'])
        for bad in (dict(value,activation='foreign'),dict(value,state='all-good'),dict(value,forced=1),dict(value,backend_exit=True),dict(value,raw='anything')):
            self.assertFalse(read(bad)['available'])
    def test_no_ownership_never_reads_a_runtime_file(self):
        with patch('engine.ingestion.process_control.trusted') as read:
            self.assertFalse(process_runtime(dict(instances={}))['available']);read.assert_not_called()
    def test_version_two_witness_is_validated_but_not_projected(self):
        owned=dict(instances=dict(proc_lifecycle=dict(source='a',activation='b',generation='c')))
        value=dict(version=2,source='a',activation='b',generation='c',state='stopped',backend_exit=0,collector_exit=0,runtime_pid=123,runtime_invocation='a'*32)
        for v,expected in ((value,True),(dict(value,runtime_pid=True),False),(dict(value,runtime_invocation='bad'),False),(dict(value,version=1),False)):
            with patch('engine.ingestion.process_control.trusted',return_value=json.dumps(v).encode()):
                result=process_runtime(owned);self.assertEqual(result['available'],expected);self.assertNotIn('runtime_pid',result)
if __name__=='__main__':unittest.main()
