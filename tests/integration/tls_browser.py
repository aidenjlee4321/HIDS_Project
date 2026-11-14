"""Synthetic-only actual certificate verification, ordinary-user Firefox."""
import json
from pathlib import Path
import subprocess
import sys
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import InsecureCertificateException
r=Path(sys.argv[1]);tools=Path(sys.argv[2]);ports=json.loads(sys.argv[3]);build=Path(sys.argv[4]);checks={}
def browser(label,cert):
 profile=r/('profile-'+label);profile.mkdir(mode=0o700)
 subprocess.run([str(tools/'certutil'),'-N','--empty-password','-d','sql:'+str(profile)],check=True,capture_output=True)
 subprocess.run([str(tools/'certutil'),'-A','-n','HIDS synthetic leaf','-t','P,,','-i',str(cert),'-d','sql:'+str(profile)],check=True,capture_output=True)
 options=Options();options.add_argument('-headless');options.accept_insecure_certs=False;options.profile=webdriver.FirefoxProfile(str(profile))
 profiles=r/'driver-profiles';profiles.mkdir(exist_ok=True)
 driver=webdriver.Firefox(service=Service(str(build/'geckodriver'),service_args=['--profile-root',str(profiles)],log_output=str(r/('driver-'+label+'.log'))),options=options)
 assert driver.capabilities['acceptInsecureCerts'] is False
 driver.set_page_load_timeout(15);return driver

def rejected(driver,url):
 try:driver.get(url)
 except InsecureCertificateException:return True
 return False
try:
 d=browser('valid',r/'valid.pem')
 try:
  d.get('https://127.0.0.1:'+str(ports['valid'])+'/');checks['trusted_leaf_verified']=d.find_element('tag name','body').text=='TLS synthetic only'
  checks['foreign_leaf_rejected']=rejected(d,'https://127.0.0.1:'+str(ports['foreign'])+'/')
  checks['wrong_name_rejected']=rejected(d,'https://localhost:'+str(ports['valid'])+'/')
  checks['certificate_bypass_disabled']=d.capabilities['acceptInsecureCerts'] is False
 finally:d.quit()
 d=browser('expired',r/'expired.pem')
 try:checks['expired_trusted_leaf_rejected']=rejected(d,'https://127.0.0.1:'+str(ports['expired'])+'/')
 finally:d.quit()
 assert all(checks.values()),checks
 print(json.dumps({'passed':True,'checks':checks}),flush=True)
except Exception as exc:
 print(json.dumps({'passed':False,'checks':checks,'error_type':type(exc).__name__}),flush=True);raise
