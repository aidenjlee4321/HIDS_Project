"""Private ordinary-account browser acceptance; payloads stay in VM evidence."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from playwright.sync_api import sync_playwright,Error,expect
root,tools,binary=map(Path,sys.argv[1:4]);command=json.loads(sys.stdin.readline());checks={};home=root/'home';home.mkdir(mode=0o700);nss=home/'.local/share/pki/nssdb';nss.mkdir(parents=True,mode=0o700)
subprocess.run([str(tools/'certutil'),'-N','--empty-password','-d','sql:'+str(nss)],check=True,capture_output=True)
for name in ('valid','expired','history'):
 subprocess.run([str(tools/'certutil'),'-A','-n',name,'-t','P,,','-i',str(root/(name+'.pem')),'-d','sql:'+str(nss)],check=True,capture_output=True)
trust=subprocess.check_output([str(tools/'certutil'),'-L','-d','sql:'+str(nss)],text=True);(root/'nss-trust.txt').write_text(trust);assert 'C,,' not in trust and trust.count('P,,')==3;checks['direct_peer_trust_no_ca']=True
report={'passed':False,'uid':os.getuid(),'checks':checks}
try:
 with sync_playwright() as p:
  env=dict(os.environ,HOME=str(home),XDG_DATA_HOME=str(home/'.local/share'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'))
  context=p.chromium.launch_persistent_context(str(home/'user-data'),executable_path=str(binary),headless=True,chromium_sandbox=True,ignore_https_errors=False,args=['--enable-automation'],env=env,timeout=20000)
  try:
   # Install before the app captures fetch.bind(window), as in the earlier
   # synthetic pilot regression. A post-load monkeypatch misses that transport.
   context.add_init_script("""(()=>{const real=window.fetch.bind(window);window.hidsDelay=false;window.hidsWaiting=false;window.fetch=async(...args)=>{const r=await real(...args);if(window.hidsDelay&&String(args[0]).startsWith('/v0/history/events/')){const text=await r.text();window.hidsWaiting=true;await new Promise(resolve=>window.hidsRelease=resolve);return new Response(text,{status:r.status,headers:r.headers});}return r;};})();""")
   page=context.new_page();page.set_default_timeout(10000);page.set_default_navigation_timeout(15000)
   cdp=context.new_cdp_session(page);report['version']=cdp.send('Browser.getVersion')['product'];args=cdp.send('Browser.getBrowserCommandLine')['arguments'];checks['no_verification_or_sandbox_bypass']=not any(a.startswith(('--no-sandbox','--ignore-certificate-errors','--disable-setuid-sandbox','--allow-insecure-localhost')) for a in args)
   page.goto('chrome://sandbox');sandbox=page.locator('body').inner_text();(root/'sandbox.txt').write_text(sandbox);checks['browser_sandbox']=all(s in sandbox for s in ('Namespace','Seccomp-BPF sandbox','You are adequately sandboxed.'))
   ports=command['ports']
   for name,url,error in [('foreign','https://127.0.0.1:'+str(ports['foreign'])+'/','ERR_CERT_AUTHORITY_INVALID'),('wrong_name','https://localhost:'+str(ports['valid'])+'/','ERR_CERT_COMMON_NAME_INVALID'),('expired','https://127.0.0.1:'+str(ports['expired'])+'/','ERR_CERT_DATE_INVALID')]:
    probe=context.new_page()
    try:probe.goto(url)
    except Error as exc:checks[name+'_rejected']=error in str(exc)
    else:checks[name+'_rejected']=False
    finally:probe.close()
   base='https://127.0.0.1:18765/'
   probe=context.new_page()
   try:probe.goto('http://127.0.0.1:18765/')
   except Error as exc:checks['plaintext_rejected']=any(s in str(exc) for s in ('ERR_EMPTY_RESPONSE','ERR_CONNECTION_RESET','ERR_SSL_PROTOCOL_ERROR'))
   else:checks['plaintext_rejected']=False
   finally:probe.close()
   page.goto(base);expect(page.get_by_test_id('status')).to_have_text('Locked')
   checks['locked_routes_denied']=page.evaluate("Promise.all(['/v0/history','/v0/history/events','/v0/history/findings','/v0/history/events/'+('a'.repeat(64)),'/v0/history/findings/'+('a'.repeat(64))].map(p=>fetch(p).then(r=>r.status)))")==[403]*5
   page.goto(command['url']);expect(page.get_by_test_id('status')).to_have_text('Authorized');expect(page.get_by_test_id('event')).to_have_count(min(command['counts']['events'],20));expect(page.get_by_test_id('finding')).to_have_count(command['counts']['findings'])
   checks['authorized_counts']=page.get_by_test_id('counts').inner_text()==f"{command['counts']['events']} events · {command['counts']['findings']} informational findings · 16 unevaluated events"
   checks['fragment_and_storage_empty']=page.evaluate('[location.hash,document.cookie,localStorage.length,sessionStorage.length]')==['','',0,0]
   page.get_by_test_id('event').first.click();expect(page.get_by_test_id('detail')).to_be_visible();detail=json.loads(page.get_by_test_id('detail').locator('pre').inner_text());checks['lossless_event_detail']=type(detail['execution']['result']) is str and type(detail['first_offset']) is str and (detail['metadata']['first_observed_unix_ns'] is None or type(detail['metadata']['first_observed_unix_ns']) is str)
   page.get_by_test_id('finding').first.click();expect(page.get_by_test_id('detail').locator('pre')).to_contain_text('"finding_id"');finding=json.loads(page.get_by_test_id('detail').locator('pre').inner_text());checks['finding_explanation_and_rule']=finding['severity']=='informational' and finding['rule_id']=='linux.audit.configured-root-shell' and 'Authorized administration and scripts can match.' in finding['explanation']
   page.get_by_role('button',name='Triggering event',exact=True).first.click();expect(page.get_by_test_id('detail').locator('pre')).to_contain_text('native_identity');linked=json.loads(page.get_by_test_id('detail').locator('pre').inner_text());checks['finding_event_link']=linked['event_id']==finding['event_id'] and linked['evaluation_state']=='matched'
   if command['synthetic']:
    checks['hostile_values_are_literal_text']=page.get_by_test_id('event').filter(has_text='<img').count()>0 and page.locator('img').count()==0 and page.evaluate('window.hidsInjected===undefined')
    page.get_by_role('button',name='Next events',exact=True).click();expect(page.get_by_test_id('event')).to_have_count(5);checks['next_page']=page.get_by_role('button',name='Next events',exact=True).count()==0
   page.screenshot(path=str(root/'authorized.png'),full_page=True)
   # Buffer a completed, authorized HTTP response. Return it only after logout;
   # ignore AbortSignal deliberately so generation checks are actually exercised.
   page.evaluate('()=>{window.hidsWaiting=false;window.hidsDelay=true;}')
   page.get_by_test_id('event').first.click();page.wait_for_function('()=>window.hidsWaiting===true');page.get_by_role('button',name='Log out',exact=True).click();expect(page.get_by_test_id('status')).to_have_text('Locked');page.evaluate('window.hidsRelease()');page.wait_for_timeout(100)
   checks['late_detail_cannot_restore_locked_data']=page.get_by_test_id('history').count()==0 and page.get_by_test_id('detail').count()==0 and page.get_by_test_id('event').count()==0
   page.screenshot(path=str(root/'locked.png'),full_page=True)
   page.goto(command['url']);expect(page.get_by_test_id('status')).to_have_text('Locked');checks['grant_replay_denied']=page.get_by_test_id('history').count()==0
   (root/'ready-impostor').write_text('ready')
   end=time.monotonic()+30
   while not (root/'impostor-ready').exists() and time.monotonic()<end:time.sleep(.05)
   assert (root/'impostor-ready').exists()
   probe=context.new_page()
   try:probe.goto(base)
   except Error as exc:checks['stopped_port_impostor_rejected']='ERR_CERT_AUTHORITY_INVALID' in str(exc)
   else:checks['stopped_port_impostor_rejected']=False
   finally:probe.close()
   report['passed']=all(checks.values())
  finally:context.close()
except Exception as exc:report.update(error_type=type(exc).__name__,error=re.sub(r'#grant=[A-Za-z0-9_-]+','#grant=<redacted>',str(exc)[-1200:]))
finally:
 (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':report['passed'],'checks':checks,'error_type':report.get('error_type')}),flush=True)
raise SystemExit(0 if report['passed'] else 1)
