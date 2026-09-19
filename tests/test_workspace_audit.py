"""Check the actual screen routes and the limits of filtered entity views."""
import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.data_structures import Size

from hacontext.state import Store, Settings
from hacontext.ui import ContextUI
from hacontext.worker import rebuild_bundle


class CapturingUI(ContextUI):
    def __init__(self, *args, **kwargs):
        self.buttons = []
        super().__init__(*args, **kwargs)

    def button(self, text, handler, name=None):
        button = super().button(text, handler, name)
        self.buttons.append(button)
        return button

    def choose(self, text):
        next(button for button in reversed(self.buttons) if button.text == text).handler()


def populated_store(tmp_path):
    store = Store(tmp_path / 'installed')
    store.initialize()
    store.save(Settings(url='http://127.0.0.1:8123'), 'SYNTHETIC_UI_TOKEN')
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / 'app/docs', store.root / 'app/docs')
    snapshot = store.exports / '20260919T120000'
    entries = [
        {'entity_id': 'light.desk', 'name': 'Desk', 'state': 'on', 'disabled_by': None},
        {'entity_id': 'sensor.phone_battery', 'state': '80', 'platform': 'mobile_app', 'device_id': 'phone-new', 'disabled_by': None},
        {'entity_id': 'sensor.phone_old', 'state': '[not in live states]', 'platform': 'mobile_app', 'device_id': 'phone-old', 'disabled_by': 'config_entry'},
    ]
    summary = {'status': 'Complete', 'scope': 'API + configuration files', 'live_entities': 2, 'registered_entities': 3, 'devices': 2, 'companion_registrations': 2}
    sections = {'entities.json': json.dumps(entries), 'summary.json': json.dumps(summary),
                'companion.json': json.dumps([{'device_id': 'phone-new'}, {'device_id': 'phone-old'}]),
                'coverage.json': '{}', 'issues.json': '[]', 'privacy.txt': 'Review before sharing'}
    rebuild_bundle(snapshot, sections, {'tool': 'ha-context'})
    return store, snapshot


def test_every_sidebar_route_opens_with_an_existing_snapshot(tmp_path):
    class Small(DummyOutput):
        def get_size(self):
            return Size(rows=24, columns=80)

    async def audit():
        store, snapshot = populated_store(tmp_path)
        with patch('pathlib.Path.home', return_value=tmp_path), create_pipe_input() as inp:
            ui = CapturingUI(store, input=inp, output=Small())
            task = asyncio.create_task(ui.app.run_async())
            await asyncio.sleep(.05)
            for label, page in [
                ('Overview', 'overview'), ('Create export', 'export'),
                ('Devices & sensors', 'inventory'), ('Export history', 'history'),
                ('Diagnostics', 'diagnostics'), ('Notes', 'notes'),
                ('Documentation', 'docs'), ('Settings', 'settings'), ('Maintenance', 'maintenance'),
            ]:
                ui.choose(label)
                await asyncio.sleep(.03)
                assert ui.page == page, (label, ui.page, ui.message)
                screen = ui.app.renderer.last_rendered_screen
                text = '\n'.join(''.join(screen.data_buffer[y][x].char for x in range(80)) for y in range(24))
                assert 'Window too small' not in text, label
            ui.choose('Settings')
            ui.choose('Privacy & retention')
            assert ui.page == 'privacy'
            ui.choose('Export history')
            ui.choose('Review')
            assert ui.page == 'preview'
            assert 'Complete' in ui.controls['preview-text'].text
            inp.send_text('\x11')
            await asyncio.wait_for(task, 3)

    asyncio.run(audit())


def test_phone_filters_and_saved_view_are_explicitly_not_full_exports(tmp_path):
    store, snapshot = populated_store(tmp_path)
    with patch('pathlib.Path.home', return_value=tmp_path), create_pipe_input() as inp:
        ui = CapturingUI(store, input=inp, output=DummyOutput())
        ui.inventory(True)
        ui.controls['entity-status'].current_value = 'enabled'
        ui.choose('Apply filters')
        assert [row['entity_id'] for row in ui.filtered_entities] == ['sensor.phone_battery']
        ui.choose('Save filtered view')
        output = (store.local / 'selections/selected-entities.txt').read_text()
        assert 'not a full HA configuration' in output
        assert 'sensor.phone_old' not in output
        ui.choose('Phone registrations')
        assert ui.page == 'preview'
        assert 'phone-new' in ui.controls['preview-text'].text
        assert 'phone-old' in ui.controls['preview-text'].text


def test_clean_maintenance_has_no_legacy_cleanup_button(tmp_path):
    store, _ = populated_store(tmp_path)
    with patch('pathlib.Path.home', return_value=tmp_path), create_pipe_input() as inp:
        ui = CapturingUI(store, input=inp, output=DummyOutput())
        ui.buttons = []
        ui.maintenance()
        assert not any('old files' in button.text.lower() for button in ui.buttons)
        assert 'Reset settings' in [button.text for button in ui.buttons]
        assert 'Uninstall ha-context' in [button.text for button in ui.buttons]
