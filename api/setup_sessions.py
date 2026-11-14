"""Volatile setup drafts; a browser credential never authorizes source control."""
import secrets
from api.pilot_sessions import Sessions,Denied,digest
from api.setup_contract import validate_view,selected,clone,require

class SetupSessions(Sessions):
 def __init__(self,view,*,mint_check=lambda:None,**kw):
  super().__init__(scope='setup:draft',**kw);self.view=validate_view(view) if view is not None else None;self.drafts={};self.mint_check=mint_check
 def mint(self):
  require(self.view is not None);self.mint_check();return super().mint()
 def prune_drafts(self):
  with self._lock:
   now=self._now();self._prune(now)
   self.drafts={k:v for k,v in self.drafts.items() if now<v['expires'] and v['session'] in self._sessions and self._sessions[v['session']][2]=='setup:draft'}
 def stage(self,token,body):
  self.authorize(token,'setup:draft');self.prune_drafts();require(self.view is not None)
  require(type(body) is dict and set(body)=={'assessment_id','confirmed_revision','selected'} and body['assessment_id']==self.view['assessment_id'] and type(body['confirmed_revision']) is int and body['confirmed_revision']==self.view['confirmed']['revision'])
  values=selected(body['selected']);eligible={s['id'] for s in self.view['sources'] if s['preflight']=='eligible'};require(set(values)<=eligible)
  session=digest(token)
  with self._lock:
   now=self._now();self.drafts={k:v for k,v in self.drafts.items() if v['session']!=session};require(len(self.drafts)<4)
   reference=secrets.token_urlsafe(32);key=digest(reference);require(key not in self.drafts)
   self.drafts[key]=dict(session=session,expires=now+60,body=dict(assessment_id=body['assessment_id'],fingerprint=self.view['fingerprint'],confirmed=clone(self.view['confirmed']),selected=values))
  return dict(reference=reference,expires_seconds=60,requires_root_confirmation=True)
 def review(self,reference,*,consume=False):
  self.prune_drafts();key=digest(reference)
  with self._lock:
   record=self.drafts.pop(key,None) if consume else self.drafts.get(key)
   require(record is not None);return clone(record['body'])
 def logout(self,token):
  key=digest(token);super().logout(token)
  with self._lock:self.drafts={k:v for k,v in self.drafts.items() if v['session']!=key}
 def revoke_all(self):
  super().revoke_all()
  with self._lock:self.drafts.clear()
 def housekeeping(self):super().housekeeping();self.prune_drafts()
