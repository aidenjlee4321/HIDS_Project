"""Actual setup modules, synthetic facts/files/adapters. No OS source startup."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from api.setup_contract import *
from api.setup_store import _Store
from api.setup_sessions import SetupSessions
from api.setup_manager import _Manager
from api.pilot_sessions import Sessions,Denied

def fixture(eligible=True,record=None):
 facts={name:dict(preflight='unknown' if name=='proc_lifecycle' else 'unsupported',checks=dict(runtime_delivery='unknown')) for name in REGISTRY}
 facts['audit_exec']=dict(preflight='eligible' if eligible else 'blocked',checks=dict(hids_collection='inactive',hids_plugin='present' if eligible else 'absent',runtime_delivery='unknown'))
 facts['witness']=dict(synthetic_only=True);return build_view(facts,record or empty_record())

class ContractTests(unittest.TestCase):
 def test_public_projection_closed_and_honest(self):
  value=public_view(fixture());self.assertNotIn('fingerprint',value);self.assertTrue(value['snapshot_only']);self.assertEqual(value['monitoring_status'],'not_assessed');self.assertNotIn('/var/',canonical(value))
 def test_no_invented_supported_sources(self):
  v=fixture();v['sources'][2]['preflight']='eligible'
  with self.assertRaises(Denied):validate_view(v)
 def test_unknown_fields_and_inconsistent_registry_refuse(self):
  for change in (lambda v:v.update(extra='x'),lambda v:v['confirmed'].update(registry_sha256='x'),lambda v:v['sources'][0].update(label='<img>'),lambda v:v['sources'][0].update(checks={'x':'healthy'})):
   v=fixture();change(v)
   with self.assertRaises(Denied):validate_view(v)
 def test_selection_types_duplicates_paths_and_commands(self):
  for v in (['audit_exec']*2,['other'],['/etc/passwd'],['systemctl start auditd'],{'audit_exec':True},None):
   with self.assertRaises(Denied):selected(v)
 def test_existing_legacy_source_blocks_empty_confirmation_preflight(self):
  from api import setup_preflight as p
  def unit(name):return dict(LoadState='loaded',ActiveState='active' if name in ('auditd.service','hids-journal.service') else 'inactive',FragmentPath='/synthetic/unit')
  with patch.object(p,'unit',side_effect=unit),patch.object(p,'trusted_bytes',return_value=b''),patch.object(p.os,'getuid',return_value=0),patch.object(p.os,'geteuid',return_value=0),patch('engine.ingestion.m3_service.load_config',return_value=dict(source_id='11111111-1111-4111-8111-111111111111')),patch('engine.ingestion.m3_service.identities',side_effect=PermissionError):
   facts=p.facts();self.assertEqual(facts['audit_exec']['checks']['hids_collection'],'active');self.assertEqual(facts['journal_auth']['checks']['existing_hids_service'],'present')
 def test_root_metadata_required(self):
  from api.setup_preflight import facts
  with patch('api.setup_preflight.os.getuid',return_value=1000):
   with self.assertRaises(Denied):facts()

class StoreTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name).resolve();self.p.chmod(0o750);self.store=_Store(self.p,os.geteuid(),os.getegid())
 def test_save_is_immutable_bounded_and_durable(self):
  self.assertEqual(self.store.load(),empty_record());a=self.store.save(['audit_exec'],0);first=(self.p/'selection-0001.json').read_bytes();self.store.save([],1);self.assertEqual(first,(self.p/'selection-0001.json').read_bytes());self.assertEqual(self.store.load()['revision'],2);self.assertEqual((self.p/'selection-0001.json').stat().st_mode&0o777,0o440)
 def test_cap_refuses_without_deleting_prior_choices(self):
  for n in range(16):self.store.save([],n)
  with self.assertRaises(Denied):self.store.save([],16)
  self.assertEqual(len(list(self.p.glob('selection-*.json'))),16)
 def test_stale_or_boolean_revision_refused(self):
  self.store.save([],0)
  for v in (0,True):
   with self.assertRaises(Denied):self.store.save([],v)
  self.assertEqual(self.store.load()['revision'],1)
 def test_unsafe_mode_symlink_and_extra_files_refuse(self):
  self.store.save([],0);p=self.p/'selection-0001.json';p.chmod(0o644)
  with self.assertRaises(Denied):self.store.load()
  p.chmod(0o440);p.rename(self.p/'saved');p.symlink_to(self.p/'saved')
  with self.assertRaises(Denied):self.store.load()
 def test_write_fault_never_publishes_partial_record(self):
  self.store.save([],0)
  for point in ('before_file_sync','before_publish'):
   self.store.fault=lambda name:(_ for _ in ()).throw(OSError('synthetic disk failure')) if name==point else None
   with self.assertRaises(OSError):self.store.save(['audit_exec'],1)
   self.assertEqual(self.store.load()['revision'],1)
 def test_after_publish_fault_reconciles_choices_without_activation(self):
  self.store.fault=lambda point:(_ for _ in ()).throw(OSError('synthetic sync failure')) if point=='after_publish' else None
  with self.assertRaises(OSError):self.store.save([],0)
  self.assertEqual(self.store.load()['revision'],1)
 def test_partial_and_zero_write_handling(self):
  original=os.write
  with patch('api.setup_store.os.write',side_effect=lambda fd,b:original(fd,b[:3])):self.store.save([],0)
  with patch('api.setup_store.os.write',return_value=0):
   with self.assertRaises(Denied):self.store.save([],1)
  self.assertEqual(self.store.load()['revision'],1)
 def test_pending_crash_file_is_not_configuration_or_authority(self):
  p=self.p/('pending-'+'a'*32+'.tmp');p.write_bytes(b'{incomplete');p.chmod(0o600);self.assertEqual(self.store.load(),empty_record());self.store.save([],0);self.assertTrue(p.exists())

class DraftTests(unittest.TestCase):
 def setUp(self):
  self.now=[0.0];self.s=SetupSessions(fixture(),clock=lambda:self.now[0]);self.token=self.s.redeem(self.s.mint());self.body=dict(assessment_id=self.s.view['assessment_id'],confirmed_revision=0,selected=['audit_exec'])
 def stage(self):return self.s.stage(self.token,self.body)['reference']
 def test_root_review_draft_bound_to_view_and_source_selection(self):
  r=self.stage();value=self.s.review(r);self.assertEqual(value['selected'],['audit_exec']);self.assertNotIn(self.token,canonical(value));self.assertEqual(self.s.review(r,consume=True),value)
  with self.assertRaises(Denied):self.s.review(r)
 def test_replacing_draft_revokes_previous_reference(self):
  a=self.stage();b=self.stage()
  with self.assertRaises(Denied):self.s.review(a)
  self.assertEqual(self.s.review(b)['selected'],['audit_exec'])
 def test_draft_ttl_logout_revoke_and_restart(self):
  a=self.stage();self.now[0]=60
  with self.assertRaises(Denied):self.s.review(a)
  a=self.stage();self.s.logout(self.token)
  with self.assertRaises(Denied):self.s.review(a)
  self.token=self.s.redeem(self.s.mint());a=self.stage();self.s.revoke_all()
  with self.assertRaises(Denied):self.s.review(a)
  with self.assertRaises(Denied):SetupSessions(fixture()).review(a)
 def test_session_expiry_cannot_be_renewed_by_housekeeping(self):
  for _ in range(5):self.now[0]+=50;self.s.housekeeping()
  a=self.stage();self.now[0]=550;self.s.housekeeping()
  with self.assertRaises(Denied):self.s.review(a)
 def test_empty_selection_allowed_blocked_unknown_and_stale_refused(self):
  self.body['selected']=[];self.assertEqual(self.s.review(self.stage())['selected'],[])
  for field,value in (('selected',['proc_lifecycle']),('selected',['journal_auth']),('confirmed_revision',True),('assessment_id','wrong')):
   body=copy.deepcopy(self.body);body[field]=value
   with self.assertRaises(Denied):self.s.stage(self.token,body)
 def test_other_scopes_and_grants_are_not_setup_credentials(self):
  for scope in ('pilot:read','history:read'):
   p=Sessions(scope=scope)
   with self.assertRaises(Denied):self.s.stage(p.redeem(p.mint()),self.body)
  with self.assertRaises(Denied):self.s.stage(self.s.mint(),self.body)
 def test_reference_not_bearer_no_scope_selection_from_browser(self):
  r=self.stage()
  with self.assertRaises(Denied):self.s.authorize(r,'setup:draft')
  body=dict(self.body,scope='root')
  with self.assertRaises(Denied):self.s.stage(self.token,body)
 def test_unavailable_view_refuses_grant_and_tls_rechecked(self):
  with self.assertRaises(Denied):SetupSessions(None).mint()
  calls=[];s=SetupSessions(fixture(),mint_check=lambda:calls.append(1));s.mint();self.assertEqual(calls,[1])

class OwnedReaderTests(unittest.TestCase):
 def test_deleted_executable_still_counts_as_owned_reader(self):
  from api.setup_manager import AuditAdapter
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);process=root/'123';process.mkdir();(process/'exe').symlink_to('/usr/lib/hids/hids-audit-plugin (deleted)');(process/'cmdline').write_bytes(b'plugin\0socket\0owned-activation\0generation\0private-test-lease\0')
   with patch('api.setup_manager.Path',side_effect=lambda name:root if name=='/proc' else Path(name)),patch('api.setup_manager.pwd.getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid())):
    self.assertFalse(AuditAdapter().owned_readers_absent(dict(activation='owned-activation')))
    self.assertTrue(AuditAdapter().owned_readers_absent(dict(activation='other-activation')))
 def test_unrelated_executable_arguments_not_read(self):
  from api.setup_manager import AuditAdapter
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);process=root/'123';process.mkdir();(process/'exe').symlink_to('/usr/bin/unrelated')
   with patch('api.setup_manager.Path',side_effect=lambda name:root if name=='/proc' else Path(name)),patch('api.setup_manager.pwd.getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid())):
    self.assertTrue(AuditAdapter().owned_readers_absent(dict(activation='owned-activation')))

class MemoryOwnership:
 def __init__(self):self.value=dict(version=1,revision=0,instances={})
 def load(self):return clone(self.value)
 def write(self,v):self.value=clone(v)
class FakeAdapter:
 def __init__(self,result='initialized_delivery_unproven'):self.calls=[];self.result=result;self.stop_result=True
 def prepare(self):return dict(activation='11111111-1111-4111-8111-111111111111',source='22222222-2222-4222-8222-222222222222',generation=None,state='intent')
 def initialize(self,entry):self.calls.append('start');return self.result
 def stop(self,entry):self.calls.append('stop');return self.stop_result

class ManagerTests(unittest.TestCase):
 # Reuses real store fixture but does not inherit its test methods twice.
 def setUp(self):StoreTests.setUp(self);self.owned=MemoryOwnership();self.adapter=FakeAdapter();self.view=fixture();self.manager=_Manager(self.store,self.owned,lambda _:clone(self.view),{'audit_exec':self.adapter});self.draft=dict(assessment_id=self.view['assessment_id'],fingerprint=self.view['fingerprint'],confirmed=self.view['confirmed'],selected=['audit_exec'])
 def test_confirmation_then_activation_and_owned_stop(self):
  result=self.manager.confirm(self.draft);self.assertEqual(result['confirmed']['selected'],['audit_exec']);self.assertEqual(self.adapter.calls,['start']);self.assertEqual(self.manager.stop(),{'audit_exec':'stopped'})
 def test_empty_choice_never_calls_adapter(self):
  self.draft['selected']=[];result=self.manager.confirm(self.draft);self.assertEqual(self.adapter.calls,[]);self.assertEqual(result['collecting'],'not_collecting')
 def test_unconfirmed_persistence_never_initializes_source(self):
  self.store.fault=lambda point:(_ for _ in ()).throw(OSError('synthetic')) if point=='after_publish' else None
  with self.assertRaises(OSError):self.manager.confirm(self.draft)
  self.assertEqual(self.adapter.calls,[]);self.assertEqual(self.store.load()['revision'],1)
 def test_stale_preflight_or_confirmation_refused(self):
  self.draft['fingerprint']='a'*64
  with self.assertRaises(Denied):self.manager.confirm(self.draft)
  self.assertEqual(self.store.load()['revision'],0)
 def test_unmanaged_active_units_refuse_even_empty_selection(self):
  self.draft['selected']=[];self.view['sources'][0]['checks']['hids_collection']='active'
  with self.assertRaises(Denied):self.manager.confirm(self.draft)
  self.assertEqual(self.adapter.calls,[])
 def test_active_edit_and_uncertain_stop_refused(self):
  self.manager.confirm(self.draft);self.adapter.stop_result=False;self.assertEqual(self.manager.stop(),{'audit_exec':'stop_unconfirmed'})
  with self.assertRaises(Denied):self.manager.confirm(self.draft)
 def test_explicit_stop_cleans_owned_initialization_failure(self):
  self.adapter.result='initialization_failed';self.manager.confirm(self.draft)
  self.assertEqual(self.manager.stop(),{'audit_exec':'stopped'});self.assertEqual(self.adapter.calls,['start','stop'])
 def test_init_exception_is_uncertain_not_clean_success(self):
  self.adapter.initialize=lambda _:(_ for _ in ()).throw(OSError('synthetic'))
  result=self.manager.confirm(self.draft);self.assertEqual(result['states']['audit_exec'],'initialization_unconfirmed')
 def test_prepare_failure_preserves_other_confirmed_subset(self):
  self.view['sources'][2]['preflight']='eligible';self.draft['selected']=['audit_exec','proc_lifecycle'];other=FakeAdapter();self.manager.adapters['proc_lifecycle']=other
  self.adapter.prepare=lambda:(_ for _ in ()).throw(OSError('synthetic configuration unavailable'))
  result=self.manager.confirm(self.draft);self.assertEqual(result['states']['audit_exec'],'initialization_failed');self.assertEqual(other.calls,['start'])
 def test_uncertain_init_does_not_block_other_confirmed_subset(self):
  self.view['sources'][2]['preflight']='eligible';self.draft['selected']=['audit_exec','proc_lifecycle'];other=FakeAdapter();self.manager.adapters['proc_lifecycle']=other
  self.adapter.initialize=lambda _:(_ for _ in ()).throw(OSError('synthetic'))
  result=self.manager.confirm(self.draft);self.assertEqual(result['states']['audit_exec'],'initialization_unconfirmed');self.assertEqual(other.calls,['start'])
 def test_restart_restores_no_activation(self):
  self.draft['selected']=[];self.manager.confirm(self.draft);restarted=_Manager(self.store,self.owned,lambda _:fixture(record=self.store.load()),{'audit_exec':self.adapter});self.assertEqual(restarted.store.load()['selected'],[]);self.assertEqual(self.adapter.calls,[])

if __name__=='__main__':unittest.main()
