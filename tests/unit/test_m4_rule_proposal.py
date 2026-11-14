"""Test-only evidence for a D-08 proposal. No production rule support/activation.

The tiny prototype evaluates the single proposed condition on synthetic complete
M3 events; it is deliberately not imported by any engine module or service.
"""
import base64
import copy
from pathlib import Path
import unittest

from engine.detection.m4_pilot import Invalid,load_json,validate_rule
from engine.ingestion.m3_event import PROFILE
from engine.ingestion.m3_progress import _canonical_execution,ProgressError

ROOT=Path(__file__).resolve().parents[2]
PROPOSAL=ROOT/'rules/proposals/configured-root-shell.json'


def proposed_result(execution,profile):
    try:_canonical_execution(execution)
    except (ProgressError,ValueError):return 'error'
    if profile!=PROFILE:return 'unable'
    return 'matched' if (execution['exe_base64']==base64.b64encode(b'/usr/bin/dash').decode() and
                         execution['euid']==0 and execution['success'] is True) else 'no_match'


class RuleProposalTests(unittest.TestCase):
    def setUp(self):
        self.event=load_json(ROOT/'tests/fixtures/m4/execution.json')['execution']
        self.event.update(exe_base64=base64.b64encode(b'/usr/bin/dash').decode(),euid=0)

    def test_explicit_proposal_not_accepted_by_current_production_parser(self):
        rule=load_json(PROPOSAL)
        self.assertEqual(rule['version'],2)
        self.assertFalse(rule['demo'])
        self.assertEqual(rule['severity'],'informational')
        self.assertEqual(rule['required'],['exe_base64','euid','success'])
        self.assertEqual(rule['all_of'],[{'field':'exe_base64','eq':self.event['exe_base64']},{'field':'euid','eq':0},{'field':'success','eq':True}])
        with self.assertRaises(Invalid):validate_rule(rule)

    def test_matching_root_shell_with_unset_optional_login_identity(self):
        self.assertIsNone(self.event['auid'])
        self.assertEqual(proposed_result(self.event,PROFILE),'matched')

    def test_real_uid_zero_alone_does_not_match_nonzero_effective_uid(self):
        self.event.update(uid=0,euid=1000)
        self.assertEqual(proposed_result(self.event,PROFILE),'no_match')

    def test_effective_uid_not_inferred_from_real_uid(self):
        self.event.update(uid=1000,euid=0,auid=1000)
        self.assertEqual(proposed_result(self.event,PROFILE),'matched')

    def test_other_root_executable_and_comm_spoof_do_not_match(self):
        self.event.update(exe_base64=base64.b64encode(b'/usr/bin/true').decode(),comm_base64=base64.b64encode(b'dash').decode())
        self.assertEqual(proposed_result(self.event,PROFILE),'no_match')

    def test_nonroot_shell_does_not_match(self):
        self.event.update(uid=1000,euid=1000)
        self.assertEqual(proposed_result(self.event,PROFILE),'no_match')

    def test_failure_does_not_match(self):
        self.event.update(success=False,result=-1)
        self.assertEqual(proposed_result(self.event,PROFILE),'no_match')

    def test_unknown_or_unsupported_profile_is_unable(self):
        for profile in (None,'unrecognized'):
            with self.subTest(profile=profile):self.assertEqual(proposed_result(self.event,profile),'unable')

    def test_missing_boolean_null_or_malformed_effective_uid_is_error(self):
        for value in (None,False,'0',-1,2**32):
            event=copy.deepcopy(self.event);event['euid']=value
            with self.subTest(value=value):self.assertEqual(proposed_result(event,PROFILE),'error')
        event=copy.deepcopy(self.event);del event['euid']
        self.assertEqual(proposed_result(event,PROFILE),'error')


if __name__=='__main__':unittest.main()
