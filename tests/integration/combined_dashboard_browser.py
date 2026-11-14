"""Ordinary isolated Chromium acceptance; actual security payloads stay in VM."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from playwright.sync_api import sync_playwright,expect

root,tools,binary=map(Path,sys.argv[1:4]);command=json.loads(sys.stdin.readline());home=root/'home';checks={};context=None
report=dict(passed=False,checks=checks,uid=os.getuid())
try:
 home.mkdir(mode=0o700);nss=home/'.local/share/pki/nssdb';nss.mkdir(parents=True,mode=0o700)
 subprocess.run([str(tools/'certutil'),'-N','--empty-password','-d','sql:'+str(nss)],check=True,capture_output=True)
 subprocess.run([str(tools/'certutil'),'-A','-n','hids-leaf','-t','P,,','-i',str(root/'leaf.pem'),'-d','sql:'+str(nss)],check=True,capture_output=True)
 trust=subprocess.check_output([str(tools/'certutil'),'-L','-d','sql:'+str(nss)],text=True);checks['direct_leaf_only']=trust.count('P,,')==1 and 'C,,' not in trust
 with sync_playwright() as p:
  context=p.chromium.launch_persistent_context(str(home/'user-data'),executable_path=str(binary),headless=True,chromium_sandbox=True,ignore_https_errors=False,args=['--enable-automation'],env=dict(os.environ,HOME=str(home),XDG_DATA_HOME=str(home/'.local/share'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache')),timeout=20000)
  try:
   context.add_init_script("""(()=>{const real=window.fetch.bind(window);window.hidsDelay=false;window.hidsWaiting=false;window.fetch=async(...args)=>{const r=await real(...args);if(window.hidsDelay&&String(args[0]).startsWith('/v0/process/events/')){const text=await r.text();window.hidsWaiting=true;await new Promise(resolve=>window.hidsRelease=resolve);return new Response(text,{status:r.status,headers:r.headers});}return r;};})();""")
   page=context.new_page();page.set_default_timeout(10000);cdp=context.new_cdp_session(page)
   args=cdp.send('Browser.getBrowserCommandLine')['arguments'];checks['no_bypass']=not any(a.startswith(('--no-sandbox','--ignore-certificate-errors','--disable-setuid-sandbox','--allow-insecure-localhost')) for a in args)
   page.goto('chrome://sandbox');sandbox=page.locator('body').inner_text();checks['browser_sandbox']='You are adequately sandboxed.' in sandbox and 'Seccomp-BPF sandbox' in sandbox
   base='https://127.0.0.1:18765/';page.goto(base);expect(page.get_by_test_id('status')).to_have_text('Locked')
   checks['unauthenticated_denial']=page.evaluate("Promise.all(['/v0/dashboard','/v0/process/events','/v0/process/events/x','/v0/history','/v0/history/events','/v0/history/findings'].map(p=>fetch(p).then(r=>r.status)))")==[403]*6
   page.goto(command['url']);expect(page.get_by_test_id('status')).to_have_text('Authorized')
   expect(page.get_by_test_id('process-event')).to_have_count(command['counts']['process']);expect(page.get_by_test_id('event')).to_have_count(command['counts']['history']);expect(page.get_by_test_id('finding')).to_have_count(command['counts']['findings'])
   checks['actual_counts']=True;checks['no_persistent_auth']=page.evaluate('[location.hash,document.cookie,localStorage.length,sessionStorage.length]')==['','',0,0]
   page.get_by_test_id('process-event').first.click();expect(page.get_by_test_id('detail').locator('pre')).to_contain_text('"envelope"');detail=json.loads(page.get_by_test_id('detail').locator('pre').inner_text())
   checks['process_time_precision_and_status']=detail['envelope']['timestamps']['activity_wall_time'] is None and type(detail['envelope']['native']['timestamp_ns']) is str and type(detail['arrival_ordinal']) is str and detail['historical_interval']['stopped'] and not detail['historical_interval']['acknowledged']
   page.get_by_test_id('finding').first.click();expect(page.get_by_test_id('detail').locator('pre')).to_contain_text('"finding_id"');finding=json.loads(page.get_by_test_id('detail').locator('pre').inner_text())
   page.get_by_role('button',name='Triggering event',exact=True).click();expect(page.get_by_test_id('detail').locator('pre')).to_contain_text('native_identity');event=json.loads(page.get_by_test_id('detail').locator('pre').inner_text());checks['finding_link_preserved']=event['event_id']==finding['event_id']
   page.screenshot(path=str(root/'authorized.png'),full_page=True)
   page.evaluate('window.hidsDelay=true');page.get_by_test_id('process-event').first.click();page.wait_for_function('window.hidsWaiting===true')
   page.get_by_role('button',name='Log out',exact=True).click();expect(page.get_by_test_id('status')).to_have_text('Locked');page.evaluate('window.hidsRelease()');page.wait_for_timeout(100)
   checks['late_process_response_erased']=page.get_by_test_id('dashboard').count()==0 and page.get_by_test_id('detail').count()==0
   page.goto(command['url']);expect(page.get_by_test_id('status')).to_have_text('Locked');checks['grant_replay_denied']=True
  finally:context.close();context=None
except Exception as e:
 report['error_type']=type(e).__name__
 report['error_operation']=str(e).split(':',1)[0][:80]
 import traceback
 (root/'failure.txt').write_text(traceback.format_exc())
finally:
 if context:context.close()
 # Exactly this invocation's newly created profile. Evidence remains outside it.
 if home.exists():shutil.rmtree(home)
 checks['new_transient_profile_removed']=not home.exists();report['passed']=all(checks.values()) and 'error_type' not in report
 (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(passed=report['passed'],checks=checks,error_type=report.get('error_type'))))
raise SystemExit(0 if report['passed'] else 1)
