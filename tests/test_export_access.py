"""Regressions for sudo's terminal scope and honest config-source errors.

Process/session IDs and cancellation are tested with real subprocesses; HA and
container responses are synthetic. Tests never change sudoers or HA permissions.
"""
import asyncio
import errno
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from hacontext import engine, state
from hacontext.state import Store, Settings
from test_workspace_audit import CapturingUI


def worker_store(tmp_path, payload):
    store = Store(tmp_path / 'installed')
    store.initialize()
    store.save(Settings(url='http://127.0.0.1:8123'), 'SYNTHETIC_PRIVATE_TOKEN')
    store.notes.write_text('Keep my existing notes')
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / 'app', store.root / 'app')
    # Only this test installation contains a worker substitute. The actual UI
    # launches the actual CLI entry point and uses the real subprocess transport.
    hook = '''from hacontext import worker
import json, os, time, subprocess, sys
from pathlib import Path
def fixture_export(store, progress):
    record = {'pid':os.getpid(), 'sid':os.getsid(0), 'pgid':os.getpgrp(), 'uid':os.geteuid()}
    try:
        fd = os.open('/dev/tty', os.O_RDONLY | os.O_NONBLOCK)
        record['tty'] = os.fstat(fd).st_rdev
        os.close(fd)
    except OSError:
        record['tty'] = None
    (store.local/'process-probe.json').write_text(json.dumps(record))
'''
    hook += '\n'.join('    '+line for line in payload.splitlines())
    hook += '\nworker.run_export = fixture_export\n'
    worker_file = store.root / 'app/hacontext/worker.py'
    worker_file.write_text(worker_file.read_text() + '\n' + hook)
    return store


SUCCESS = '''progress('Synthetic read complete')
root=store.exports/'test-snapshot'
summary={'status':'Complete','scope':'synthetic process test'}
worker.rebuild_bundle(root,{'summary.json':json.dumps(summary)}, {'tool':'ha-context'})
return root,summary'''


def test_export_preserves_session_and_user_but_owns_process_group(tmp_path):
    async def run():
        store = worker_store(tmp_path, SUCCESS)
        before = {p.name:p.read_bytes() for p in (store.config, store.local/'token', store.notes)}
        with create_pipe_input() as inp:
            ui = CapturingUI(store,input=inp,output=DummyOutput())
            await asyncio.wait_for(ui.export_async(),10)
            record = json.loads((store.local/'process-probe.json').read_text())
            assert record['sid'] == os.getsid(0), 'Export lost the authorized terminal session'
            assert record['pgid'] == record['pid'], 'Cancellation requires a dedicated worker group'
            assert record['pgid'] != os.getpgrp(), 'Never signal the UI process group'
            assert record['uid'] == os.geteuid(), 'Do not elevate the full exporter'
            assert ui.page == 'done', ui.message
            assert before == {p.name:p.read_bytes() for p in (store.config, store.local/'token', store.notes)}
    asyncio.run(run())


def test_export_failure_has_error_page_not_dead_cancel_button(tmp_path):
    async def run():
        store = worker_store(tmp_path, "raise ValueError('Docker authorization required. Use Authorize Docker.')")
        with create_pipe_input() as inp:
            ui=CapturingUI(store,input=inp,output=DummyOutput())
            await asyncio.wait_for(ui.export_async(),10)
            assert ui.page=='export-error', ui.page
            assert 'authorization' in ui.controls['export-error-detail'].text
            assert ui.process is None and ui.busy is False
            assert not store.history()
            ui.choose('Connection settings')
            assert ui.page=='connection'
    asyncio.run(run())


def test_cancel_export_during_startup_never_signals_the_ui_group(tmp_path,monkeypatch):
    store=worker_store(tmp_path,SUCCESS)
    calls=[]
    monkeypatch.setattr(os,'getpgid',lambda pid:os.getpgrp())
    monkeypatch.setattr(os,'killpg',lambda *args:calls.append(('group',args)))
    monkeypatch.setattr(os,'kill',lambda *args:calls.append(('pid',args)))
    with create_pipe_input() as inp:
        ui=CapturingUI(store,input=inp,output=DummyOutput())
        ui.process=SimpleNamespace(pid=999999,returncode=None)
        ui.cancel_job()
    assert calls == [('pid',(999999,signal.SIGTERM))], calls


