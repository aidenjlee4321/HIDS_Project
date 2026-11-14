"""D-14 proposal evidence ONLY, using synthetic adapters and in-memory choices.

No production module imports this model. It opens no source, file, socket or DB,
implements no authentication/OS privilege boundary, and is not an approved wire or
persistence format. OS identity, atomic persistence and cleanup require later tests.
"""
import copy
import secrets
import time
import unittest

SOURCES=('audit_exec','proc_lifecycle','journal_auth')

class Refused(ValueError):pass

def require(value):
    if not value:raise Refused('proposal operation refused')

class FirstRunProposal:
    HELD={'initialized_delivery_unproven','delivery_observed','initialization_unconfirmed','stop_unconfirmed'}
    def __init__(self,saved=None,clock=time.monotonic):
        self.clock=clock;self.last=-float('inf');self.tickets={};self.runtime={};self.assessment_revision=0
        self.catalog={s:'unknown' for s in SOURCES};self.saved={'version':1,'revision':0,'selected':[]}
        if saved is not None:
            require(type(saved) is dict and set(saved)=={'version','revision','selected'})
            require(type(saved['version']) is int and saved['version']==1 and type(saved['revision']) is int and 0<=saved['revision']<2**63)
            self.selection(saved['selected']);self.saved=copy.deepcopy(saved)
    @staticmethod
    def root(uid):require(type(uid) is int and uid==0)
    @staticmethod
    def selection(values):
        require(type(values) is list and len(values)<=len(SOURCES) and all(type(s) is str and s in SOURCES for s in values) and len(set(values))==len(values))
        return sorted(values)
    def now(self):
        now=self.clock()
        if type(now) not in (int,float) or not self.last<=now<float('inf'):
            self.tickets.clear();raise Refused('invalid clock')
        self.last=now;return now
    def assess(self,catalog):
        require(type(catalog) is dict and set(catalog)==set(SOURCES) and all(v in ('eligible','blocked','unknown','unsupported') for v in catalog.values()))
        self.catalog=copy.deepcopy(catalog);self.assessment_revision+=1;self.tickets.clear()
    def confirm(self,uid,base_revision,assessment_revision,selected):
        self.root(uid);values=self.selection(selected)
        require(type(base_revision) is int and base_revision==self.saved['revision'] and type(assessment_revision) is int and assessment_revision==self.assessment_revision and assessment_revision>0)
        require(not any(r['state'] in self.HELD for r in self.runtime.values()))
        require(all(self.catalog[s]=='eligible' for s in values))
        now=self.now();require(base_revision<2**63-1)
        self.saved=dict(version=1,revision=base_revision+1,selected=values)
        self.tickets.clear();ticket=secrets.token_urlsafe(32)
        self.tickets[ticket]=(self.saved['revision'],self.assessment_revision,now+60)
        return ticket
    def activate(self,uid,ticket,initialize):
        self.root(uid);now=self.now();record=self.tickets.pop(ticket,None)
        require(record is not None and record[:2]==(self.saved['revision'],self.assessment_revision) and now<record[2])
        require(not any(r['state'] in self.HELD for r in self.runtime.values()))
        self.runtime={}
        for source in self.saved['selected']:
            require(self.catalog[source]=='eligible')
            generation=secrets.token_hex(16)
            try:result=initialize(source)
            except Exception:result='unconfirmed'
            state='initialized_delivery_unproven' if result=='initialized' else 'initialization_failed' if result=='refused_clean' else 'initialization_unconfirmed'
            self.runtime[source]=dict(state=state,generation=generation)
        return copy.deepcopy(self.runtime)
    def observe_delivery(self,source,generation):
        r=self.runtime.get(source)
        require(r is not None and r['generation']==generation and r['state'] in ('initialized_delivery_unproven','delivery_observed'))
        r['state']='delivery_observed'
    def stop(self,uid,source,stopper):
        self.root(uid);require(source in self.runtime)
        try:stopped=stopper(source) is True
        except Exception:stopped=False
        self.runtime[source]['state']='stopped' if stopped else 'stop_unconfirmed'
        self.tickets.clear()
    def state(self):
        return dict(confirmed=copy.deepcopy(self.saved),runtime=copy.deepcopy(self.runtime),waiting_for_activation=bool(self.saved['selected']) and not any(r['state'] in self.HELD for r in self.runtime.values()))

