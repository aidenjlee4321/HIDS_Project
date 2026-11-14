"""Explicit synthetic-path or approved bounded live M3→M4 Ubuntu acceptance.

Never installs a production unit. Live phase restores temporary Audit setup and
retains every old/new event database. Run only from a verified source snapshot.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests/integration')]
import dev
from m3_rotation_ubuntu import inventory,preserved,restore_all,run,settings
from m3_runtime_ubuntu_acceptance import control,query,until
from m4_handoff_ubuntu import PRODUCER,receive
from engine.detection.m4_service import POLICY
from engine.detection.m4_rules import REFERENCE
from engine.detection.m4_pilot import digest as content_digest

PRODUCER_RULE = PRODUCER.replace("scope['generation']=r.activate(scope['activation'])['generation']", """scope['generation']=r.activate(scope['activation'])['generation']
from engine.detection.m4_handoff import Store
from engine.detection.m4_service import LiveStore,LiveSource
from engine.ingestion.m1_contract import utc_now
from engine.detection.m4_pilot import digest
old=dict(scope)
e0=load_json(Path.cwd()/'tests/fixtures/m4/execution.json')['execution']
for n in range(1,17):
 r.progress.register('1.001:'+str(n),(n-1)*10,n*10,eoe=True)
 r.progress.accept('1.001:'+str(n),e0,observation=dict(version=1,arch=ARCH,profile=PROFILE,first_observed_unix_ns=123))
