"""Setup metadata and draft HTTP only. No file writes or source-control route."""
from fastapi import Request
from starlette.responses import JSONResponse
from api.pilot_app import make_app as pilot_app
from api.pilot_sessions import Denied,closed_json
from api.setup_sessions import SetupSessions
from api.setup_contract import public_view,require

def make_app(authority,assets,view,state=None):
 state=state if state is not None else SetupSessions(view)
 require(state.scope=='setup:draft')
 wrapped,state=pilot_app(authority,assets,state,scheme='https',shell='setup.html')
 app=wrapped.app;app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None)!='/v0/pilot']
 def token(request):
  value=request.headers.get('authorization','');require(value.startswith('Bearer ') and value.count(' ')==1)
  t=value[7:];state.authorize(t,'setup:draft');return t
 @app.get('/v0/setup')
 async def setup(request:Request):
  token(request);require(state.view is not None);result=JSONResponse(public_view(state.view));require(len(result.body)<=65536);return result
 @app.post('/v0/setup/draft')
 async def draft(request:Request):
  t=token(request);body=closed_json(await request.body(),{'assessment_id','confirmed_revision','selected'});return JSONResponse(state.stage(t,body))
 return wrapped,state
