"""Closed dashboard scope over independently loaded, immutable process/M4 views."""
import re
from fastapi import Request
from starlette.responses import JSONResponse
from api.pilot_app import Boundary, make_app as pilot_app
from api.pilot_sessions import Sessions, Denied
from api.history_view import ViewError

LISTS=('/v0/process/events','/v0/history/events','/v0/history/findings')


def make_app(authority,assets,process,history,sessions=None):
    # Count conservative family representations plus combined object framing.
    if process is not None and history is not None and process.serialized_bytes+history.serialized_bytes+64>8*1024*1024:
        process=None
    state=sessions if sessions is not None else Sessions(scope='dashboard:read')
    if state.scope!='dashboard:read':raise ValueError('dashboard scope required')
    wrapped,state=pilot_app(authority,assets,state,scheme='https',shell='dashboard.html')
    app=wrapped.app
    app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None)!='/v0/pilot']
    def authorize(request):
        token=request.headers.get('authorization','')
        if not token.startswith('Bearer ') or token.count(' ')!=1:raise Denied()
        token=token[7:];state.authorize(token,'dashboard:read');return token
    def response(value,detail=False):
        result=JSONResponse(value)
        if len(result.body)>(32768 if detail else 65536):raise ViewError()
        return result
    @app.exception_handler(ViewError)
    async def unavailable(request,exc):return JSONResponse({'error':'history unavailable'},status_code=404)
    @app.get('/v0/dashboard')
    async def summary(request:Request):
        authorize(request)
        return response(dict(format='hids.dashboard-view/1',history_only=True,monitoring_status='not_assessed',process=dict(available=process is not None,snapshot=process.summary() if process is not None else None),history=dict(available=history is not None,snapshot=history.summary() if history is not None else None)))
    @app.get('/v0/history')
    async def history_summary(request:Request):
        authorize(request)
        if history is None:raise ViewError()
        return response(history.summary())
    async def listing(request,view,kind):
        token=authorize(request)
        if view is None:raise ViewError()
        query=request.scope.get('query_string',b'');cursor=None
        if query:
            if not re.fullmatch(rb'cursor=[A-Za-z0-9_-]{1,512}',query):raise ViewError()
            cursor=query[7:].decode('ascii')
        return response(view.page(kind,token,cursor))
    async def detail(request,view,kind,key):
        authorize(request)
        if view is None:raise ViewError()
        return response(view.detail(kind,key),True)
    @app.get('/v0/process/events')
    async def process_events(request:Request):return await listing(request,process,'process')
    @app.get('/v0/process/events/{key}')
    async def process_detail(request:Request,key:str):return await detail(request,process,'process',key)
    @app.get('/v0/history/events')
    async def events(request:Request):return await listing(request,history,'events')
    @app.get('/v0/history/findings')
    async def findings(request:Request):return await listing(request,history,'findings')
    @app.get('/v0/history/events/{key}')
    async def event(request:Request,key:str):return await detail(request,history,'events',key)
    @app.get('/v0/history/findings/{key}')
    async def finding(request:Request,key:str):return await detail(request,history,'findings',key)
    return Boundary(app,authority,'https',LISTS),state
