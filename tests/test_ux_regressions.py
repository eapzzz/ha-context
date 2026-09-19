"""Behavioral regressions: drive keyboard input, not just click Python handlers."""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.data_structures import Size
from hacontext.state import Store
from hacontext.ui import ContextUI
from test_workspace_audit import populated_store, CapturingUI

class Terminal(DummyOutput):
    def get_size(self):
        return Size(rows=32, columns=110)

def test_document_chapter_changes_with_arrow_key(tmp_path):
    async def run():
        store, _ = populated_store(tmp_path)
        with create_pipe_input() as inp:
            ui = ContextUI(store, input=inp, output=Terminal())
            task = asyncio.create_task(ui.app.run_async())
            try:
                await asyncio.sleep(.06)
                ui.docs(); await asyncio.sleep(.06)
                before = ui.controls['doc-text'].text
                inp.send_text('\x1b[B')
                await asyncio.sleep(.08)
                assert ui.controls['doc-text'].text != before
                assert ui.controls['docs'].current_value.endswith('02-connection.md')
                inp.send_text('\x1b[A'); await asyncio.sleep(.08)
                assert ui.controls['doc-text'].text == before
            finally:
                ui.app.exit(); await task
    asyncio.run(run())

def test_workspace_background_extent_does_not_follow_page_height(tmp_path):
    async def run():
        store, _ = populated_store(tmp_path)
        with create_pipe_input() as inp:
            ui = ContextUI(store, input=inp, output=Terminal())
            task = asyncio.create_task(ui.app.run_async())
            try:
                await asyncio.sleep(.06)
                edges=[]
                for action in (ui.overview, ui.docs, ui.notes_page, ui.settings_page, ui.maintenance):
                    action(); await asyncio.sleep(.06)
                    screen=ui.app.renderer.last_rendered_screen
                    # The right edge of the workspace must extend to the row above status.
                    edges.append([(y,screen.data_buffer[y][109].char,ui.app._merged_style.get_attrs_for_style_str(screen.data_buffer[y][109].style).bgcolor)
                                  for y in range(2,30)])
                assert all(edge == edges[0] for edge in edges[1:])
            finally:
                ui.app.exit(); await task
    asyncio.run(run())

def test_context_notes_are_scoped_private_and_preserve_general_notes(tmp_path):
    store, _ = populated_store(tmp_path)
    store.notes.write_text('Existing general context')
    assert callable(getattr(store, 'save_annotation', None)), 'Per-object notes are missing'
    store.save_annotation('entity','light.desk','Below the TV')
    store.save_annotation('device','phone-new','Primary phone')
    assert store.annotation('entity','light.desk') == 'Below the TV'
    assert store.annotation('device','phone-new') == 'Primary phone'
    store.save_annotation('entity','light.desk','Behind the TV')
    assert store.annotation('entity','light.desk') == 'Behind the TV'
    store.reset()
    assert store.notes.read_text()=='Existing general context'
    assert store.annotation('entity','light.desk') == 'Behind the TV'
    assert store.annotations.stat().st_mode & 0o777 == 0o600
    store.save_annotation('entity','light.desk','')
    assert store.annotation('entity','light.desk') == ''

def test_inventory_search_filters_without_apply_button(tmp_path):
    store, _ = populated_store(tmp_path)
    with create_pipe_input() as inp:
        ui=ContextUI(store,input=inp,output=Terminal());ui.inventory()
        ui.controls['inventory-search'].text='light.desk'
        assert [r['entity_id'] for r in ui.filtered_entities]==['light.desk']
        assert 'light.desk' in ui.controls['entity-details'].text

def test_editing_selected_entity_note_returns_to_filtered_inventory(tmp_path):
    store, _ = populated_store(tmp_path)
    with create_pipe_input() as inp:
        ui=CapturingUI(store,input=inp,output=Terminal());ui.inventory()
        assert any(b.text=='Entity note' for b in ui.buttons), 'No contextual annotation action'
        ui.controls['inventory-search'].text='light.desk'
        ui.choose('Entity note')
        assert ui.page=='annotation'
        ui.controls['annotation-editor'].text='Below the TV'
        ui.choose('Save note')
        assert ui.page=='inventory'
        assert store.annotation('entity','light.desk')=='Below the TV'
        assert ui.controls['inventory-search'].text=='light.desk'

