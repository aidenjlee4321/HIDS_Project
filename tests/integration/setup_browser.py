"""Ordinary-user setup browser; only private VM files transfer draft references."""
import json,os,re,subprocess,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root,tools,binary=map(Path,sys.argv[1:4]);command=json.loads(sys.stdin.readline());checks={};report=dict(passed=False,checks=checks,uid=os.getuid())
def waitfile(name,seconds=30):
 end=time.monotonic()+seconds
 while not (root/name).exists() and time.monotonic()<end:time.sleep(.05)
 assert (root/name).exists();return json.loads((root/name).read_text())
def save(name,value):
 p=root/name;p.write_text(json.dumps(value));p.chmod(0o600)
try:
 home=root/'home';home.mkdir(mode=0o700);nss=home/'.local/share/pki/nssdb';nss.mkdir(parents=True,mode=0o700)
 subprocess.run([str(tools/'certutil'),'-N','--empty-password','-d','sql:'+str(nss)],check=True,capture_output=True)
 subprocess.run([str(tools/'certutil'),'-A','-n','setup-leaf','-t','P,,','-i',str(root/'leaf.pem'),'-d','sql:'+str(nss)],check=True,capture_output=True)
 trust=subprocess.check_output([str(tools/'certutil'),'-L','-d','sql:'+str(nss)],text=True);(root/'nss-trust.txt').write_text(trust);checks['peer_trust_without_ca']='C,,' not in trust and trust.count('P,,')==1
 with sync_playwright() as p:
  context=p.chromium.launch_persistent_context(str(home/'user-data'),executable_path=str(binary),headless=True,chromium_sandbox=True,ignore_https_errors=False,args=['--enable-automation'],env=dict(os.environ,HOME=str(home),XDG_DATA_HOME=str(home/'.local/share'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache')),timeout=20000)
  try:
   context.add_init_script("""(()=>{const real=window.fetch.bind(window);window.hidsDelay=false;window.hidsWaiting=false;window.fetch=async(...args)=>{const r=await real(...args);if(window.hidsDelay&&String(args[0])==='/v0/setup/draft'){const text=await r.text();window.hidsWaiting=true;await new Promise(resolve=>window.hidsRelease=resolve);return new Response(text,{status:r.status,headers:r.headers});}return r;};})();""")
   page=context.new_page();page.set_default_timeout(10000);cdp=context.new_cdp_session(page);args=cdp.send('Browser.getBrowserCommandLine')['arguments'];checks['no_verification_or_sandbox_bypass']=not any(a.startswith(('--no-sandbox','--ignore-certificate-errors','--disable-setuid-sandbox','--allow-insecure-localhost')) for a in args)
   page.goto('chrome://sandbox');sandbox=page.locator('body').inner_text();(root/'sandbox.txt').write_text(sandbox);checks['browser_sandbox']='You are adequately sandboxed.' in sandbox and 'Namespace' in sandbox
   base='https://127.0.0.1:18765/';page.goto(base);expect(page.get_by_test_id('status')).to_have_text('Locked');checks['unauthenticated_denial']=page.evaluate("fetch('/v0/setup').then(r=>r.status)")==403
   page.goto(command['url']);expect(page.get_by_test_id('status')).to_have_text('Authorized');expect(page.get_by_test_id('saved-selection')).to_contain_text('revision '+str(command['revision']));checks['authorized_snapshot']=page.locator('input[type=checkbox]').count()==3
   checks['fragment_and_storage_empty']=page.evaluate('[location.hash,document.cookie,localStorage.length,sessionStorage.length]')==['','',0,0]
   for id in ('proc_lifecycle','journal_auth'):assert page.get_by_test_id('source-'+id).is_disabled()
   checks['unvalidated_sources_disabled']=True
   if command['synthetic']:assert page.get_by_test_id('source-audit_exec').is_checked();page.get_by_test_id('source-audit_exec').uncheck()
   else:assert page.get_by_test_id('source-audit_exec').is_disabled()
   if command['synthetic']:
    page.get_by_role('button',name='Prepare root review',exact=True).click();expect(page.get_by_test_id('review-reference')).to_be_visible();expired=page.get_by_test_id('review-reference').inner_text();save('ready-expiry.json',dict(reference=expired))
    expect(page.get_by_test_id('review-reference')).to_have_count(0,timeout=65000);page.wait_for_timeout(1100);save('expiry-complete.json',dict(cleared=True));waitfile('expiry-verified.json');checks['actual_draft_ttl_and_display_clear']=True
   page.get_by_role('button',name='Prepare root review',exact=True).click();expect(page.get_by_test_id('review-reference')).to_be_visible();old=page.get_by_test_id('review-reference').inner_text()
   page.get_by_role('button',name='Prepare root review',exact=True).click();expect(page.get_by_test_id('review-reference')).not_to_have_text(old);reference=page.get_by_test_id('review-reference').inner_text();save('ready-confirm.json',dict(reference=reference,old_reference=old))
   result=waitfile('confirmed.json');checks['root_confirmation_saved_empty_selection']=result['selected']==[] and result['states']=={}
   page.screenshot(path=str(root/'setup.png'),full_page=True)
   page.evaluate('()=>{window.hidsDelay=true;window.hidsWaiting=false;}');page.get_by_role('button',name='Prepare root review',exact=True).click();page.wait_for_function('()=>window.hidsWaiting===true');page.get_by_role('button',name='Log out',exact=True).click();expect(page.get_by_test_id('status')).to_have_text('Locked');page.evaluate('window.hidsRelease()');page.wait_for_timeout(100)
   checks['late_draft_cannot_restore_locked_data']=page.get_by_test_id('setup').count()==0 and page.get_by_test_id('review-reference').count()==0
   page.goto(command['url']);expect(page.get_by_test_id('status')).to_have_text('Locked');checks['grant_replay_refused']=page.get_by_test_id('setup').count()==0
   save('ready-restart.json',dict(ready=True));new=waitfile('new-session.json');page.goto(new['url']);expect(page.get_by_test_id('status')).to_have_text('Authorized');expect(page.get_by_test_id('saved-selection')).to_contain_text('revision '+str(new['revision']));checks['restart_retains_choices_without_activation']=not page.get_by_test_id('source-audit_exec').is_checked()
   page.reload();expect(page.get_by_test_id('status')).to_have_text('Locked');checks['refresh_requires_new_root_link']=page.get_by_test_id('setup').count()==0
   checks['no_http_collection_control']=page.evaluate("Promise.all(['/v0/setup/start','/v0/setup/stop','/v0/setup/confirm','/v0/history','/v0/pilot'].map(p=>fetch(p).then(r=>r.status)))")==[404]*5
   report['passed']=all(checks.values())
  finally:context.close()
except Exception as exc:report.update(error_type=type(exc).__name__,error=re.sub(r'#grant=[A-Za-z0-9_-]+','#grant=<redacted>',str(exc)[-1000:]))
finally:save('report.json',report);print(json.dumps(dict(passed=report['passed'],checks=checks,error_type=report.get('error_type'))),flush=True)
raise SystemExit(0 if report['passed'] else 1)
