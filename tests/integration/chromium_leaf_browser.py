"""Direct-leaf Chromium comparison. New HOME/NSS and user-data directory only."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from playwright.sync_api import sync_playwright, Error, expect
root=Path(sys.argv[1]);tools=Path(sys.argv[2]);ports=json.loads(sys.argv[3]);binary=Path(sys.argv[4]);checks={}
# Chromium's Linux trust DB is shared by HOME, not isolated by user-data-dir.
# Use a wholly new HOME and XDG paths; never touch the normal user's NSS DB.
home=root/'home';home.mkdir(mode=0o700);nss=home/'.local/share/pki/nssdb';nss.mkdir(parents=True,mode=0o700)
subprocess.run([str(tools/'certutil'),'-N','--empty-password','-d','sql:'+str(nss)],check=True,capture_output=True)
for name in ('valid','expired'):
 subprocess.run([str(tools/'certutil'),'-A','-n','synthetic-'+name,'-t','P,,','-i',str(root/(name+'.pem')),'-d','sql:'+str(nss)],check=True,capture_output=True)
trust=subprocess.check_output([str(tools/'certutil'),'-L','-d','sql:'+str(nss)],text=True);(root/'nss-trust.txt').write_text(trust)
assert 'C,,' not in trust and trust.count('P,,')==2
checks['peer_only_trust_no_ca']=True
env=dict(os.environ,HOME=str(home),XDG_DATA_HOME=str(home/'.local/share'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'))
report={'passed':False,'checks':checks,'uid':os.getuid()}
try:
 with sync_playwright() as p:
  context=p.chromium.launch_persistent_context(str(home/'user-data'),executable_path=str(binary),headless=True,chromium_sandbox=True,ignore_https_errors=False,args=['--enable-automation'],env=env,timeout=20000)
  try:
   page=context.new_page();page.set_default_navigation_timeout(15000)
   # Verify actual browser launch args: no certificate or sandbox bypass.
   cdp=context.new_cdp_session(page);report['version']=cdp.send('Browser.getVersion')['product'];args=cdp.send('Browser.getBrowserCommandLine')['arguments']
   assert not any(x.startswith(('--ignore-certificate-errors','--allow-insecure-localhost','--no-sandbox','--disable-setuid-sandbox')) for x in args)
   checks['no_tls_or_sandbox_bypass']=True
   response=page.goto('https://127.0.0.1:'+str(ports['valid'])+'/')
   checks['trusted_leaf_verified']=response.status==200 and page.locator('body').inner_text()=='TLS synthetic only'
   for name,url,expected in (
    ('foreign_leaf_rejected','https://127.0.0.1:'+str(ports['foreign'])+'/','ERR_CERT_AUTHORITY_INVALID'),
    ('wrong_name_rejected','https://localhost:'+str(ports['valid'])+'/','ERR_CERT_COMMON_NAME_INVALID'),
    ('expired_trusted_leaf_rejected','https://127.0.0.1:'+str(ports['expired'])+'/','ERR_CERT_DATE_INVALID')):
    probe=context.new_page();probe.set_default_navigation_timeout(15000)
    try:probe.goto(url)
    except Error as exc:checks[name]=expected in str(exc)
    else:checks[name]=False
    finally:probe.close()
   probe=context.new_page();probe.set_default_navigation_timeout(15000)
   try:probe.goto('http://127.0.0.1:'+str(ports['valid'])+'/')
   except Error as exc:checks['plaintext_rejected']=any(x in str(exc) for x in ('ERR_EMPTY_RESPONSE','ERR_CONNECTION_RESET','ERR_SSL_PROTOCOL_ERROR'))
   else:checks['plaintext_rejected']=False
   finally:probe.close()
   sandbox_page=context.new_page();sandbox_page.goto('chrome://sandbox');sandbox=sandbox_page.locator('body').inner_text();sandbox_page.close();(root/'sandbox.txt').write_text(sandbox)
   statuses={line.split('\t',1)[0].strip():line.split('\t',1)[1].strip() for line in sandbox.splitlines() if '\t' in line}
   checks['namespace_and_seccomp_reported']=(statuses.get('Layer 1 Sandbox')=='Namespace' and statuses.get('PID namespaces')=='Yes' and statuses.get('Network namespaces')=='Yes' and statuses.get('Seccomp-BPF sandbox')=='Yes' and 'You are adequately sandboxed.' in sandbox)
   page.goto('https://127.0.0.1:'+str(ports['valid'])+'/');checks['valid_after_negatives']=page.locator('body').inner_text()=='TLS synthetic only'
   command=json.loads(sys.stdin.readline() or '{}')
   if command:
    url=command['url'];base='https://127.0.0.1:'+str(ports['api'])+'/'
    assert url.startswith(base+'#grant=')
    page.goto(base);expect(page.get_by_test_id('status')).to_have_text('Locked')
    checks['https_api_unauthenticated_denied']=page.evaluate("fetch('/v0/pilot').then(r=>r.status)")==403
    page.goto(url);expect(page.get_by_test_id('status')).to_have_text('Authorized')
    checks['https_root_grant_authorized']=page.get_by_test_id('example').inner_text().startswith('<img') and page.locator('img').count()==0
    checks['https_fragment_and_storage_empty']=page.evaluate("[location.hash,document.cookie,localStorage.length,sessionStorage.length]")==['','',0,0]
    page.get_by_role('button',name='Log out').click();expect(page.get_by_test_id('status')).to_have_text('Locked')
    checks['https_logout_clears_data']=page.get_by_test_id('example').count()==0
    page.goto(url);expect(page.get_by_test_id('status')).to_have_text('Locked')
    checks['https_grant_replay_refused']=page.get_by_test_id('example').count()==0
    checks['no_history_endpoint']=page.evaluate("fetch('/v0/history').then(r=>r.status)")==404
   report['passed']=all(checks.values())
  finally:context.close()
except Exception as exc:report['error_type']=type(exc).__name__;report['error']=re.sub(r'#grant=[A-Za-z0-9_-]+','#grant=<redacted>',str(exc)[-1200:])
finally:
 (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':report['passed'],'checks':checks,'version':report.get('version'),'error':report.get('error')}),flush=True)
raise SystemExit(0 if report['passed'] else 1)