def test_sidebar_supports_arrows_and_active_page(tmp_path):
    async def run():
        store, _ = populated_store(tmp_path)
        with create_pipe_input() as inp:
            ui=ContextUI(store,input=inp,output=Terminal())
            task=asyncio.create_task(ui.app.run_async())
            try:
                await asyncio.sleep(.06)
                inp.send_text('\x1b[17~') # F6 focuses the persistent navigation.
                await asyncio.sleep(.06)
                inp.send_text('\x1b[B\r')
                await asyncio.sleep(.08)
                assert ui.page=='export'
            finally:
                ui.app.exit(); await task
    asyncio.run(run())

def test_notes_export_is_tied_to_ids_and_has_matching_txt_zip(tmp_path):
    import http.server, threading, zipfile
    from hacontext.state import Settings
    from hacontext.worker import run_export
    from mock_ha import MockHA, TOKEN
    config=tmp_path/'config';config.mkdir()
    (config/'configuration.yaml').write_text('default_config:\n')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),MockHA)
    server.root=config;server.audit=[]
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        store=Store(tmp_path/'installed');store.initialize()
        store.save(Settings(url=f'http://127.0.0.1:{server.server_port}',source_mode='local',source_dir=str(config),timeout=2),TOKEN)
        assert callable(getattr(store,'save_annotation',None)), 'No structured note store'
        store.notes.write_text('General context')
        store.save_annotation('entity','light.desk','Below the TV '+TOKEN)
        store.save_annotation('device','dev1','Do not unplug')
        store.save_annotation('area','bedroom','Upstairs')
        store.save_annotation('entity','light.removed','Keep this unmatched context')
        path,_=run_export(store)
        records=json.loads((path/'annotations.json').read_text())['annotations']
        assert records[0]['kind'] in {'area','device','entity'}
        lamp=next(x for x in records if x['id']=='light.desk')
        assert lamp['matched'] is True
        assert 'Below the TV' in lamp['note'] and TOKEN not in lamp['note']
        stale=next(x for x in records if x['id']=='light.removed')
        assert stale['matched'] is False
        text=(path/'ha-context.txt').read_text()
        assert 'General context' in text and 'Below the TV' in text and TOKEN not in text
        with zipfile.ZipFile(path/'ha-context.zip') as z:
            assert z.read('ha-context.txt')==(path/'ha-context.txt').read_bytes()
            assert z.read('annotations.json')==(path/'annotations.json').read_bytes()
    finally:
        server.shutdown();server.server_close()

def test_mouse_selects_document_without_an_extra_open_button(tmp_path):
    from prompt_toolkit.mouse_events import MouseEvent, MouseEventType, MouseButton
    from prompt_toolkit.data_structures import Point
    store,_=populated_store(tmp_path)
    with create_pipe_input() as inp:
        ui=ContextUI(store,input=inp,output=Terminal());ui.docs()
        pick=ui.controls['docs'];before=ui.controls['doc-text'].text
        handler=next(f[2] for f in pick._get_text_fragments() if len(f)>2)
        handler(MouseEvent(position=Point(x=3,y=1),event_type=MouseEventType.MOUSE_UP,button=MouseButton.LEFT,modifiers=frozenset()))
        assert ui.controls['doc-text'].text!=before
        assert pick.current_value.endswith('02-connection.md')

def test_document_previous_next_and_reader_search(tmp_path):
    async def run():
        store,_=populated_store(tmp_path)
        with create_pipe_input() as inp:
            ui=CapturingUI(store,input=inp,output=Terminal());task=asyncio.create_task(ui.app.run_async())
            try:
                await asyncio.sleep(.04);ui.docs();original=ui.controls['doc-text'].text
                ui.choose('Next');assert ui.controls['docs'].current_value.endswith('02-connection.md')
                ui.choose('Previous');assert ui.controls['doc-text'].text==original
                inp.send_text('\x06');await asyncio.sleep(.08)
                assert ui.app.layout.is_searching, 'Ctrl-F must reach the reader even from the chapter list'
            finally:ui.app.exit();await task
    asyncio.run(run())

def test_selected_entity_survives_editing_its_note(tmp_path):
    store,_=populated_store(tmp_path)
    with create_pipe_input() as inp:
        ui=CapturingUI(store,input=inp,output=Terminal());ui.inventory()
        ui.controls['entities'].move(1)
        original=ui.controls['entities'].current_value
        ui.choose('Entity note');ui.controls['annotation-editor'].text='My primary phone';ui.choose('Save note')
        assert ui.controls['entities'].current_value==original

def test_annotation_validation_preserves_malformed_source(tmp_path):
    import pytest
    store,_=populated_store(tmp_path)
    assert callable(getattr(store,'save_annotation',None))
    with pytest.raises(ValueError):store.save_annotation('service','light.desk','wrong kind')
    store.annotations.write_text('broken JSON')
    with pytest.raises(ValueError):store.save_annotation('entity','light.desk','note')
    assert store.annotations.read_text()=='broken JSON'

