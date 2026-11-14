"""Closed FastAPI synthetic surface. Deliberately imports no HIDS data modules."""
import asyncio
from pathlib import Path
import re
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response
from api.pilot_sessions import Sessions, Denied, closed_json

DEFENSES = {
    'cache-control': 'no-store', 'referrer-policy': 'no-referrer',
    'x-content-type-options': 'nosniff', 'x-frame-options': 'DENY',
    'content-security-policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; worker-src 'none'",
}
SYNTHETIC = {'synthetic': True, 'message': '<img src=x onerror="window.hidsInjected=true"> Synthetic example only; no host data.'}


class Boundary:
    def __init__(self, app, authority, scheme='http', query_paths=()):
        self.query_paths=frozenset(query_paths)
        if scheme not in ('http','https'):raise ValueError('invalid trusted scheme')
        self.app, self.authority, self.scheme = app, authority, scheme
        self.origin = scheme + '://' + authority
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def safe_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = list(message.get('headers', [])) + [
                    (k.encode(), v.encode()) for k,v in DEFENSES.items()]
            await send(message)
        async def reject(status=403):
            await JSONResponse({'error':'request denied'}, status_code=status)(scope, receive, safe_send)
        if self.active >= 16:
            return await reject(503)
        self.active += 1
        try:
            raw = scope.get('headers', [])
            if len(raw) > 40 or sum(len(k)+len(v) for k,v in raw) > 8192:
                return await reject()
            headers = {}
            for k,v in raw:
                k = k.lower()
                if k in headers:
                    return await reject()
                headers[k] = v
            if (scope.get('scheme') != self.scheme or headers.get(b'host') != self.authority.encode() or (scope.get('query_string') and (scope.get('path') not in self.query_paths or len(scope['query_string'])>519))
                or any(k in headers for k in (b'forwarded', b'x-forwarded-host', b'x-forwarded-proto', b'x-forwarded-for'))):
                return await reject()
            origin = headers.get(b'origin')
            if origin is not None and origin != self.origin.encode():
                return await reject()
            method, path = scope['method'], scope['path']
            api = path.startswith('/v0/')
            if api and headers.get(b'sec-fetch-site') != b'same-origin':
                return await reject()
            if api and method == 'POST' and (origin != self.origin.encode() or headers.get(b'content-type') != b'application/json'):
                return await reject()
            length = headers.get(b'content-length', b'0')
            if not re.fullmatch(rb'[0-9]{1,4}', length) or int(length) > 1024:
                return await reject(413)
            body = bytearray()
            async def read():
                while True:
                    msg = await receive()
                    if msg['type'] != 'http.request':
                        raise Denied()
                    body.extend(msg.get('body', b''))
                    if len(body) > 1024:
                        raise Denied()
                    if not msg.get('more_body'):
                        return
            try:
                await asyncio.wait_for(read(), 3)
                if method == 'GET' and body:
                    raise Denied()
            except (Denied, TimeoutError):
                return await reject()
            delivered = False
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request','body':bytes(body),'more_body':False}
                return {'type':'http.disconnect'}
            await self.app(scope, replay, safe_send)
        finally:
            self.active -= 1


def make_app(authority, assets, sessions=None, *, scheme='http', shell='index.html'):
    if scheme not in ('http','https'):raise ValueError('invalid trusted scheme')
    if not re.fullmatch(r'127\.0\.0\.1:[1-9][0-9]{3,4}', authority) or not 1024 <= int(authority.split(':')[1]) <= 65535:
        raise ValueError('invalid pilot origin')
    state = sessions if sessions is not None else Sessions()
    if shell not in ('index.html','history.html','setup.html','dashboard.html'):raise ValueError('invalid shell')
    assets = Path(assets)
    # An explicit, bounded asset map; no runtime user-controlled filesystem reads.
    static = {'/': ((assets/shell).read_bytes(), 'text/html')}
    for p in sorted((assets/'assets').iterdir()):
        if not p.is_file() or not re.fullmatch(r'[A-Za-z0-9_-]+\.(js|css)', p.name):
            raise ValueError('invalid packaged asset')
        data = p.read_bytes()
        if len(data) > 1024*1024 or len(static) >= 16:
            raise ValueError('asset budget exceeded')
        static['/assets/'+p.name] = (data, 'text/javascript' if p.suffix == '.js' else 'text/css')
    if len(static['/'][0]) > 16384:
        raise ValueError('shell budget exceeded')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    @app.exception_handler(Denied)
    async def denied(request, exc):
        return JSONResponse({'error':'request denied'}, status_code=403)

    @app.exception_handler(404)
    @app.exception_handler(405)
    async def closed(request, exc):
        return JSONResponse({'error':'request denied'}, status_code=404)

    @app.post('/v0/auth/redeem')
    async def redeem(request: Request):
        data = closed_json(await request.body(), {'grant'})
        token = state.redeem(data['grant'])
        return JSONResponse({'token':token, 'scope':state.scope, 'absolute_seconds':1800, 'idle_seconds':300})

    def bearer(request):
        value = request.headers.get('authorization', '')
        if not value.startswith('Bearer ') or value.count(' ') != 1:
            raise Denied()
        return value[7:]

    @app.get('/v0/pilot')
    async def pilot(request: Request):
        state.authorize(bearer(request))
        return JSONResponse(SYNTHETIC)

    @app.post('/v0/auth/logout')
    async def logout(request: Request):
        closed_json(await request.body(), set())
        state.logout(bearer(request))
        return JSONResponse({'logged_out':True})

    async def fixed_asset(request: Request):
        data, kind = static[request.url.path]
        return Response(data, media_type=kind)
    for path in static:
        app.add_api_route(path, fixed_asset, methods=['GET'], include_in_schema=False)
    return Boundary(app, authority, scheme), state