source=LiveSource.__new__(LiveSource);source.directory=root/'source';source.scope=old;source.key=digest(source.BINDING_DOMAIN,old)
s=LiveStore.__new__(LiveStore);Store.__init__(s,root/'state'/'store',create=True,max_pages=512,storage=m3_storage.defaults(512,1),lab_only=False)
s.import_page(source);s.import_page(source);s.close();r.revoke(old['activation'])
scope['activation']=__import__('uuid').uuid4().__str__();scope['generation']=r.activate(scope['activation'])['generation']
scope['legacy_scope']=old""").replace("e=load_json(Path.cwd()/'tests/fixtures/m4/execution.json')['execution']", "e=load_json(Path.cwd()/'tests/fixtures/m4/execution.json')['execution'];e.update(euid=0,exe_base64='L3Vzci9iaW4vZGFzaA==')")

UNITS=('hids-m3.socket','hids-m3.service','hids-m3-health.timer','hids-m3-health.service')
CONFIG=Path('/etc/hids/m4.json')
M4=Path('/var/lib/hids/m4')
M3=Path('/var/lib/hids/m3')


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('synthetic','live'),required=True)
    parser.add_argument('--expected-manifest',required=True)
    parser.add_argument('--live-audit',action='store_true')
    parser.add_argument('--rule',action='store_true',help='Approved schema-v2 finding scope; preserves v1 historical events')
    parser.add_argument('--recovery',action='store_true',help='Four actual v2 worker SIGKILL boundaries; synthetic scope only')
    parser.add_argument('--budgets',action='store_true',help='Real pinned-WAL and retained-backup pressure; synthetic rule scope only')
    args=parser.parse_args()
    assert not args.budgets or (args.phase=='synthetic' and args.rule),'budget probe requires synthetic rule scope'
    assert not args.recovery or (args.phase=='synthetic' and args.rule),'recovery injection requires synthetic rule scope'
    assert os.getuid()==0 and sys.platform=='linux'
    assert args.phase!='live' or args.live_audit
    dev.verify(ROOT,args.expected_manifest)
    assert all(run('systemctl','show',u,'-p','ActiveState','--value').stdout.strip()==b'inactive' for u in UNITS)
    assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
    assert not CONFIG.exists() and not CONFIG.is_symlink(),'existing M4 config must not be replaced'
    lock=os.open('/run/lock/hids-m3-workflow.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    root=Path(tempfile.mkdtemp(prefix='hids-m4-handoff.',dir='/var/tmp'));root.chmod(0o711)
    report=dict(phase=args.phase,result='running',source_manifest=args.expected_manifest,root=str(root),workers=[])
    producer=None;producer_log=None;unit=None;child=None;release=None;rule=None;plugin_created=False;activated=False;config_created=False
    audit_config=Path('/etc/audit/auditd.conf');original=audit_config.read_bytes();plugin=Path('/etc/audit/plugins.d/hids-m4-trial.conf')
    baseline_policy={str(p):digest(p) for p in [audit_config,*sorted(Path('/etc/audit/plugins.d').glob('*.conf'))]}
    original_rules=run('auditctl','-l').stdout
    old_names={p.name for p in M3.glob('*.sqlite')};old_events={p.name:digest(p) for p in M3.glob('*.sqlite') if p.name!='control.sqlite'}
    audit_settings=settings(original);active=Path(audit_settings['log_file']);before=inventory(active)
    report.update(original_databases=len(old_names),source_before=before)
    account=pwd.getpwnam('hids-ingest')
    def interrupted(*_):
        signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.signal(signal.SIGHUP,signal.SIG_IGN)
        raise InterruptedError('trial interrupted; restoring baseline')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
    def save():
        p=root/'report.json';p.write_text(json.dumps(report,sort_keys=True)+'\n');p.chmod(0o600)
    def write_config(scope):
        nonlocal config_created
        value=dict(version=2 if args.rule else 1,enabled=True,**scope,max_pages=512,storage=POLICY,max_events=(2 if args.phase=='synthetic' else 3) if args.rule else 16,max_seconds=120)
        if args.rule:value['rules']=[dict(REFERENCE)]
        data=dev.json_bytes(value)
        if not config_created:
            fd=os.open(CONFIG,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o640);config_created=True
            with os.fdopen(fd,'wb') as stream:stream.write(data)
        else:CONFIG.write_bytes(data)
        os.chown(CONFIG,0,account.pw_gid);CONFIG.chmod(0o640)
        (root/'selected-config.json').write_bytes(data);(root/'selected-config.json').chmod(0o600)
    def owner_query(path,sql,parameters=()):
        uid,gid=os.geteuid(),os.getegid();db=None
        try:
            os.setegid(account.pw_gid);os.seteuid(account.pw_uid)
            db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            return db.execute(sql,parameters).fetchall()
        finally:
            if db:db.close()
            os.seteuid(uid);os.setegid(gid)
    try:
        code=root/ROOT.name;shutil.copytree(ROOT,code)
        for parent,dirs,files in os.walk(code):
            Path(parent).chmod(0o755)
            for name in files:(Path(parent)/name).chmod(0o644)
        dev.verify(code,args.expected_manifest)
        for name in ('source','state'):
            p=root/name;p.mkdir(mode=0o700);os.chown(p,account.pw_uid,account.pw_gid)
        if not M4.exists():M4.mkdir(mode=0o700);os.chown(M4,account.pw_uid,account.pw_gid)
        s=M4.stat();assert s.st_uid==account.pw_uid and stat.S_IMODE(s.st_mode)==0o700
        if args.phase=='live' and not args.rule:assert not (M4/'store').exists(),'first live destination must be fresh'
        def worker(expect_success=True,migration=False,crash=None,budgets=False):
            nonlocal unit
            unit='hids-m4-trial-'+uuid.uuid4().hex[:12]
            properties=dict(User='hids-ingest',Group='hids-ingest',SupplementaryGroups='',WorkingDirectory=str(code),
                UMask='0077',NoNewPrivileges='yes',CapabilityBoundingSet='',AmbientCapabilities='',ProtectSystem='strict',
                ProtectHome='yes',PrivateDevices='yes',ProtectKernelTunables='yes',ProtectKernelModules='yes',
                ProtectControlGroups='yes',RestrictSUIDSGID='yes',RestrictAddressFamilies='AF_UNIX',LimitCORE='0',
                ReadOnlyPaths=str(M3),ReadWritePaths=str(M4),InaccessiblePaths='/run/hids/m3')
            if args.phase=='synthetic':
                properties.update(BindReadOnlyPaths=str(root/'source')+':'+str(M3),BindPaths=str(root/'state')+':'+str(M4))
            if migration:
                # This short maintenance process must drop UID before reading data.
                # On this target the seccomp-derived settings remove CAP_SETUID.
                # Keep its mount restrictions, NNP and only SETUID/SETGID; the
                # application worker retains every original sandbox restriction.
                properties.update(User='root',Group='root',CapabilityBoundingSet='CAP_SETUID CAP_SETGID',
                    RestrictSUIDSGID='no',PrivateDevices='no',ProtectKernelTunables='no',
                    ProtectKernelModules='no')
                properties.pop('RestrictAddressFamilies',None)
            argv=['systemd-run','--quiet','--wait','--collect','--pipe','--unit',unit]
            for k,v in properties.items():argv+=['--property',k+'='+v]
            if budgets:
                assert args.budgets and args.phase=='synthetic' and args.rule and not migration and not crash
                argv+=[sys.executable,'-B',str(code/'tests/integration/m4_budget_probe.py'),'--root',str(root),'--scope',json.dumps(scope)]
            elif crash:
                # Test-only wrapper; the normal service has no fault-injection flag.
                assert args.recovery and args.phase=='synthetic' and not migration
                injected="""import os,sys,signal,json
