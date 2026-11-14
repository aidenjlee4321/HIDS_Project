"""Root terminal source choice/confirmation; uses the approved setup manager."""
import json
import os
import sys
from api.setup_contract import require


def process_runtime(owned):
    result=dict(available=False)
    entry=owned['instances'].get('proc_lifecycle')
    if entry is None:return result
    try:
        from engine.ingestion import process_control as p
        value=p.c.decode(p.trusted(p.STATUS,4096,0o600))
        base={'version','source','activation','generation','state','backend_exit','collector_exit'}
        witness={'runtime_pid','runtime_invocation'}
        require(type(value['version']) is int and value['version'] in (1,2))
        fields=base if value['version']==1 else base|witness
        require(set(value) in (fields,fields|{'forced'}) and all(value[k]==entry[k] for k in ('source','activation','generation')))
        if value['version']==2:
            import re
            require(type(value['runtime_pid']) is int and value['runtime_pid']>0 and (value['runtime_invocation'] is None or type(value['runtime_invocation']) is str and re.fullmatch('[0-9a-f]{32}',value['runtime_invocation'])))
        require(value['state'] in ('starting','initialized_delivery_unproven','stopped','failed'))
        require('forced' not in value or type(value['forced']) is bool)
        for key in ('backend_exit','collector_exit'):require(value[key] is None or type(value[key]) is int and 0<=value[key]<=255)
        return dict(available=True,last_published_state=value['state'],backend_exit=value['backend_exit'],collector_exit=value['collector_exit'],forced_stop=value.get('forced'),current_monitoring='not_assessed')
    except Exception:return result


def main():
    try:
        require(os.getuid()==os.geteuid()==0 and len(sys.argv)==2 and sys.stdin.isatty() and sys.stdout.isatty())
        op=sys.argv[1];require(op in ('status','start-process','stop'))
        from api.setup_store import root_store
        from api.setup_preflight import assess
        from api.setup_manager import root_lock,manager,Ownership
        with root_lock():
            current=root_store().load()
            if op=='status':
                view=assess(current)
                # Closed, payload-free coverage/status metadata only.
                owned=Ownership().load()
                print(json.dumps(dict(saved_selection=current,owned_intervals=owned,process_runtime=process_runtime(owned),sources=[dict(id=s['id'],preflight=s['preflight'],checks=s['checks']) for s in view['sources']]),indent=2));return 0
            if op=='stop':
                require(input('Stop only this setup\'s owned HIDS instances? Type STOP: ')=='STOP')
                print(json.dumps(manager().stop()));return 0
            print('Retain native process fork/exec/exit metadata in the private bounded store.')
            print('No executable/user enrichment or process detection rule. Activity wall time is unavailable.')
            print('Saved choices never resume collection after restart. No Ubuntu logging settings change.')
            require(input('Save process-only selection and initialize it now? Type START: ')=='START')
            view=assess(current);draft=dict(assessment_id=view['assessment_id'],fingerprint=view['fingerprint'],confirmed=current,selected=['proc_lifecycle'])
            print(json.dumps(manager().confirm(draft)))
        return 0
    except Exception:
        print('HIDS source request refused or outcome unconfirmed. Inspect status; no automatic retry.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
