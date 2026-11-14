"""Fresh ordinary-user Firefox. Commands/secrets arrive only on private pipes."""
import json
import os
from pathlib import Path
import sys
import tempfile
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

root=Path(sys.argv[1]);label=sys.argv[2] if len(sys.argv)>2 else 'standalone'
options=Options();options.add_argument('-headless');options.set_capability('webSocketUrl',True)
# A home-owned profile root is visible to Ubuntu's confined Firefox.
profiles=root/'browser-profiles';profiles.mkdir(exist_ok=True)
service=Service(str(root/'geckodriver'),service_args=['--profile-root',str(profiles)],log_output=str(root/('geckodriver-'+label+'.log')))
driver=webdriver.Firefox(service=service,options=options)
driver.set_page_load_timeout(15)
driver.script.add_preload_script("""()=>{window.hidsHoldFetch=false;window.hidsHeld=null;const original=window.fetch.bind(window);window.fetch=(url,init)=>original(url,init).then(async response=>{if(url==='/v0/pilot'&&window.hidsHoldFetch){const body=await response.text();return new Promise(resolve=>{window.hidsHeld=()=>resolve(new Response(body,{status:response.status,headers:response.headers}))})}return response})}""")

wait=WebDriverWait(driver,15)
def status(value):wait.until(lambda d:d.execute_script("return document.readyState==='complete' && location.hash==='' && document.querySelector('[data-testid=status]')?.textContent===arguments[0]",value))
def inspect():
 return driver.execute_script('''return {fragment:location.hash,local:localStorage.length,session:sessionStorage.length,cookies:document.cookie,resources:performance.getEntriesByType('resource').map(x=>x.name),injected:window.hidsInjected===true,images:document.querySelectorAll('img').length,status:document.querySelector('[data-testid=status]').textContent}''')
try:
 print(json.dumps({'ready':True,'browser':driver.capabilities.get('browserVersion'),'uid':os.getuid()}),flush=True)
 for line in sys.stdin:
  command=json.loads(line)
  try:
   action=command['action']
   if action=='stop':break
   if action=='open':driver.get(command['url']);status(command['expected'])
   elif action=='refresh':driver.refresh();status('Locked')
   elif action=='logout':driver.find_element(By.XPATH,"//button[text()='Log out']").click();status('Locked')
   elif action=='check':driver.find_element(By.XPATH,"//button[text()='Check access']").click();status(command['expected'])
   elif action=='race_logout':
    driver.execute_script('window.hidsHoldFetch=true;window.hidsHeld=null')
    driver.find_element(By.XPATH,"//button[text()='Check access']").click()
    wait.until(lambda d:d.execute_script('return !!window.hidsHeld'))
    driver.find_element(By.XPATH,"//button[text()='Log out']").click();status('Locked')
    driver.execute_script('window.hidsHoldFetch=false;window.hidsHeld()')
    driver.execute_async_script('const done=arguments[0];setTimeout(done,100)')
    assert driver.find_elements(By.CSS_SELECTOR,'[data-testid=example]')==[]
    assert 'Synthetic example only' not in driver.find_element(By.TAG_NAME,'body').text
    status('Locked')

   else:raise ValueError()
   value=inspect()
   assert value['fragment']==value['cookies']=='' and value['local']==value['session']==0
   assert not value['injected'] and value['images']==0
   assert all('#' not in x and 'grant=' not in x and 'token=' not in x for x in value['resources'])
   if value['status']=='Authorized':
    text=driver.find_element(By.CSS_SELECTOR,'[data-testid=example]').text
    assert '<img' in text and 'Synthetic example only' in text
    driver.save_screenshot(str(root/('pilot-'+label+'.png')))
   print(json.dumps({'passed':True,'action':action,'status':value['status'],'storage_empty':True,'fragment_removed':True,'text_rendered':True,'resource_urls_clean':True}),flush=True)
  except Exception as exc:
   print(json.dumps({'passed':False,'error_type':type(exc).__name__}),flush=True)
finally:driver.quit()