from contextlib import contextmanager
from engine.detection.m4_rule_store import RuleStore
from engine.detection.m4_service import main
original=RuleStore.transaction
selected=(int(sys.argv[1]),sys.argv[2])
count=0
@contextmanager
def transaction(self):
 global count
 count+=1
 target,when=selected
 with original(self):
  yield
  if count==target and when=='before':
   print(json.dumps(dict(fault=when,transaction=count)),flush=True);os.kill(os.getpid(),signal.SIGKILL)
 if count==target and when=='after':
  print(json.dumps(dict(fault=when,transaction=count)),flush=True);os.kill(os.getpid(),signal.SIGKILL)
RuleStore.transaction=transaction
sys.argv=['m4_service','--once']
raise SystemExit(main())
"""
                argv+=[sys.executable,'-B','-c',injected,str(crash[0]),crash[1]]
            else:
                argv+=[sys.executable,'-B','-m','engine.detection.m4_migrate','--apply'] if migration else [sys.executable,'-B','-m','engine.detection.m4_service','--once']
            result=subprocess.run(argv,text=True,capture_output=True,timeout=40 if budgets else 20)
            index=len(report['workers'])
            for suffix,data in (('stdout',result.stdout),('stderr',result.stderr)):
                p=root/(f'worker-{index}.'+suffix);p.write_text(data);p.chmod(0o600)
            report['workers'].append(dict(exit_code=result.returncode));save()
            assert (result.returncode==0)==expect_success,'worker result differs; private logs retained'
            status=json.loads(result.stdout.strip().splitlines()[-1]);report['workers'][-1]['status']=status
            if crash:assert status==dict(fault=crash[1],transaction=crash[0]),'worker did not reach intended crash boundary'
            unit=None;save();return status
        scope=dict(source=str(uuid.uuid4()),activation=str(uuid.uuid4()))
        if args.phase=='synthetic':
            producer_log=(root/'producer.stderr').open('x');os.chmod(producer_log.name,0o600)
            producer=subprocess.Popen([sys.executable,'-B','-c',PRODUCER_RULE if args.rule else PRODUCER,str(root),json.dumps(scope)],cwd=code,
                env={**os.environ,'PYTHONPATH':str(code),'PYTHONDONTWRITEBYTECODE':'1'},user=account.pw_uid,group=account.pw_gid,extra_groups=[],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=producer_log,text=True,start_new_session=True)
            scope=receive(producer.stdout);legacy=scope.pop('legacy_scope',None);write_config(scope)
            if args.rule:
                migration=worker(migration=True);assert migration['version']==2
                write_config(legacy);worker(False);write_config(scope)
            # Real root mode/selection checks, before any live path access.
            CONFIG.chmod(0o644);worker(False);CONFIG.chmod(0o640)
            bad=dict(scope,generation=str(uuid.uuid4()));write_config(bad);worker(False);write_config(scope)
            if args.recovery:
                destination=root/'state'/'store'/'handoff.sqlite'
                report['crash_boundaries']=[]
                for transaction,when,events,pending,alerts in ((1,'before',16,0,0),(1,'after',17,1,0),(2,'before',17,1,0),(2,'after',17,0,1)):
                    worker(False,crash=(transaction,when))
                    assert owner_query(destination,'SELECT count(*) FROM m4h_events')==[(events,)]
                    assert owner_query(destination,"SELECT count(*) FROM m4h_evaluations WHERE state='pending'")==[(pending,)]
                    assert owner_query(destination,'SELECT count(*) FROM m4h_alerts')==[(alerts,)]
                    assert owner_query(destination,'PRAGMA integrity_check')==[('ok',)]
                    assert owner_query(destination,'PRAGMA foreign_key_check')==[]
                    report['crash_boundaries'].append(dict(transaction=transaction,when=when,events=events,pending=pending,alerts=alerts));save()
            first=worker();assert first['events']==(17 if args.rule else 1) and first['unevaluated']==(16 if args.rule else 1) and not first['lab_only']
            producer.stdin.write('{"command":"accept_a"}\n');producer.stdin.flush();assert receive(producer.stdout)==dict(accepted=True)
            # Recovery retries may already have advanced into the next sweep.
            assert worker()['events'] in ((17,18) if args.rule else (1,2))
            assert worker()['events']==(18 if args.rule else 2)
            final=worker();assert final['events']==(18 if args.rule else 2) and final['alerts']==(2 if args.rule else 0)
            destination=root/'state'/'store'/'handoff.sqlite'
            assert owner_query(destination,'PRAGMA application_id')==[(0x48344c31,)]
            if args.rule:
                assert owner_query(destination,'SELECT COUNT(*) FROM m4h_bindings WHERE rule_plan=\'[]\'')==[(1,)]
                report.update(old_plan_backfill_refused=True,old_events_unevaluated=16,non_demo_findings=2)
            if args.budgets:report['budget_probe']=worker(budgets=True);assert report['budget_probe']['result']=='passed'
            report.update(real_shaped_synthetic=True,events=final['events'],late_A_preserved=True,root_mode_refused=True,wrong_generation_refused=True)
        else:
            assert original_rules.strip()==b'No rules' and not plugin.exists() and not plugin.is_symlink()
            ceiling=int(audit_settings['max_log_file'])*1024*1024
            assert ceiling-active.stat().st_size>=2*1024*1024,'source retention headroom insufficient'
            state_config=json.loads(Path('/etc/hids/m3.json').read_text());assert len(old_names)-1<state_config['max_activations']
            scope['source']=state_config['source_id']
            run('systemctl','start','hids-m3.socket');control('activate',scope['activation']);activated=True
            fd=os.open(plugin,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o640);plugin_created=True
            with os.fdopen(fd,'w') as stream:stream.write('active = yes\npath = /usr/lib/hids/hids-audit-launcher\ntype = always\nformat = string\n')
            raw,count=re.subn(rb'(?m)^\s*log_format\s*=.*$',b'log_format = RAW',original);assert count==1
            audit_config.write_bytes(raw);run('auditctl','--signal','reload');until(lambda:control('status')['source_ready'])
            initial=control('status');scope['generation']=initial['interval']['generation'];write_config(scope)
            kernel_before=run('auditctl','-s').stdout;start=time.monotonic();deadline=start+120
            targets=[]
            old_m4=owner_query(M4/'store'/'handoff.sqlite','SELECT * FROM m4h_events ORDER BY event_key') if args.rule else []
            if args.rule:
                assert len(old_m4)==16 and owner_query(M4/'store'/'handoff.sqlite','PRAGMA user_version')==[(2,)]
                assert owner_query(M4/'store'/'handoff.sqlite','SELECT count(*) FROM m4h_alerts')==[(0,)]
            cases=[('/usr/bin/dash',['dash','-c','exit 0'],0),('/usr/bin/dash',['dash','-c','exit 0'],pwd.getpwnam('nobody').pw_uid),('/usr/bin/true',['true'],0)] if args.rule else [('/usr/bin/true',['true'],0)]*16
            for executable,arguments,uid in cases:
                assert time.monotonic()<deadline
                read,release=os.pipe();child=os.fork()
                if child==0:
                    os.close(release);os.read(read,1);os.close(read)
                    if uid:
                        nobody=pwd.getpwnam('nobody');os.setgroups([]);os.setgid(nobody.pw_gid);os.setuid(uid)
                    os.execve(executable,arguments,{})
                os.close(read);target=child;targets.append(target)
                rule=['always,exit','-F','arch=b64','-S','execve','-F',f'pid={target}','-k','hids_m4_trial']
                run('auditctl','-a',*rule);os.write(release,b'x');os.close(release);release=None
                _,status=os.waitpid(child,0);child=None;assert status==0
                run('auditctl','-d',*rule);rule=None
            while time.monotonic()<deadline:
                executions=query(scope['activation'],'SELECT identity,payload FROM m3_execution')
                if len(executions)==len(cases):break
                time.sleep(.1)
            else:raise TimeoutError('live M3 delivery incomplete')
            assert {json.loads(p)['pid'] for _,p in executions}==set(targets)
            first=worker();second=worker()
            destination=M4/'store'/'handoff.sqlite'
            if args.rule:
                assert first['events']==second['events']==19 and second['unevaluated']==16
                assert second['alerts']==1 and second['pending']==0
                assert second['evaluations']=={'matched':1,'no_match':2}
                current=dict((r[0],r) for r in owner_query(destination,'SELECT * FROM m4h_events'))
                assert all(current[r[0]]==r for r in old_m4)
                alert=owner_query(destination,'SELECT demo,severity,explanation FROM m4h_alerts')
                assert len(alert)==1 and alert[0][:2]==(0,'informational') and 'identity is unavailable' in alert[0][2]
                assert owner_query(destination,"SELECT count(*) FROM m4h_evaluations v JOIN m4h_events e USING(event_key) JOIN m4h_bindings b USING(binding_key) WHERE b.rule_plan='[]'")==[(0,)]
                report.update(old_16_events_unchanged=True,old_16_unevaluated=True,non_demo_findings=1,nonmatches=2)
            else:
                assert first['events']==second['events']==16 and second['unevaluated']==16
                assert second['alerts']==0 and second['pending']==0
            imported=owner_query(destination,'SELECT envelope FROM m4h_events WHERE binding_key=?',(content_digest('hids.m4.live.binding/1',scope),))
            assert len(imported)==len(cases)
            expected=dict(executions)
            metadata={row[0]:row[1:] for row in query(scope['activation'],'SELECT identity,format,arch,collector_profile,first_observed_unix_ns,received_at,persistence_started_at FROM m3_event_metadata')}
            for (payload,) in imported:
                event=json.loads(payload);assert event['origin']=='audit_plugin' and event['source']==scope['source']
                assert event['activation']==scope['activation'] and event['generation']==scope['generation']
                assert event['execution']==json.loads(expected[event['identity']])
                assert tuple(event['metadata'][k] for k in ('format','arch','profile','first_observed_unix_ns','received_at','persistence_started_at'))==metadata[event['identity']]
            def counter(data,key):return next(line.split()[1] for line in data.splitlines() if line.startswith(key+b' '))
            after=run('auditctl','-s').stdout
            assert counter(after,b'lost')==counter(kernel_before,b'lost') and counter(after,b'pid')==counter(kernel_before,b'pid')
            assert owner_query(destination,'PRAGMA integrity_check')==[('ok',)]
            assert owner_query(destination,'PRAGMA foreign_key_check')==[]
            assert owner_query(destination,'SELECT count(*) FROM m4h_rules')==[(1 if args.rule else 0,)]
            report.update(real_kernel_events=len(cases),imported=len(cases),unevaluated=16,alerts=1 if args.rule else 0,deduplicated_restart=True,
                normalized_payload_and_metadata_equal=True,scope=scope,elapsed_seconds=round(time.monotonic()-start,3))
            assert time.monotonic()<deadline
        dev.verify(code,args.expected_manifest);report['result']='passed'
    finally:
        def stop_unit():
            if unit:subprocess.run(['systemctl','stop',unit],capture_output=True,timeout=20)
        def stop_producer():
            if producer:
                if producer.poll() is None:
                    producer.stdin.write('{"command":"stop"}\n');producer.stdin.flush();producer.wait(timeout=10)
                producer.stdin.close();producer.stdout.close()
            if producer_log is not None:producer_log.close()
        def finish_child():
            if release is not None:os.close(release)
            if child:
                try:os.kill(child,signal.SIGKILL)
                except ProcessLookupError:pass
                os.waitpid(child,0)
        def revoke():
            if activated:
                try:control('deactivate',scope['activation'])
                except Exception:pass
        def verify():
            assert {str(p):digest(p) for p in [audit_config,*sorted(Path('/etc/audit/plugins.d').glob('*.conf'))]}==baseline_policy
            assert run('auditctl','-l').stdout==original_rules
            preserved(before,inventory(active))
            assert all((M3/name).exists() and digest(M3/name)==value for name,value in old_events.items())
            assert old_names<={p.name for p in M3.glob('*.sqlite')}
            assert run('systemctl','is-active','auditd').stdout.strip()==b'active'
            assert all(run('systemctl','show',u,'-p','ActiveState','--value').stdout.strip()==b'inactive' for u in UNITS)
        try:
            restore_all([('trial unit',stop_unit),('producer',stop_producer),('child',finish_child),
                ('rule',lambda:run('auditctl','-d',*rule) if rule else None),('activation',revoke),
                ('plugin',lambda:plugin.unlink(missing_ok=True) if plugin_created else None),
                ('Audit config',lambda:audit_config.write_bytes(original) if args.phase=='live' else None),
                ('Audit reload',lambda:run('auditctl','--signal','reload') if args.phase=='live' else None),
                ('M3 units',lambda:run('systemctl','stop',*UNITS) if activated else None),
                ('temporary root config',lambda:CONFIG.unlink() if config_created else None),('preservation',verify)])
            report['restoration']='verified'
        except BaseException:
            report['result']='failed';report['restoration']='needs_attention'
            raise
        finally:
            if report['result']!='passed':report['result']='failed'
            report['database_count_after']=len(list(M3.glob('*.sqlite')));save();os.close(lock)
            print('Private trial report '+str(root/'report.json'),flush=True)
    print(json.dumps({k:report.get(k) for k in ('phase','result','restoration','events','imported','unevaluated','alerts','elapsed_seconds')},sort_keys=True))


if __name__=='__main__':main()
