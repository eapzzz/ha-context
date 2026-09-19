import asyncio,json
from pathlib import Path
from aiohttp.test_utils import TestServer,TestClient
from hacontext.gateway import create_app,peer_allowed
from hacontext.state import Store


def test_ingress_peer_not_forwarded_header():
    assert peer_allowed('172.30.32.2')
    assert peer_allowed('::ffff:172.30.32.2')
    for ip in ('127.0.0.1','172.30.33.4',None,'unknown'):assert not peer_allowed(ip)


def test_gateway_rejects_direct_access(tmp_path):
    async def go():
        store=Store(tmp_path/'app');store.initialize()
        async with TestClient(TestServer(create_app(store))) as c:
            response=await c.get('/',headers={'X-Forwarded-For':'172.30.32.2'})
            assert response.status==403
    asyncio.run(go())


def test_downloads_are_allowlisted_and_not_tokens(tmp_path):
    async def go():
        store=Store(tmp_path/'app');store.initialize()
        root=store.exports/'2026-test';root.mkdir();(root/'manifest.json').write_text(json.dumps({'tool':'ha-context'}))
        (root/'ha-context.txt').write_text('SANITIZED SNAPSHOT')
        (root/'token').write_text('SYNTHETIC_PRIVATE_TOKEN')
        (root/'ha-context.zip').symlink_to(root/'token')
        async with TestClient(TestServer(create_app(store,allowed=frozenset({'127.0.0.1'})))) as c:
            r=await c.get('/files');assert r.status==200 and '2026-test' in await r.text()
            r=await c.get('/download/2026-test/ha-context.txt');assert r.status==200 and await r.text()=='SANITIZED SNAPSHOT'
            for path in ['/download/2026-test/token','/download/2026-test/ha-context.zip','/download/missing/ha-context.txt']:
                r=await c.get(path);assert r.status==404
    asyncio.run(go())
