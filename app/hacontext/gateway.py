"""HA OS ingress gateway: fixed terminal command and explicit export downloads.

Never a generic shell or directory server. Only the Supervisor ingress peer is
accepted. No public port, CORS relaxation or forwarded-IP authentication.
"""
from __future__ import annotations
import asyncio
import html
import ipaddress
import os
from pathlib import Path
import subprocess
import sys
from aiohttp import web, ClientSession, WSMsgType, ClientTimeout
from .state import Store

STYLE='''body{margin:0;background:#18232c;color:#e3dccf;font:15px system-ui,sans-serif}header{display:flex;align-items:center;gap:24px;padding:16px 22px;background:#23313c;border-bottom:1px solid #445966}strong{color:#c4b7df}a{color:#9bbfd3;text-decoration:none}a:hover{text-decoration:underline}main{padding:24px;max-width:1100px;margin:auto}iframe{display:block;border:0;width:100%;height:calc(100vh - 57px)}article{padding:18px;margin-bottom:12px;border:1px solid #445966;border-radius:8px}small{color:#a1b1bd}pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}nav{display:flex;gap:20px}h2{color:#c4b7df;font-weight:600}'''


def shell(body: str, *, title='ha-context', prefix='', full=False):
    if prefix and (not prefix.startswith('/') or prefix.startswith('//') or '\\' in prefix):
        raise web.HTTPBadRequest(text='Invalid ingress prefix.')
    base='<base href="'+html.escape(prefix.rstrip('/')+'/',quote=True)+'">'
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'+base+'<title>'+title+'</title><style>'+STYLE+'</style></head><body>'+body+'</body></html>'


def peer_allowed(peer: str | None, allowed=frozenset({'172.30.32.2'})) -> bool:
    try:
        parsed=ipaddress.ip_address(peer or '')
        if isinstance(parsed,ipaddress.IPv6Address) and parsed.ipv4_mapped:parsed=parsed.ipv4_mapped
        return str(parsed) in allowed
    except ValueError:return False