def test_cancellation_stops_worker_and_its_child_not_ui(tmp_path):
    async def run():
        store=worker_store(tmp_path,'''child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
(store.local/'child.json').write_text(json.dumps({'pid':child.pid,'group':os.getpgrp()}))
while True: time.sleep(.05)''')
        with create_pipe_input() as inp:
            ui=CapturingUI(store,input=inp,output=DummyOutput())
            task=asyncio.create_task(ui.export_async())
            try:
                for _ in range(150):
                    if (store.local/'child.json').exists():break
                    await asyncio.sleep(.02)
                assert (store.local/'child.json').exists(), ui.message
                child=json.loads((store.local/'child.json').read_text())
                assert child['group']!=os.getpgrp()
                ui.cancel_job()
                await asyncio.wait_for(task,6)
                for _ in range(60):
                    status=Path(f"/proc/{child['pid']}/stat")
                    if not status.exists() or status.read_text().split(') ')[1].startswith('Z'):break
                    await asyncio.sleep(.02)
                else:pytest.fail('Worker child still running after cancellation')
                assert ui.page=='export' and not ui.busy
                assert not store.history()
            finally:
                if ui.process and ui.process.returncode is None:
                    ui.cancel_job()
                if not task.done():await asyncio.wait_for(task,6)
    asyncio.run(run())


def test_missing_discovery_due_to_permissions_is_not_missing_container(monkeypatch):
    monkeypatch.setattr(state,'discover_containers',lambda *a:([],['docker is installed but inaccessible. Use Authorize Docker.']))
    cfg=Settings(url='http://localhost:8123',source_mode='container',container='Home-Assistant',docker_sudo=True,auto_url=True)
    with pytest.raises(ValueError) as caught:state.resolved_settings(cfg)
    assert 'Authorize Docker' in str(caught.value)
    assert 'no longer available' not in str(caught.value)


def test_missing_container_after_successful_discovery_is_distinct(monkeypatch):
    monkeypatch.setattr(state,'discover_containers',lambda *a:([],[]))
    cfg=Settings(url='http://localhost:8123',source_mode='container',container='Home-Assistant',auto_url=True)
    with pytest.raises(ValueError,match='not running|not found'):state.resolved_settings(cfg)


def test_source_validation_does_not_mislabel_permission_denial(tmp_path,monkeypatch):
    store=worker_store(tmp_path,SUCCESS)
    folder=tmp_path/'protected';folder.mkdir();(folder/'configuration.yaml').write_text('default_config:')
    original_stat=Path.stat
    def denied(path,*args,**kwargs):
        if path==folder or folder in path.parents:raise PermissionError(errno.EACCES,'Permission denied',str(path))
        return original_stat(path,*args,**kwargs)
    with create_pipe_input() as inp:
        ui=CapturingUI(store,input=inp,output=DummyOutput());ui.source_page()
        ui.controls['source_mode'].current_value='local';ui.controls['source_dir'].text=str(folder)
        monkeypatch.setattr(Path,'stat',denied)
        ui.choose('Continue')
        assert 'Permission denied' in ui.message, ui.message
        assert 'does not contain' not in ui.message
        assert ui.page=='source'


def test_engine_local_source_reports_denied_not_missing(tmp_path,monkeypatch):
    folder=tmp_path/'config'
    args=SimpleNamespace(source_mode='local',config_dir=str(folder))
    original=Path.stat
    def denied(path,*a,**kw):
        if path==folder/'configuration.yaml':raise PermissionError(errno.EACCES,'Permission denied',str(path))
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'stat',denied)
    with pytest.raises((ValueError,RuntimeError),match='Permission denied'):
        engine.select_source(args,{'config_dir':'/config'},[])


def test_folder_is_not_readable_just_because_metadata_exists(tmp_path,monkeypatch):
    folder=tmp_path/'config';folder.mkdir();config=folder/'configuration.yaml';config.write_text('default_config:')
    original=Path.open
    def denied(path,*a,**kw):
        if path==config:raise PermissionError(errno.EACCES,'Permission denied',str(path))
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'open',denied)
    with pytest.raises((RuntimeError,ValueError),match='Permission denied'):
        engine.select_source(SimpleNamespace(source_mode='local',config_dir=str(folder)),{},[])


def test_sudo_error_is_specific_without_echoing_raw_stderr(monkeypatch):
    monkeypatch.setattr(engine.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1,stdout='',stderr='sudo: interactive authentication is required\nPRIVATE_NOISE'))
    with pytest.raises(RuntimeError) as exc:engine.run_command(['sudo','-n','docker','ps'])
    text=str(exc.value)
    assert 'Authorize Docker' in text
    assert 'PRIVATE_NOISE' not in text