class FirstRunDesignTests(unittest.TestCase):
    def setUp(self):
        self.clock=[0.0];self.model=FirstRunProposal(clock=lambda:self.clock[0]);self.model.assess(dict(audit_exec='eligible',proc_lifecycle='eligible',journal_auth='unsupported'));self.calls=[]
    def confirm(self,selected=None):return self.model.confirm(0,self.model.saved['revision'],self.model.assessment_revision,['audit_exec'] if selected is None else selected)
    def initialize(self,source):self.calls.append(source);return 'initialized'
    def start(self,selected=None):return self.model.activate(0,self.confirm(selected),self.initialize)
    def test_confirm_saves_choices_without_starting(self):
        self.confirm();self.assertEqual(self.calls,[]);self.assertEqual(self.model.state()['runtime'],{});self.assertTrue(self.model.state()['waiting_for_activation'])
    def test_empty_choice_starts_nothing(self):
        self.start([]);self.assertEqual(self.calls,[]);self.assertEqual(self.model.runtime,{})
    def test_root_required_for_confirmation(self):
        for uid in (1000,994,True,'0'):
            with self.assertRaises(Refused):self.model.confirm(uid,0,1,['audit_exec'])
        self.assertEqual(self.model.saved['revision'],0)
    def test_root_required_for_activation(self):
        ticket=self.confirm()
        with self.assertRaises(Refused):self.model.activate(1000,ticket,self.initialize)
        self.assertEqual(self.calls,[]);self.model.activate(0,ticket,self.initialize)
    def test_no_unknown_duplicate_path_or_command_choices(self):
        for values in (['audit_exec']*2,['new_source'],['/etc/passwd'],['systemctl start auditd'],None,{'audit_exec':True}):
            with self.subTest(values=values),self.assertRaises(Refused):self.model.confirm(0,0,1,values)
        self.assertEqual(self.calls,[])
    def test_blocked_unknown_and_unsupported_refused(self):
        for state in ('blocked','unknown','unsupported'):
            self.model.assess(dict(audit_exec=state,proc_lifecycle='eligible',journal_auth='unsupported'))
            with self.assertRaises(Refused):self.confirm()
    def test_stale_config_refused_without_changing_saved(self):
        self.confirm();saved=copy.deepcopy(self.model.saved)
        with self.assertRaises(Refused):self.model.confirm(0,0,1,[])
        self.assertEqual(saved,self.model.saved)
    def test_stale_assessment_refused(self):
        self.model.assess(self.model.catalog)
        with self.assertRaises(Refused):self.model.confirm(0,0,1,['audit_exec'])
    def test_boolean_revision_not_integer_revision(self):
        for base,assessment in ((False,1),(0,True)):
            with self.assertRaises(Refused):self.model.confirm(0,base,assessment,[])
    def test_assessment_refresh_never_starts_or_selects(self):
        self.model.assess(dict(audit_exec='eligible',proc_lifecycle='eligible',journal_auth='eligible'));self.assertEqual(self.model.saved['selected'],[]);self.assertEqual(self.calls,[])
    def test_refresh_invalidates_pending_activation(self):
        ticket=self.confirm();self.model.assess(self.model.catalog)
        with self.assertRaises(Refused):self.model.activate(0,ticket,self.initialize)
    def test_ticket_expires_at_boundary(self):
        ticket=self.confirm();self.clock[0]=60
        with self.assertRaises(Refused):self.model.activate(0,ticket,self.initialize)
        self.assertEqual(self.calls,[])
    def test_ticket_single_use(self):
        ticket=self.confirm();self.model.activate(0,ticket,self.initialize)
        with self.assertRaises(Refused):self.model.activate(0,ticket,self.initialize)
        self.assertEqual(self.calls,['audit_exec'])
    def test_forged_ticket_refused(self):
        self.confirm()
        with self.assertRaises(Refused):self.model.activate(0,'forged',self.initialize)
        self.assertEqual(self.calls,[])
    def test_new_confirmation_invalidates_old_ticket(self):
        old=self.confirm();self.confirm([])
        with self.assertRaises(Refused):self.model.activate(0,old,self.initialize)
    def test_restart_retains_choices_but_no_authorization_or_runtime(self):
        ticket=self.confirm();restored=FirstRunProposal(copy.deepcopy(self.model.saved));self.assertEqual(restored.saved['selected'],['audit_exec']);self.assertTrue(restored.state()['waiting_for_activation'])
        with self.assertRaises(Refused):restored.activate(0,ticket,self.initialize)
        self.assertEqual(self.calls,[])
    def test_restore_cannot_inject_running_state_or_commands(self):
        for saved in ({'version':1,'revision':1,'selected':[],'running':True},{'version':1,'revision':1,'selected':['/bin/sh']},{'version':1,'revision':True,'selected':[]},{'version':2,'revision':1,'selected':[]}):
            with self.assertRaises(Refused):FirstRunProposal(saved)
    def test_saved_and_reported_objects_do_not_alias_model(self):
        self.confirm();out=self.model.state();out['confirmed']['selected'].append('journal_auth');self.assertEqual(self.model.saved['selected'],['audit_exec'])
    def test_clean_failure_does_not_block_other_confirmed_source(self):
        def initialize(source):self.calls.append(source);return 'refused_clean' if source=='audit_exec' else 'initialized'
        result=self.model.activate(0,self.confirm(['audit_exec','proc_lifecycle']),initialize);self.assertEqual(self.calls,['audit_exec','proc_lifecycle']);self.assertEqual(result['audit_exec']['state'],'initialization_failed');self.assertEqual(result['proc_lifecycle']['state'],'initialized_delivery_unproven')
    def test_uncertain_cleanup_visible_while_other_source_continues(self):
        def initialize(source):
            if source=='audit_exec':raise OSError('synthetic')
            return 'initialized'
        result=self.model.activate(0,self.confirm(['audit_exec','proc_lifecycle']),initialize);self.assertEqual(result['audit_exec']['state'],'initialization_unconfirmed');self.assertEqual(result['proc_lifecycle']['state'],'initialized_delivery_unproven')
        with self.assertRaises(Refused):self.confirm([])
    def test_unselected_sources_never_initialized(self):
        self.start(['proc_lifecycle']);self.assertEqual(self.calls,['proc_lifecycle']);self.assertNotIn('journal_auth',self.model.runtime)
    def test_initialization_not_delivery_proof(self):
        self.start();self.assertEqual(self.model.runtime['audit_exec']['state'],'initialized_delivery_unproven')
    def test_delivery_requires_matching_active_scope(self):
        self.start();generation=self.model.runtime['audit_exec']['generation']
        with self.assertRaises(Refused):self.model.observe_delivery('audit_exec','old')
        with self.assertRaises(Refused):self.model.observe_delivery('proc_lifecycle',generation)
        self.model.observe_delivery('audit_exec',generation);self.assertEqual(self.model.runtime['audit_exec']['state'],'delivery_observed')
    def test_edit_while_active_refused_preserves_current_subset(self):
        self.start();saved=copy.deepcopy(self.model.saved)
        with self.assertRaises(Refused):self.confirm([])
        self.assertEqual(saved,self.model.saved);self.assertEqual(self.model.runtime['audit_exec']['state'],'initialized_delivery_unproven')
    def test_stop_must_be_root_and_confirmed_before_reselection(self):
        self.start()
        with self.assertRaises(Refused):self.model.stop(1000,'audit_exec',lambda _:True)
        self.model.stop(0,'audit_exec',lambda _:True);self.confirm([]);self.assertEqual(self.model.saved['selected'],[])
    def test_stop_failure_never_fabricates_stopped_state(self):
        self.start();self.model.stop(0,'audit_exec',lambda _:False);self.assertEqual(self.model.runtime['audit_exec']['state'],'stop_unconfirmed')
        with self.assertRaises(Refused):self.confirm([])
    def test_old_delivery_after_stop_refused(self):
        self.start();generation=self.model.runtime['audit_exec']['generation'];self.model.stop(0,'audit_exec',lambda _:True)
        with self.assertRaises(Refused):self.model.observe_delivery('audit_exec',generation)
    def test_no_automatic_retry_after_clean_failure(self):
        ticket=self.confirm();calls=[]
        self.model.activate(0,ticket,lambda s:(calls.append(s),'refused_clean')[1]);self.model.assess(self.model.catalog);self.assertEqual(calls,['audit_exec'])
        with self.assertRaises(Refused):self.model.activate(0,ticket,self.initialize)
    def test_assessment_change_does_not_stop_working_subset(self):
        self.start();self.model.assess(dict(audit_exec='blocked',proc_lifecycle='eligible',journal_auth='unsupported'));self.assertEqual(self.model.runtime['audit_exec']['state'],'initialized_delivery_unproven');self.assertEqual(self.calls,['audit_exec'])
    def test_clock_regression_and_invalid_clocks_refuse_activation(self):
        self.clock[0]=10;ticket=self.confirm();self.clock[0]=9
        with self.assertRaises(Refused):self.model.activate(0,ticket,self.initialize)
        self.assertFalse(self.model.tickets)
        for bad in (float('nan'),float('inf'),True):
            self.clock[0]=bad
            with self.assertRaises(Refused):self.confirm([])

if __name__=='__main__':unittest.main()