def create_app(store: Store, *, allowed=frozenset({'172.30.32.2'}), terminal_url='http://127.0.0.1:7681'):
    @web.middleware
    async def ingress_only(request,handler):
        if not peer_allowed(request.remote,allowed):raise web.HTTPForbidden(text='Supervisor ingress required.')
        response=await handler(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Cache-Control']='no-store'
        return response
    app=web.Application(middlewares=[ingress_only],client_max_size=1024*1024)

    async def index(request):
        if not request.path.endswith('/'):
            # Keep the incoming ingress prefix by redirecting relatively.
            raise web.HTTPFound(location=request.headers.get('X-Ingress-Path','')+'/')
        body='<header><strong>ha-context</strong><small>Read-only Home Assistant context</small><nav><a href="files" target="_blank" rel="noopener">Files ↗</a><a href="help" target="_blank" rel="noopener">Documentation ↗</a></nav></header><iframe src="term/" title="ha-context terminal"></iframe>'
        return web.Response(text=shell(body,prefix=request.headers.get('X-Ingress-Path','')),content_type='text/html')

    async def files(request):
        rows=[]
        for path in store.history():
            stamp=html.escape(path.name)
            rows.append('<article><strong>'+stamp+'</strong><p><a href="download/'+stamp+'/ha-context.txt">Download TXT</a> &nbsp; <a href="download/'+stamp+'/ha-context.zip">Download ZIP</a></p></article>')
        text='<main><h2>Your exports</h2><p>These are private snapshots. Review before sharing. Keep the terminal tab open while an export runs.</p>'+(''.join(rows) or '<p>No completed snapshots yet. Create one in the terminal interface.</p>')
        selected=store.local/'selections'/'selected-entities.txt'
        if selected.is_file() and not selected.is_symlink():text+='<article><a href="selection">Download last filtered entity view</a></article>'
        return web.Response(text=shell(text+'</main>',prefix=request.headers.get('X-Ingress-Path','')),content_type='text/html')

    async def download(request):
        name=request.match_info['name'];stamp=request.match_info['stamp']
        if name not in {'ha-context.txt','ha-context.zip'}:raise web.HTTPNotFound()
        root=next((p for p in store.history() if p.name==stamp),None)
        if root is None:raise web.HTTPNotFound()
        target=root/name
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(store.exports.resolve()):raise web.HTTPNotFound()
        return web.FileResponse(target,headers={'Content-Disposition':'attachment; filename="'+name+'"'})

    async def selection(request):
        target=store.local/'selections'/'selected-entities.txt'
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(store.local.resolve()):raise web.HTTPNotFound()
        return web.FileResponse(target,headers={'Content-Disposition':'attachment; filename="selected-entities.txt"'})

    async def help_page(request):
        body='<main><h2>Included documentation</h2>'
        for p in sorted((store.root/'app/docs').glob('*.md')):
            body+='<article><pre>'+html.escape(p.read_text())+'</pre></article>'
        return web.Response(text=shell(body+'</main>',prefix=request.headers.get('X-Ingress-Path','')),content_type='text/html')

    async def terminal(request):
        tail=request.match_info.get('tail','')
        # The upstream host is fixed; never accept an arbitrary proxy URL.
        url=terminal_url+'/'+tail
        if request.query_string:url+='?'+request.query_string
        timeout=ClientTimeout(total=None,sock_connect=10)
        if request.headers.get('Upgrade','').casefold()=='websocket':
            async with ClientSession(timeout=timeout) as session:
                try:
                    upstream=await session.ws_connect(url,protocols=['tty'],max_msg_size=1024*1024)
                except Exception:raise web.HTTPBadGateway(text='Terminal is not ready; reload this page.')
                async with upstream:
                    downstream=web.WebSocketResponse(protocols=['tty'],max_msg_size=1024*1024)
                    await downstream.prepare(request)
                    async def pump(source,dest):
                        async for msg in source:
                            if msg.type==WSMsgType.TEXT:await dest.send_str(msg.data)
                            elif msg.type==WSMsgType.BINARY:await dest.send_bytes(msg.data)
                            elif msg.type in {WSMsgType.ERROR,WSMsgType.CLOSE,WSMsgType.CLOSED}:break
                    tasks=[asyncio.create_task(pump(downstream,upstream)),asyncio.create_task(pump(upstream,downstream))]
                    try:await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        for task in tasks:task.cancel()
                        await asyncio.gather(*tasks,return_exceptions=True)
                        await downstream.close()
                    return downstream
        if request.method!='GET':raise web.HTTPMethodNotAllowed(request.method,['GET'])
        async with ClientSession(timeout=ClientTimeout(total=15)) as session:
            try:
                async with session.get(url,allow_redirects=False) as response:
                    data=await response.read()
                    headers={'Content-Type':response.headers.get('Content-Type','application/octet-stream')}
                    return web.Response(body=data,status=response.status,headers=headers)
            except Exception:raise web.HTTPBadGateway(text='Terminal is not ready; reload this page.')

    app.router.add_get('/',index)
    app.router.add_get('/files',files)
    app.router.add_get('/download/{stamp}/{name}',download)
    app.router.add_get('/selection',selection)
    app.router.add_get('/help',help_page)
    app.router.add_route('*','/term/{tail:.*}',terminal)
    return app


def main():
    root=Path(__file__).resolve().parents[2]
    if os.environ.get('HA_CONTEXT_ADDON')!='1':raise SystemExit('The ingress gateway is only for the HA OS app.')
    store=Store(root);store.initialize()
    # No -a/url-arg and no shell: a browser can only operate the application UI.
    child=subprocess.Popen(['ttyd','-i','lo','-p','7681','-W','-m','1','-s','15','-d','1',
        '-t','disableLeaveAlert=true','-t','fontSize=14',sys.executable,'-m','hacontext'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:web.run_app(create_app(store),host='0.0.0.0',port=8099,access_log=None,print=None)
    finally:
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait()

if __name__=='__main__':main()
