import asyncio,json
from pathlib import Path
from unittest.mock import patch
import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from hacontext.state import Store,Settings
from hacontext.ui import ContextUI


def test_first_run_does_not_show_legacy_cleanup(tmp_path):
    s=Store(tmp_path/'app');s.initialize()
    with patch('pathlib.Path.home',return_value=tmp_path),create_pipe_input() as inp:
        ui=ContextUI(s,input=inp,output=DummyOutput())
        assert ui.page=='welcome' and 'legacy' not in ui.controls
        ui.controls['start'].handler()
        assert ui.page=='connection'
        assert any(type(getattr(p, 'processor', None)).__name__ == 'PasswordProcessor' and p.filter() for p in ui.controls['token'].control.input_processors)


def test_cleanup_only_after_verified_detection(tmp_path):
    old=tmp_path/'.config/ha-context';old.mkdir(parents=True)
    (old/'connection.json').write_text(json.dumps({'url':'http://localhost:8123','token':'synthetic'}))
    s=Store(tmp_path/'app');s.initialize()
    with patch('pathlib.Path.home',return_value=tmp_path),create_pipe_input() as inp:
        ui=ContextUI(s,input=inp,output=DummyOutput())
        assert 'legacy' in ui.controls
        ui.controls['legacy'].handler()
        assert ui.page=='legacy'
        assert (old/'connection.json').exists()


def test_confirmation_is_not_automatic(tmp_path):
    s=Store(tmp_path/'app');s.initialize();s.save(Settings(url='http://localhost:8123'),'synthetic-test-token')
    with patch('pathlib.Path.home',return_value=tmp_path),create_pipe_input() as inp:
        ui=ContextUI(s,input=inp,output=DummyOutput());ui.reset_confirm()
        ui.controls['confirm'].handler();assert s.config.exists()
        ui.controls['confirm-word'].text='RESET';ui.controls['confirm'].handler()
        assert not s.config.exists() and ui.page=='welcome'


def test_real_terminal_eventloop_accepts_keyboard(tmp_path):
    async def check():
        s=Store(tmp_path/'app');s.initialize()
        with create_pipe_input() as inp:
            ui=ContextUI(s,input=inp,output=DummyOutput())
            task=asyncio.create_task(ui.app.run_async())
            await asyncio.sleep(.1)
            inp.send_text('\r')
            await asyncio.sleep(.1)
            assert ui.page=='connection'
            inp.send_text('\x11')
            await asyncio.wait_for(task,2)
    asyncio.run(check())


def test_editing_detected_url_clears_automatic_address_selection(tmp_path):
    s=Store(tmp_path/'app');s.initialize()
    with create_pipe_input() as inp:
        ui=ContextUI(s,input=inp,output=DummyOutput())
        ui.pending=Settings(url='http://127.0.0.1:8123',auto_url=True,container='home',source_mode='container')
        ui.connection();ui.controls['url'].text='http://192.0.2.2:8123'
        ui.controls['token'].text='SYNTHETIC_TEST_ACCESS_TOKEN';ui.capture_connection()
        assert not ui.pending.auto_url


def test_exit_waits_for_export_worker(tmp_path):
    async def check():
        import sys
        s=Store(tmp_path/'app');s.initialize()
        with create_pipe_input() as inp:
            ui=ContextUI(s,input=inp,output=DummyOutput())
            task=asyncio.create_task(ui.app.run_async())
            await asyncio.sleep(.1)
            worker=await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(60)',start_new_session=True)
            ui.process=worker;ui.quit()
            await asyncio.wait_for(task,4)
            assert worker.returncode is not None
    asyncio.run(check())


def test_all_main_pages_render_in_80_by_24_terminal(tmp_path):
    from prompt_toolkit.data_structures import Size
    class Small(DummyOutput):
        def get_size(self):return Size(rows=24,columns=80)
    async def check():
        s=Store(tmp_path/'app');s.initialize();s.save(Settings(url='http://127.0.0.1:8123'),'SYNTHETIC_TEST_TOKEN')
        with create_pipe_input() as inp:
            ui=ContextUI(s,input=inp,output=Small())
            task=asyncio.create_task(ui.app.run_async());await asyncio.sleep(.05)
            for name in ['overview','export_page','connection','source_page','privacy_page','ready_page','maintenance','settings_page']:
                getattr(ui,name)();await asyncio.sleep(.05)
                screen=ui.app.renderer.last_rendered_screen
                text='\n'.join(''.join(screen.data_buffer[y][x].char for x in range(80)) for y in range(24))
                assert 'Window too small' not in text,name
            inp.send_text('\x11');await asyncio.wait_for(task,2)
    asyncio.run(check())


def test_full_onboarding_saves_settings_notes_and_one_command(tmp_path,monkeypatch):
    import http.server,threading,os
    from mock_ha import MockHA,TOKEN
    from hacontext.state import Settings
    home=tmp_path/'home';home.mkdir();bin_dir=home/'.local/bin';bin_dir.mkdir(parents=True)
    config=tmp_path/'ha';config.mkdir();(config/'configuration.yaml').write_text('default_config:\n')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),MockHA);server.root=config;server.audit=[]
    threading.Thread(target=server.serve_forever,daemon=True).start()
    monkeypatch.setenv('PATH',str(bin_dir)+os.pathsep+os.environ['PATH'])
    async def check():
        store=Store(home/'ha-context');store.initialize();(store.root/'ha-context').write_text('#!/bin/sh\n')
        with patch('pathlib.Path.home',return_value=home),create_pipe_input() as inp:
            ui=ContextUI(store,input=inp,output=DummyOutput())
            task=asyncio.create_task(ui.app.run_async());await asyncio.sleep(.05)
            ui.connection();ui.controls['url'].text=f'http://127.0.0.1:{server.server_port}';ui.controls['token'].text=TOKEN
            await ui.connection_next();assert ui.page=='source'
            ui.controls['source_mode'].current_value='local';ui.controls['source_dir'].text=str(config)
            ui.source_next();assert ui.page=='privacy'
            ui.controls['notes'].text='Synthetic room context';ui.privacy_next();assert ui.page=='ready'
            await ui.finish_setup();assert ui.page=='overview'
            assert store.load().source_dir==str(config) and store.token()==TOKEN
            assert store.notes.read_text()=='Synthetic room context'
            assert (bin_dir/'ha-context').is_symlink()
            assert (bin_dir/'ha-context').resolve()==(store.root/'ha-context').resolve()
            inp.send_text('\x11');await task
    try:asyncio.run(check())
    finally:server.shutdown();server.server_close()