def test_export_under_real_controlling_terminal_keeps_sudo_scope(tmp_path):
    """Real PTY, real CLI worker, synthetic sudo policy tied to SID and TTY.

    No password, sudoers modification, root subprocess or real Docker call.
    The failure mode under setsid matches the separately supplied host test.
    """
    import fcntl
    import select
    import time
    import termios
    source = Path(__file__).resolve().parents[1]
    binaries = tmp_path/'bin';binaries.mkdir()
    stub = binaries/'sudo'
    stub.write_text('#!'+sys.executable+'\n'+'''
import os, sys
try:
    fd=os.open('/dev/tty',os.O_RDONLY|os.O_NONBLOCK)
    tty=os.fstat(fd).st_rdev;os.close(fd)
except OSError:
    tty=None
allowed=os.getsid(0)==int(os.environ['EXPECTED_SESSION']) and tty==int(os.environ['EXPECTED_TTY'])
if not allowed:
    print('sudo: interactive authentication is required',file=sys.stderr)
    sys.exit(1)
print('true')
''')
    stub.chmod(0o755)
    script = '''
import asyncio, fcntl, json, os, termios, sys
from pathlib import Path
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_export_access import worker_store, SUCCESS
from test_workspace_audit import CapturingUI
# Become the controlling-terminal owner, as an SSH login normally would.
fcntl.ioctl(0,termios.TIOCSCTTY,0)
os.environ['EXPECTED_SESSION']=str(os.getsid(0))
fd=os.open('/dev/tty',os.O_RDONLY|os.O_NONBLOCK)
os.environ['EXPECTED_TTY']=str(os.fstat(fd).st_rdev);os.close(fd)
async def run():
    store=worker_store(Path(sys.argv[1]),"from hacontext import engine\\nengine.run_command(['sudo','-n','docker','inspect','Home-Assistant'])\\n"+SUCCESS)
    cfg=store.load();cfg.source_mode='container';cfg.container='Home-Assistant';cfg.docker_sudo=True
    store.save(cfg)
    with create_pipe_input() as inp:
        ui=CapturingUI(store,input=inp,output=DummyOutput())
        await asyncio.wait_for(ui.export_async(),10)
        record=json.loads((store.local/'process-probe.json').read_text())
        assert record['sid']==int(os.environ['EXPECTED_SESSION']),record
        assert record['tty']==int(os.environ['EXPECTED_TTY']),record
        assert record['pgid']==record['pid'],record
        assert ui.page=='done',(ui.page,ui.message)
        print('PTY_EXPORT_PASS',flush=True)
asyncio.run(run())
'''
    master,slave=os.openpty()
    proc=subprocess.Popen([sys.executable,'-c',script,str(tmp_path/'run')],
        stdin=slave,stdout=slave,stderr=slave,start_new_session=True,
        env={**os.environ,'PATH':str(binaries)+os.pathsep+os.environ['PATH'],
             'PYTHONPATH':os.pathsep.join([str(source/'app'),str(source/'tests')]),'TERM':'xterm'})
    os.close(slave);raw=bytearray()
    try:
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            ready,_,_=select.select([master],[],[],.1)
            if ready:
                try:chunk=os.read(master,65536)
                except OSError:break
                if not chunk:break
                raw.extend(chunk)
            if proc.poll() is not None and not ready:break
        assert proc.wait(timeout=3)==0,raw.decode(errors='replace')
        assert b'PTY_EXPORT_PASS' in raw,raw.decode(errors='replace')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        os.close(master)


def test_actual_ui_worker_exports_rest_and_websocket_snapshot(tmp_path):
    import http.server
    import threading
    import zipfile
    from mock_ha import MockHA, TOKEN
    folder=tmp_path/'ha';folder.mkdir();(folder/'configuration.yaml').write_text('default_config:\n')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),MockHA)
    server.root=folder;server.audit=[]
    threading.Thread(target=server.serve_forever,daemon=True).start()
    async def run():
        store=Store(tmp_path/'installed');store.initialize()
        shutil.copytree(Path(__file__).resolve().parents[1]/'app',store.root/'app')
        store.save(Settings(url=f'http://127.0.0.1:{server.server_port}',source_mode='local',source_dir=str(folder),timeout=2),TOKEN)
        before=store.config.read_bytes()
        with create_pipe_input() as inp:
            ui=CapturingUI(store,input=inp,output=DummyOutput())
            await asyncio.wait_for(ui.export_async(),15)
            assert ui.page=='done',(ui.page,ui.message)
            snapshot=store.history()[0]
            with zipfile.ZipFile(snapshot/'ha-context.zip') as z:
                assert z.read('ha-context.txt')==(snapshot/'ha-context.txt').read_bytes()
            assert store.config.read_bytes()==before and store.token()==TOKEN
            assert all(method in {'GET','WS'} for method,_ in server.audit)
    try:asyncio.run(run())
    finally:server.shutdown();server.server_close()


def test_noisy_worker_stderr_cannot_block_export_or_leak_into_ui(tmp_path):
    async def run():
        store=worker_store(tmp_path,"sys.stderr.write('SYNTHETIC_PRIVATE_STDERR' * 100000)\nsys.stderr.flush()\n"+SUCCESS)
        with create_pipe_input() as inp:
            ui=CapturingUI(store,input=inp,output=DummyOutput())
            await asyncio.wait_for(ui.export_async(),10)
            assert ui.page=='done'
            assert 'SYNTHETIC_PRIVATE_STDERR' not in ui.message
            assert not list(store.logs.iterdir())
    asyncio.run(run())