def test_unsaved_context_survives_navigation_and_quit_needs_confirmation(tmp_path):
    async def run():
        store,_=populated_store(tmp_path)
        with create_pipe_input() as inp:
            ui=CapturingUI(store,input=inp,output=Terminal());task=asyncio.create_task(ui.app.run_async())
            try:
                await asyncio.sleep(.05)
                ui.general_notes();ui.controls['notes-editor'].text='Unsaved household context'
                ui.overview();ui.general_notes()
                assert ui.controls['notes-editor'].text=='Unsaved household context'
                inp.send_text('\x11');await asyncio.sleep(.07)
                assert not task.done(), 'Quitting must not silently discard note drafts'
                assert ui.page=='confirm'
                ui.choose('Cancel')
                inp.send_text('\x13');await asyncio.sleep(.07)
                assert store.notes.read_text()=='Unsaved household context'
                inp.send_text('\x11');await asyncio.wait_for(task,2)
            finally:
                if not task.done():ui.app.exit();await task
    asyncio.run(run())

def test_docs_prose_wraps_on_words_and_preserves_code():
    from hacontext.ui_widgets import wrap_document
    text='## Connection\n\nOne fairly long paragraph that should wrap at words instead of breaking the middle.\n\n```sh\nha-context export\n```\n'
    result=wrap_document(text,24)
    assert 'ha-context export' in result and '## Connection' in result
    assert 'paragraph' in result and 'parag\nraph' not in result
    assert max(map(len,result.splitlines()))<=24

def test_inventory_uses_cached_parsed_snapshot(tmp_path,monkeypatch):
    store,snapshot=populated_store(tmp_path)
    original=Path.read_text;reads=[]
    def read(path,*args,**kwargs):
        if path==snapshot/'entities.json':reads.append(path)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    with create_pipe_input() as inp:
        ui=ContextUI(store,input=inp,output=Terminal())
        ui.inventory();ui.overview();ui.inventory()
        assert len(reads)==1
        assert ui.inventory_rows

def test_resizing_keeps_workspace_fixed_and_visible(tmp_path):
    class Resizable(DummyOutput):
        rows=32;columns=110
        def get_size(self):return Size(rows=self.rows,columns=self.columns)
    async def run():
        store,_=populated_store(tmp_path);out=Resizable()
        with create_pipe_input() as inp:
            ui=ContextUI(store,input=inp,output=out);task=asyncio.create_task(ui.app.run_async())
            try:
                await asyncio.sleep(.05)
                for w,h in [(80,24),(118,40),(100,30),(80,24)]:
                    out.rows=h;out.columns=w
                    for route in [ui.overview,ui.inventory,ui.notes_page,ui.docs,ui.settings_page,ui.maintenance]:
                        route();ui.app.invalidate();await asyncio.sleep(.04)
                        screen=ui.app.renderer.last_rendered_screen
                        text='\n'.join(''.join(screen.data_buffer[y][x].char for x in range(w)) for y in range(h))
                        assert 'Window too small' not in text,(ui.page,w,h)
                        colors={ui.app._merged_style.get_attrs_for_style_str(screen.data_buffer[y][w-1].style).bgcolor for y in range(2,h-2)}
                        assert colors=={'172734'},(ui.page,w,h,colors)
                        assert 'Ctrl-Q' in text.splitlines()[-1]
                ui.docs();await asyncio.sleep(.04)
                before=ui.controls['doc-text'].text
                out.columns=118;ui.app.invalidate();await asyncio.sleep(.06)
                assert ui.controls['doc-text'].text!=before
            finally:ui.app.exit();await task
    asyncio.run(run())

def test_back_to_original_text_after_save_is_still_an_unsaved_change(tmp_path):
    store,_=populated_store(tmp_path)
    with create_pipe_input() as inp:
        ui=CapturingUI(store,input=inp,output=Terminal());ui.general_notes()
        ui.controls['notes-editor'].text='Saved revised content';ui.choose('Save notes')
        ui.controls['notes-editor'].text=''
        assert ui.note_drafts.get('general')==''


def test_malformed_and_symlinked_annotation_store_is_not_overwritten(tmp_path):
    import pytest
    store,_=populated_store(tmp_path)
    outside=tmp_path/'unrelated';outside.write_text('keep')
    store.annotations.symlink_to(outside)
    with pytest.raises(ValueError):store.save_annotation('entity','light.desk','No')
    assert outside.read_text()=='keep'
