"""Closed HTTPS routes over an already validated, database-free frozen view."""
import re
from fastapi import Request
from starlette.responses import JSONResponse
from api.pilot_app import Boundary, make_app as pilot_app
from api.pilot_sessions import Sessions, Denied
from api.history_view import ViewError

LISTS=('/v0/history/events','/v0/history/findings')

def make_app(authority,assets,view,sessions=None):
    state=sessions if sessions is not None else Sessions(scope='history:read')
    if state.scope!='history:read':raise ValueError('history scope required')
    wrapped,state=pilot_app(authority,assets,state,scheme='https',shell='history.html')
    app=wrapped.app
    app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None)!='/v0/pilot']
    def authorize(request):
        token=request.headers.get('authorization','')
        if not token.startswith('Bearer ') or token.count(' ')!=1:raise Denied()
        token=token[7:];state.authorize(token,'history:read');return token
    def response(value,detail=False):
        # Starlette emits UTF-8, while the loader's canonical ASCII accounting is
        # conservative for every native string. Also check the actual wire bytes.
        result=JSONResponse(value)
        if len(result.body)>(32768 if detail else 65536):raise ViewError()
        return result
    @app.exception_handler(ViewError)
    async def unavailable(request,exc):return JSONResponse({'error':'history unavailable'},status_code=404)
    @app.get('/v0/history')
    async def summary(request:Request):
        authorize(request)
        if view is None:raise ViewError()
        return response(view.summary())
    async def listing(request:Request,kind):
        token=authorize(request)
        if view is None:raise ViewError()
        query=request.scope.get('query_string',b'')
        cursor=None
        if query:
            if not re.fullmatch(rb'cursor=[A-Za-z0-9_-]{1,512}',query):raise ViewError()
            cursor=query[7:].decode('ascii')
        return response(view.page(kind,token,cursor))
    @app.get('/v0/history/events')
    async def events(request:Request):return await listing(request,'events')
    @app.get('/v0/history/findings')
    async def findings(request:Request):return await listing(request,'findings')
    @app.get('/v0/history/events/{key}')
    async def event(request:Request,key:str):
        authorize(request)
        if view is None:raise ViewError()
        return response(view.detail('events',key),True)
    @app.get('/v0/history/findings/{key}')
    async def finding(request:Request,key:str):
        authorize(request)
        if view is None:raise ViewError()
        return response(view.detail('findings',key),True)
    return Boundary(app,authority,'https',LISTS),state
